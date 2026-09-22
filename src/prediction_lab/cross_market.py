"""Do our models know anything ABOUT EACH OTHER'S markets that the market's own model missed?

    python -m src.prediction_lab.cross_market

THE QUESTION, stated so it cannot drift. Not "are BTTS and Over 2.5 correlated" -- they obviously
are, both are made of goals, and finding that out would be a fact about football rather than a
fact about our models. The question is:

    AFTER I ALREADY KNOW WHAT THE OVER 2.5 MODEL THINKS, does knowing what the BTTS model
    thinks make my prediction of Over 2.5 more accurate?

That is a question about INCREMENTAL information, and almost every naive version of this analysis
answers a different, easier question by accident.

THE TRAP THIS CODE IS BUILT TO AVOID. Our four models are trained on THE SAME 145 FEATURES. Any
correlation between their outputs is therefore guaranteed before a single match is played -- they
are four views of one feature vector. So a conditional table showing "when P(BTTS) is high,
Over 2.5 happens more often" proves nothing at all: both are high because the same rolling-form
columns were high. The only test that separates "genuinely extra information" from "the same
information wearing a different hat" is an out-of-sample one, on fixtures the meta-model never
saw, comparing a model given P_O25 alone against a model given P_O25 plus the others.

WHAT IT RUNS ON. The out-of-sample probability frame from `run.py baselines` -- roughly 26,000
fixtures, each carrying four probabilities produced by models that had never seen that fixture.
Using in-sample probabilities here would be catastrophic: a model's fitted probability on its own
training row already contains the answer, and every cross-market relationship would look real.

DISCOVERY IS SEPARATED FROM CONFIRMATION. Patterns are found on the earlier part of the OOS
period and then re-measured on the later part, which they have never touched. A pattern that
looks strong in discovery and dies in validation is reported as FAILED, not quietly dropped --
those are the most useful rows in the output file.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.prediction_lab import data as D
from src.prediction_lab import experiments as E
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M

CALC_VERSION = "1.0.0"
MARKETS = ("btts", "over15", "over25", "over35")
MIN_CELL = 150                 # below this a conditional cell is printed but never interpreted
EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def load_wide(*, path: str | None = None) -> pd.DataFrame:
    """One row per fixture: every model's OOS probability, plus what actually happened."""
    p = D.out_dir() / "oof_probabilities.parquet"
    oof = pd.read_parquet(path or p)
    keep = list(MARKETS) + ["home_scores", "away_scores", "home_2plus", "away_2plus"]
    oof = oof[oof.target.isin(keep)]
    probs = oof.pivot_table(index="fixture_key", columns="target", values="p", aggfunc="last")
    probs.columns = [f"p_{c}" for c in probs.columns]
    meta = (oof.drop_duplicates("fixture_key")
               .set_index("fixture_key")[["date", "league", "model_type", "fold"]])
    w = meta.join(probs, how="inner")

    # Actual outcomes come from the dataset, never from the OOS frame's own y column, so that
    # every target is present on every row even where a model produced no probability.
    fx = D.load_fixtures().set_index("fixture_key")
    cols = [c for c in ("home_goals", "away_goals", "total_goals", "goals_bucket") + tuple(keep)
            if c in fx.columns]
    w = w.join(fx[cols], how="inner")
    return w.reset_index().sort_values("date", kind="mergesort").reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# 1. The matrix: does model A's probability rank market B's outcome?
# ---------------------------------------------------------------------------------------------

def cross_matrix(w: pd.DataFrame) -> pd.DataFrame:
    """Every model probability against every actual outcome. AUC, not correlation.

    AUC answers "does this probability sort fixtures by whether the thing happened", which is the
    question. A Pearson correlation between a probability and a 0/1 outcome is bounded by the
    base rate and is hard to read across targets with different prevalences.
    """
    rows = []
    for src in MARKETS:
        for tgt in MARKETS:
            a = M.auc(w[tgt].to_numpy(), w[f"p_{src}"].to_numpy())
            rows.append({"signal_model": src, "actual_outcome": tgt, "n": int(len(w)),
                         "auc": round(a, 4), "own_model": src == tgt,
                         "spearman": round(float(pd.Series(w[f"p_{src}"]).corr(
                             pd.Series(w[tgt]), method="spearman")), 4)})
    return pd.DataFrame(rows)


