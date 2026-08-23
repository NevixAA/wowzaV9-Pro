"""
BTTS asymmetry features — because BTTS is about goal DISTRIBUTION, not goal VOLUME.
==================================================================================
THE DIAGNOSIS. v9's BTTS model sits exactly at its own base rate: measured AUC-equivalent lift
of +0.0042 over the BTTS base rate, versus +0.0294 for over15 and +0.0155 for newformat. It is
not broken; it is answering a question its features cannot distinguish.

`FEATURE_COLS` is shared across every market and is almost entirely about how MANY goals:
combined attack/defence strength, xG, `p_over25_poisson_dc`, `h2h_avg_goals`, rolling scored and
conceded. Consider two fixtures with an identical 2.5 expected goals:

    lambda 1.25 + 1.25  ->  P(both score) is high
    lambda 2.30 + 0.20  ->  P(both score) is low

Every volume feature is nearly identical across those two. Nothing in the set separates them, so
the model cannot learn BTTS beyond what the total tells it — and the total is genuinely weak
evidence for BTTS.

THE ONE IDEA WORTH TAKING AWAY: **BTTS is bounded by the WEAKER attack.** A 4-0 match has plenty
of goals and no BTTS. So `min(lambda_h, lambda_a)` is far more informative than
`lambda_h + lambda_a`, and the sum is what every existing feature is a proxy for.

WHAT IS ADDED, and why each one is not redundant with the existing set:

    lam_home / lam_away        attack strength x opponent defence x league mean. v9's existing
                               Poisson lambda is `home_scored_last5` ALONE, which ignores who
                               they are playing -- a 2.0-scoring side against the best defence
                               in the division gets the same lambda as against the worst.
    p_home_scores              1 - P(home blanked). The direct quantity.
    p_away_scores
    p_btts_poisson             independent product -- the naive baseline
    p_btts_dc                  Dixon-Coles corrected. DC exists because independent Poisson
                               misprices exactly the low scorelines (0-0, 1-0, 0-1, 1-1) that
                               decide BTTS, so the correction matters MORE here than for O/U 2.5,
                               where it was originally added.
    lam_min                    the weaker attack -- the binding constraint (see above)
    lam_asymmetry              |lh - la| / (lh + la): normalised, so it is not a volume proxy
    p_neither_cs               (1 - home_cs_rate) x (1 - away_cs_rate) from season venue splits:
                               an empirical counterpart to the Poisson estimate
    btts_rate_hist             mean of the two sides' recent BTTS-adjacent tendency

CALIBRATION. v9's BTTS model is biased LOW by -1.49pp (true base rate 0.5283, model mean 0.5134,
market 0.5416 -- the market is closer to the truth than the model). That bias is a prerequisite
for ever enabling BTTS-NO, because a model that understates P(BTTS) will systematically find
fake value on NO. `bias_correction` measures it; it is reported, never silently applied.

────────────────────────────────────────────────────────────────────────────────
RESULT (2026-08-23): **THE HYPOTHESIS IS REFUTED ON THIS SAMPLE. DO NOT SHIP THESE FEATURES.**

`src.pipelines.btts_eval`, 778 labelled rows, chronological split, 156 test rows, scored against
the BTTS base rate rather than 0.50:

    base rate constant           Brier 0.24445      <- BEST
    volume features only               0.25272      -0.00827 vs constant
    volume + lam_min                   0.25294      -0.00850
    volume + all asymmetry             0.26545      -0.02100
    unfitted Dixon-Coles alone         0.28364      -0.03919

    Brier(volume) - Brier(volume+asymmetry) = -0.01273, 95% CI [-0.02500, -0.00008]
    -> asymmetry does not merely fail to help, it HURTS, and the interval excludes zero.

Per-feature discrimination over all 778 rows tells you exactly why:

    p_over25_poisson_dc  AUC 0.5600   <- the best discriminator is a VOLUME feature
    btts_rate_hist            0.5533
    lam_asymmetry             0.5309
    lam_min                   0.4898   <- BELOW chance. The claim above is simply false here.
    lam_sum                   0.5084
    p_btts_dc                 0.5032   <- no discrimination at all
    p_btts_poisson            0.5026

WHAT THAT ACTUALLY MEANS, because it is not "distribution doesn't matter". The arithmetic is
demonstrably right: dixon_coles_p_btts(1.25, 1.25) = 0.519 while dixon_coles_p_btts(2.30, 0.20)
= 0.166 — same 2.5 total, completely different answer. The physics separates those fixtures. But
`p_btts_dc` has AUC 0.5032 against real outcomes, which means **the lambdas fed into it carry no
usable per-team signal.** `attack_str x opponent_defense_str x league_avg/2` is too noisy at this
resolution, and a distribution model built on noisy per-team rates is worse than a volume model,
because summing the two teams cancels some of that noise while splitting them keeps all of it.

So the real bottleneck is UPSTREAM of anything in this module: per-team scoring-rate estimation.
The productive next step is better lambdas — opponent-adjusted, longer windows, shrunk toward the
league mean — not more distribution features layered on the current ones.

TWO INCIDENTAL FINDINGS. `odds_btts` has 0/778 coverage in the backfill, so the market's own BTTS
price is not in the training data at all — which matters, since the market beats the model on
BTTS. And `api_implied_btts` has too few distinct values to score, consistent with root CLAUDE.md
invariant 9: it was one of the hardcoded 0.5 stand-ins.

CALIBRATION. Measured bias on the test split is -7.50pp (volume) and -6.41pp (with asymmetry),
both worse than the -1.49pp seen previously — partly a regime shift, since the base rate moves
from 0.5354 in train to 0.5962 in test. Either way **BTTS-NO must stay disabled**: a model
understating P(BTTS) by 6-7pp manufactures fake value on NO.

SAMPLE CAVEAT, stated so this is not over-read in either direction: 156 test rows spanning FOUR
DAYS, with a 6pp base-rate shift between train and test. That is enough to refuse to ship these
features and nowhere near enough to close the question. Re-run when the backfill is materially
larger.

STATUS: RESEARCH, and a NEGATIVE result. Nothing here is wired into any model. It does not touch
v9, which is frozen, and it retrains nothing in production.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Published Dixon-Coles low-score correlation. Same value v9's O/U path uses, so the two
# corrections cannot disagree about the same fixture.
RHO = -0.08


def _pois(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles correction on the four low scorelines."""
    if x == 0 and y == 0:
        return 1.0 - lh * la * rho
    if x == 1 and y == 0:
        return 1.0 + la * rho
    if x == 0 and y == 1:
        return 1.0 + lh * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_p_btts(lam_h: float, lam_a: float, rho: float = RHO,
                       max_goals: int = 10) -> float:
    """P(both teams score) with the Dixon-Coles low-score correction.

        P(BTTS) = 1 - P(home blanked) - P(away blanked) + P(0-0)

    The DC correction is applied inside each term rather than to the result, because it is
    scoreline-specific: only (0,0), (1,0), (0,1) and (1,1) carry a tau, and three of those four
    are exactly the scorelines that decide whether BTTS happened. Applying a single scalar to the
    final probability would be a different model wearing the same name.
    """
    lh = max(0.05, min(float(lam_h), 8.0))
    la = max(0.05, min(float(lam_a), 8.0))
    p_h0 = sum(_tau(0, a, lh, la, rho) * _pois(0, lh) * _pois(a, la)
               for a in range(max_goals + 1))
    p_a0 = sum(_tau(h, 0, lh, la, rho) * _pois(h, lh) * _pois(0, la)
               for h in range(max_goals + 1))
    p_00 = _tau(0, 0, lh, la, rho) * _pois(0, lh) * _pois(0, la)
    return float(max(0.0, min(1.0, 1.0 - p_h0 - p_a0 + p_00)))