def prediction_correlation(w: pd.DataFrame) -> pd.DataFrame:
    """How alike are the four models' opinions? High correlation here is the null hypothesis."""
    cols = [f"p_{m}" for m in MARKETS]
    c = w[cols].corr(method="pearson").round(4)
    c.index.name = "model"
    return c.reset_index()


def error_correlation(w: pd.DataFrame) -> pd.DataFrame:
    """When one model is wrong, are the others wrong on the same fixture?

    This matters more than agreement does. Two models that agree but fail together give one
    piece of evidence dressed up as two, and any "both models agree" rule built on them is much
    weaker than its sample size suggests.
    """
    err = {}
    for m in MARKETS:
        call = (w[f"p_{m}"] >= 0.5).astype(int)
        err[m] = (call != w[m]).astype(int)
    e = pd.DataFrame(err)
    rows = []
    for i, a in enumerate(MARKETS):
        for b in MARKETS[i + 1:]:
            both = float(((e[a] == 1) & (e[b] == 1)).mean())
            ind = float(e[a].mean() * e[b].mean())
            rows.append({"model_a": a, "model_b": b,
                         "err_rate_a": round(float(e[a].mean()), 4),
                         "err_rate_b": round(float(e[b].mean()), 4),
                         "both_wrong": round(both, 4),
                         "both_wrong_if_independent": round(ind, 4),
                         "excess_pp": round((both - ind) * 100, 2),
                         "phi": round(float(e[a].corr(e[b])), 4)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# 2. Conditional outcome tables
# ---------------------------------------------------------------------------------------------

BUCKETS = (0.0, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 1.01)


def conditional_outcomes(w: pd.DataFrame) -> pd.DataFrame:
    """For each model's probability bucket, what actually happened in EVERY market."""
    rows = []
    for src in MARKETS:
        p = w[f"p_{src}"].to_numpy()
        for lo, hi in zip(BUCKETS[:-1], BUCKETS[1:]):
            m = (p >= lo) & (p < hi)
            if m.sum() == 0:
                continue
            g = w[m]
            r = {"signal_model": src, "bucket": f"{lo:.2f}-{hi:.2f}", "n": int(m.sum()),
                 "mean_p": round(float(p[m].mean()), 4),
                 "avg_goals": round(float(g["total_goals"].mean()), 3),
                 "avg_home_goals": round(float(g["home_goals"].mean()), 3),
                 "avg_away_goals": round(float(g["away_goals"].mean()), 3),
                 "interpretable": bool(m.sum() >= MIN_CELL)}
            for t in MARKETS:
                r[f"actual_{t}"] = round(float(g[t].mean()), 4)
            rows.append(r)
    return pd.DataFrame(rows)


def stratified_control(w: pd.DataFrame, *, own: str = "over25", other: str = "btts",
                       n_strata: int = 6) -> pd.DataFrame:
    """THE control. Hold the own-model probability roughly fixed; vary the other model's.

    If Over 2.5 really happens more often when BTTS is high EVEN AMONG FIXTURES THE OVER 2.5
    MODEL SCORED THE SAME, then BTTS carries something Over 2.5 does not. If the difference
    collapses once the own-model probability is held still, the apparent relationship was just
    the two models agreeing about the same underlying features.
    """
    d = w.copy()
    d["_own"] = pd.qcut(d[f"p_{own}"], n_strata, labels=False, duplicates="drop")
    rows = []
    for s, g in d.groupby("_own"):
        if len(g) < MIN_CELL * 2:
            continue
        lo_cut, hi_cut = g[f"p_{other}"].quantile([1 / 3, 2 / 3])
        low = g[g[f"p_{other}"] <= lo_cut]
        high = g[g[f"p_{other}"] >= hi_cut]
        if len(low) < MIN_CELL // 2 or len(high) < MIN_CELL // 2:
            continue
        a, b = float(low[own].mean()), float(high[own].mean())
        # Two-proportion z-test on the difference.
        n1, n2 = len(low), len(high)
        pp = (low[own].sum() + high[own].sum()) / (n1 + n2)
        se = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
        z = (b - a) / se if se > 0 else np.nan
        rows.append({"own_model": own, "other_model": other, "stratum": int(s),
                     "own_p_range": f"{g[f'p_{own}'].min():.3f}-{g[f'p_{own}'].max():.3f}",
                     "n_low_other": n1, "n_high_other": n2,
                     f"actual_{own}_low_other": round(a, 4),
                     f"actual_{own}_high_other": round(b, 4),
                     "diff_pp": round((b - a) * 100, 2), "z": round(float(z), 3),
                     "p_value": round(float(2 * (1 - _norm_cdf(abs(z)))), 5)})
    return pd.DataFrame(rows)


def _norm_cdf(x):
    from math import erf, sqrt
    return 0.5 * (1 + erf(x / sqrt(2)))


# ---------------------------------------------------------------------------------------------
# 3. The meta-model -- the only test that actually settles it
# ---------------------------------------------------------------------------------------------

def meta_models(w: pd.DataFrame, *, n_folds: int = 3) -> pd.DataFrame:
    """Own model alone vs own model plus the others, chronologically out of sample.

    Every feature here is a LOGIT of a probability, not the probability. A logistic meta-model on
    raw probabilities has to spend its capacity undoing the sigmoid; on logits, "use the own
    model unchanged" is the trivial solution with coefficient 1 and intercept 0, so anything the
    fit does beyond that is genuinely extra.
    """
    d = w.copy()
    for m in MARKETS:
        d[f"z_{m}"] = _logit(d[f"p_{m}"])
    for extra in ("home_scores", "away_scores", "home_2plus", "away_2plus"):
        if f"p_{extra}" in d.columns:
            d[f"z_{extra}"] = _logit(d[f"p_{extra}"])
    fl = FO.rolling_folds(d, n_folds=n_folds, min_train=3000)
    zoo = FO.model_zoo(fast=True)

    rows = []
    for tgt in MARKETS:
        own = [f"z_{tgt}"]
        others = [f"z_{m}" for m in MARKETS if m != tgt]
        side = [f"z_{x}" for x in ("home_scores", "away_scores", "home_2plus", "away_2plus")
                if f"z_{x}" in d.columns]
        specs = {"own_only": own}
        for m in MARKETS:
            if m != tgt:
                specs[f"own_plus_{m}"] = own + [f"z_{m}"]
        specs["own_plus_all_markets"] = own + others
        specs["own_plus_all_plus_sides"] = own + others + side
        base_ll, base_loss = None, None
        pending = []
        for name, cols in specs.items():
            for mdl in ("logreg", "hgb"):
                oof = E.walk_forward(d, tgt, cols, model=mdl, fold_list=fl, zoo=zoo)
                if oof.empty:
                    continue
                r = E.score(oof, label=f"{tgt}/{name}/{mdl}")
                r.update({"target": tgt, "spec": name, "meta_model": mdl,
                          "n_features": len(cols)})
                if name == "own_only" and mdl == "logreg":
                    base_ll = r["log_loss"]
                    base_loss = _row_logloss(oof)
                pending.append((r, oof))

        # A log-loss delta of 2e-5 is not a small yes, it is noise -- and eyeballing thresholds
        # to decide which is which is exactly what rule 19 warns about. So every spec is compared
        # against its own-model reference with a PAIRED bootstrap on the per-fixture losses,
        # blocked by 8 rows: fixtures on the same matchday share weather, news and referee
        # assignment, and row-independent resampling understates the standard error.
        from src.validation.multiple_testing import paired_bootstrap_p
        for r, oof in pending:
            if base_ll is not None:
                r["d_log_loss"] = r["log_loss"] - base_ll
            if base_loss is not None and r["spec"] != "own_only":
                mine = _row_logloss(oof)
                if len(mine) == len(base_loss):
                    p, obs, ci = paired_bootstrap_p(mine, base_loss, n_boot=2000, block=8)
                    r["paired_p"] = round(float(p), 5)
                    r["paired_diff"] = round(float(obs), 6)
                    r["paired_ci_lo"], r["paired_ci_hi"] = round(ci[0], 6), round(ci[1], 6)
                    # "a is better" means the OTHER spec's loss is higher, so a POSITIVE obs
                    # means the enriched model won. Significant only if the CI excludes zero.
                    r["beats_own_model"] = bool(obs > 0 and ci[0] > 0)
            rows.append(r)
    return pd.DataFrame(rows)


def _row_logloss(oof: pd.DataFrame) -> np.ndarray:
    """Per-fixture log loss, ordered by fixture so two specs line up row for row."""
    g = oof.sort_values("fixture_key", kind="mergesort")
    p = np.clip(g["p"].to_numpy(dtype=float), 1e-15, 1 - 1e-15)
    y = g["y"].to_numpy(dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def likelihood_ratio(w: pd.DataFrame) -> pd.DataFrame:
    """A formal in-sample test to sit beside the OOS one: does adding the other model's logit
    significantly improve the fit, and by how much?

    Reported as a SUPPORTING number only. An in-sample likelihood-ratio test on 26,000 rows will
    call almost anything significant; it is here because a large chi-square with a tiny OOS gain
    is itself informative -- it says the relationship is real but worth nothing.
    """
    from sklearn.linear_model import LogisticRegression
    rows = []
    for tgt in MARKETS:
        y = w[tgt].to_numpy()
        z_own = _logit(w[f"p_{tgt}"]).reshape(-1, 1)
        m0 = LogisticRegression(max_iter=1000).fit(z_own, y)
        ll0 = -M.log_loss(y, m0.predict_proba(z_own)[:, 1]) * len(y)
        for other in MARKETS:
            if other == tgt:
                continue
            X = np.column_stack([z_own.ravel(), _logit(w[f"p_{other}"])])
            m1 = LogisticRegression(max_iter=1000).fit(X, y)
            ll1 = -M.log_loss(y, m1.predict_proba(X)[:, 1]) * len(y)
            stat = 2 * (ll1 - ll0)
            from scipy import stats as st
            rows.append({"target": tgt, "added_model": other, "n": int(len(y)),
                         "lr_chi2": round(float(stat), 2),
                         "p_value": float(st.chi2.sf(max(stat, 0), 1)),
                         "coef_own": round(float(m1.coef_[0][0]), 4),
                         "coef_added": round(float(m1.coef_[0][1]), 4),
                         "in_sample_ll_gain": round(float((ll1 - ll0) / len(y)), 6)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# 4. Agreement, disagreement, and what the scoreline actually looked like
# ---------------------------------------------------------------------------------------------

def agreement(w: pd.DataFrame, *, hi: float = 0.60, lo: float = 0.45) -> pd.DataFrame:
    """Does model agreement produce a more predictable subset? (question 26)"""
    rows = []
    pairs = [(a, b) for i, a in enumerate(MARKETS) for b in MARKETS[i + 1:]]
    for a, b in pairs:
        pa, pb = w[f"p_{a}"].to_numpy(), w[f"p_{b}"].to_numpy()
        states = {"both_high": (pa >= hi) & (pb >= hi), "both_low": (pa <= lo) & (pb <= lo),
                  "a_high_b_low": (pa >= hi) & (pb <= lo),
                  "a_low_b_high": (pa <= lo) & (pb >= hi),
                  "mixed_middle": ~(((pa >= hi) | (pa <= lo)) & ((pb >= hi) | (pb <= lo)))}
        for name, m in states.items():
            if m.sum() < 30:
                continue
            g = w[m]
            r = {"model_a": a, "model_b": b, "state": name, "n": int(m.sum()),
                 "avg_goals": round(float(g["total_goals"].mean()), 3),
                 "interpretable": bool(m.sum() >= MIN_CELL)}
            for t in MARKETS:
                y = g[t].to_numpy()
                p = g[f"p_{t}"].to_numpy()
                base = float(y.mean())
                r[f"actual_{t}"] = round(base, 4)
                r[f"acc_{t}"] = round(float(((p >= 0.5).astype(int) == y).mean()), 4)
                r[f"rock_{t}"] = round(max(base, 1 - base), 4)
                r[f"lift_{t}_pp"] = round((r[f"acc_{t}"] - r[f"rock_{t}"]) * 100, 2)
            rows.append(r)
    return pd.DataFrame(rows)


def goal_distribution(w: pd.DataFrame, *, hi: float = 0.60, lo: float = 0.45) -> pd.DataFrame:
    """Exact goal counts and common scorelines inside each agreement/disagreement state.

    The interesting hypothesis is that "BTTS high + Over 2.5 low" is a 1-1 machine and
    "BTTS low + Over 2.5 high" is a 3-0 machine -- a latent goal distribution that neither
    binary model expresses on its own.
    """
    pa, pb = w["p_btts"].to_numpy(), w["p_over25"].to_numpy()
    states = {"btts_high_ou25_high": (pa >= hi) & (pb >= hi),
              "btts_high_ou25_low": (pa >= hi) & (pb <= lo),
              "btts_low_ou25_high": (pa <= lo) & (pb >= hi),
              "btts_low_ou25_low": (pa <= lo) & (pb <= lo),
              "all": np.ones(len(w), dtype=bool)}
    rows = []
    for name, m in states.items():
        if m.sum() < 30:
            continue
        g = w[m]
        r = {"state": name, "n": int(m.sum()), "avg_goals": round(float(g.total_goals.mean()), 3),
             "interpretable": bool(m.sum() >= MIN_CELL)}
        for k in range(6):
            r[f"goals_{k}{'plus' if k == 5 else ''}"] = round(
                float((np.minimum(g.total_goals, 5) == k).mean()), 4)
        score = g["home_goals"].astype(int).astype(str) + "-" + g["away_goals"].astype(int).astype(str)
        top = score.value_counts(normalize=True).head(5)
        r["top_scores"] = "; ".join(f"{k} {v:.3f}" for k, v in top.items())
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# 5. Discovery -> validation, with multiple-testing control
# ---------------------------------------------------------------------------------------------

def discover_and_validate(w: pd.DataFrame, *, split: float = 0.6) -> pd.DataFrame:
    """Search patterns on the early OOS period, re-measure them on the late one. Rule 20/33.

    Every two-model threshold combination is searched, which is exactly the setting rule 19
    warns about -- hundreds of comparisons guarantee some will look significant. So the discovery
    p-values are Benjamini-Hochberg corrected, and the status that matters is not the p-value but
    whether the validation period reproduced the effect.
    """
    from src.validation.multiple_testing import benjamini_hochberg
    w = w.sort_values("date", kind="mergesort").reset_index(drop=True)
    cut = int(len(w) * split)
    while cut < len(w) and w["date"].iloc[cut] == w["date"].iloc[cut - 1]:
        cut += 1
    disc, val = w.iloc[:cut], w.iloc[cut:]
    rows = []
    grid = (0.45, 0.50, 0.55, 0.60, 0.65)
    for tgt in MARKETS:
        base_d = float(disc[tgt].mean())
        for a in MARKETS:
            for b in MARKETS:
                if a == b or a == tgt:
                    continue
                for ta in grid:
                    for tb in grid:
                        md = (disc[f"p_{a}"] >= ta) & (disc[f"p_{b}"] >= tb)
                        if md.sum() < MIN_CELL:
                            continue
                        rd = float(disc.loc[md, tgt].mean())
                        n = int(md.sum())
                        se = np.sqrt(base_d * (1 - base_d) / n)
                        z = (rd - base_d) / se if se > 0 else np.nan
                        mv = (val[f"p_{a}"] >= ta) & (val[f"p_{b}"] >= tb)
                        rv = float(val.loc[mv, tgt].mean()) if mv.sum() >= MIN_CELL // 2 else np.nan
                        rows.append({
                            "target": tgt, "cond": f"p_{a}>={ta} & p_{b}>={tb}",
                            "n_discovery": n, "rate_discovery": round(rd, 4),
                            "base_discovery": round(base_d, 4),
                            "edge_discovery_pp": round((rd - base_d) * 100, 2),
                            "z_discovery": round(float(z), 3),
                            "p_discovery": float(2 * (1 - _norm_cdf(abs(z)))),
                            "n_validation": int(mv.sum()),
                            "rate_validation": round(rv, 4) if np.isfinite(rv) else np.nan,
                            "base_validation": round(float(val[tgt].mean()), 4),
                            "edge_validation_pp": (round((rv - float(val[tgt].mean())) * 100, 2)
                                                   if np.isfinite(rv) else np.nan)})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    bh = benjamini_hochberg(t["p_discovery"].to_numpy(), q=0.05)
    t["bh_significant"] = bh["significant"].to_numpy() if "significant" in bh.columns else False
    def status(r):
        if not r["bh_significant"]:
            return "DISCOVERY_ONLY"
        if not np.isfinite(r["edge_validation_pp"]):
            return "UNTESTED"
        same_sign = np.sign(r["edge_validation_pp"]) == np.sign(r["edge_discovery_pp"])
        if same_sign and abs(r["edge_validation_pp"]) >= 0.5 * abs(r["edge_discovery_pp"]):
            return "REPLICATED"
        return "FAILED" if not same_sign else "VALIDATED_WEAK"
    t["status"] = t.apply(status, axis=1)
    return t.sort_values("edge_discovery_pp", ascending=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the meta-model tournament")
    a = ap.parse_args()
    out = D.out_dir()
    w = load_wide()
    print(f"[cross] {len(w):,} fixtures with OOS probabilities for all markets  "
          f"{w.date.min().date()}..{w.date.max().date()}")

    cm = cross_matrix(w); cm.to_csv(out / "cross_market_matrix.csv", index=False)
    print("\nSIGNAL MODEL -> ACTUAL OUTCOME (AUC). Diagonal is the model on its own market.")
    piv = cm.pivot(index="signal_model", columns="actual_outcome", values="auc")
    print(piv.to_string())

    pc = prediction_correlation(w); pc.to_csv(out / "prediction_correlation.csv", index=False)
    print("\nHOW ALIKE ARE THE MODELS' OPINIONS (Pearson on probabilities):")
    print(pc.to_string(index=False))

    ec = error_correlation(w); ec.to_csv(out / "error_correlation.csv", index=False)
    print("\nWHEN ONE IS WRONG, IS THE OTHER? (excess over independence, in points)")
    print(ec[["model_a", "model_b", "both_wrong", "both_wrong_if_independent",
              "excess_pp", "phi"]].to_string(index=False))

    co = conditional_outcomes(w); co.to_csv(out / "conditional_outcomes.csv", index=False)
    print("\nCONDITIONAL OUTCOMES -- P(BTTS) bucket vs what actually happened:")
    print(co[co.signal_model == "btts"][
        ["bucket", "n", "mean_p", "actual_btts", "actual_over15", "actual_over25",
         "actual_over35", "avg_goals"]].to_string(index=False))

    strat = pd.concat([stratified_control(w, own=o, other=x)
                       for o in MARKETS for x in MARKETS if o != x], ignore_index=True)
    strat.to_csv(out / "stratified_control.csv", index=False)
    key = strat[(strat.own_model == "over25") & (strat.other_model == "btts")]
    print("\nTHE CONTROL -- within fixtures the OVER 2.5 model scored the same, does a high")
    print("BTTS probability change how often Over 2.5 actually happened?")
    print(key[["own_p_range", "n_low_other", "n_high_other", "actual_over25_low_other",
               "actual_over25_high_other", "diff_pp", "z", "p_value"]].to_string(index=False))

    ag = agreement(w); ag.to_csv(out / "agreement_analysis.csv", index=False)
    gd = goal_distribution(w); gd.to_csv(out / "disagreement_analysis.csv", index=False)
    print("\nGOAL DISTRIBUTION BY AGREEMENT STATE:")
    print(gd[["state", "n", "avg_goals", "goals_0", "goals_1", "goals_2", "goals_3",
              "goals_4", "goals_5plus", "top_scores"]].to_string(index=False))

    lr = likelihood_ratio(w); lr.to_csv(out / "cross_market_lr_tests.csv", index=False)
    dv = discover_and_validate(w); dv.to_csv(out / "cross_market_discoveries.csv", index=False)
    print(f"\nDISCOVERY -> VALIDATION over {len(dv):,} searched conditions:")
    print(dv["status"].value_counts().to_string())

    if not a.quick:
        mm = meta_models(w); mm.to_csv(out / "meta_model_comparison.csv", index=False)
        print("\nMETA-MODEL -- does adding the other models improve FUTURE prediction?")
        for tgt in MARKETS:
            g = mm[(mm.target == tgt) & (mm.meta_model == "logreg")]
            if g.empty:
                continue
            ref = g[g.spec == "own_only"]["log_loss"].iloc[0]
            print(f"  {tgt}: own_only ll={ref:.5f}")
            for _, r in g[g.spec != "own_only"].iterrows():
                print(f"      {r.spec:<28}ll={r.log_loss:.5f}  delta={r.log_loss - ref:+.5f}"
                      f"{'  <-- better' if r.log_loss < ref - 1e-4 else ''}")

    (out / "cross_market_manifest.json").write_text(json.dumps(
        {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "fixtures": int(len(w)),
         "calc_version": CALC_VERSION}, indent=2), encoding="utf-8")
    print(f"\n[cross] wrote artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