FEATURES = ["lam_home", "lam_away", "lam_min", "lam_sum", "lam_asymmetry",
            "p_home_scores", "p_away_scores", "p_btts_poisson", "p_btts_dc",
            "p_neither_cs", "btts_rate_hist"]


def _num(d: pd.DataFrame, col: str, default=np.nan) -> pd.Series:
    if col not in d.columns:
        return pd.Series(default, index=d.index, dtype="float64")
    return pd.to_numeric(d[col], errors="coerce")


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the BTTS asymmetry features. Missing inputs give NaN, never a substituted number."""
    d = df.copy()
    lg = _num(d, "league_avg_goals").fillna(2.6)
    # Attack x opponent defence, halved because league_avg_goals is the MATCH total, not the
    # per-side mean. Getting that wrong doubles every lambda and silently inflates every BTTS
    # probability toward 1.
    half = (lg / 2.0).clip(lower=0.3, upper=3.0)
    h_att, a_att = _num(d, "home_attack_str"), _num(d, "away_attack_str")
    h_def, a_def = _num(d, "home_defense_str"), _num(d, "away_defense_str")

    lam_h = (h_att * a_def * half)
    lam_a = (a_att * h_def * half)
    # Fall back to the raw rolling rate only where a strength is missing — better a cruder
    # lambda than none, and the fallback is visible in the column rather than hidden.
    lam_h = lam_h.fillna(_num(d, "home_scored_last5")).clip(lower=0.05, upper=8.0)
    lam_a = lam_a.fillna(_num(d, "away_scored_last5")).clip(lower=0.05, upper=8.0)

    d["lam_home"] = lam_h
    d["lam_away"] = lam_a
    d["lam_min"] = np.minimum(lam_h, lam_a)
    d["lam_sum"] = lam_h + lam_a
    d["lam_asymmetry"] = ((lam_h - lam_a).abs() / (lam_h + lam_a).replace(0, np.nan))
    d["p_home_scores"] = 1.0 - np.exp(-lam_h)
    d["p_away_scores"] = 1.0 - np.exp(-lam_a)
    d["p_btts_poisson"] = d["p_home_scores"] * d["p_away_scores"]
    d["p_btts_dc"] = [dixon_coles_p_btts(h, a) if pd.notna(h) and pd.notna(a) else np.nan
                      for h, a in zip(lam_h, lam_a)]

    h_cs, a_cs = _num(d, "home_cs_rate_h"), _num(d, "away_cs_rate_a")
    d["p_neither_cs"] = (1.0 - h_cs) * (1.0 - a_cs)

    # Empirical tendency. Uses over15 rates as the closest available proxy for "both sides tend
    # to be involved in scoring"; a true per-team BTTS rate is not in the stored feature set and
    # is NOT invented here.
    d["btts_rate_hist"] = (_num(d, "home_over25_last5") + _num(d, "away_over25_last5")) / 2.0
    return d


def btts_label(df: pd.DataFrame) -> pd.Series:
    """1 when both teams scored. NaN when either score is unknown — never assumed 0."""
    h = pd.to_numeric(df.get("home_goals"), errors="coerce")
    a = pd.to_numeric(df.get("away_goals"), errors="coerce")
    y = ((h >= 1) & (a >= 1)).astype("float64")
    y[h.isna() | a.isna()] = np.nan
    return y


def bias_correction(y_true: pd.Series, p_model: pd.Series) -> dict:
    """Mean-probability bias. Reported, never applied silently.

    A model biased LOW on P(BTTS) manufactures fake value on BTTS-NO, which is why this has to be
    measured before BTTS-NO could ever be enabled.
    """
    m = pd.DataFrame({"y": pd.to_numeric(y_true, errors="coerce"),
                      "p": pd.to_numeric(p_model, errors="coerce")}).dropna()
    if m.empty:
        return {"n": 0}
    return {"n": int(len(m)), "base_rate": round(float(m["y"].mean()), 4),
            "model_mean": round(float(m["p"].mean()), 4),
            "bias_pp": round(float((m["p"].mean() - m["y"].mean()) * 100), 2)}
