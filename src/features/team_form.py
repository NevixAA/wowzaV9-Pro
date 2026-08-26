"""
Rolling per-team form from real match statistics — opponent-adjusted, leakage-free.
==================================================================================
WHY THIS EXISTS. v9's per-team lambda is `home_scored_last5` — a team's own scoring rate, with no
reference to who it is playing. A side averaging 2.0 goals gets the same lambda against the best
defence in the division as against the worst. `feature_engineering` then multiplies attack and
defence *strength* indices, but the inputs behind those were measured empty on the live board
(`home_xg_last5` 0%, `home_possession_last5` 0%, `home_insidebox_last5` 0%) and missing features
are median-imputed, so the multiplication was of two league averages.

`team_match_stats` now holds the real per-fixture statistics. This module turns them into what a
distribution model actually needs:

    lam_home = (home attack rate / league mean) x (away defence rate / league mean) x league mean

That is the standard Dixon-Coles style decomposition, and it is the thing v9 never had inputs for.

TWO CORRECTNESS PROPERTIES THAT MATTER MORE THAN THE ARITHMETIC

**1. No leakage.** A team's form for fixture N uses fixtures 1..N-1 and never N itself. Computed
with `groupby().shift(1).rolling()` so the current match cannot enter its own features. Getting
this wrong produces a model that looks excellent in backtest and fails live, and it is invisible
unless you look for it — which is why `scripts/leakage_audit.py` exists at the repo root.

**2. Missing inputs stay NaN.** xG is present for 16 of 22 leagues and only from ~2024 onward
(season 2023 is largely empty: League One, League Two, Serie B, La Liga 2 and Bundesliga 2 all
0%). Where xG is absent this falls back to GOALS and records which source was used in
`xg_source`, rather than substituting a league average and pretending the input existed. Root
CLAUDE.md invariant 9: write NaN, never an invented number.

The fallback is honest but not equivalent — goals are a noisier estimate of scoring rate than xG,
which is the entire reason xG is worth collecting. Any evaluation that pools the two must
condition on `xg_source`, or it measures a mixture and attributes the result to the wrong input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = 6           # matches on which form is computed
MIN_PRIOR = 3        # below this a team's form is NaN rather than a noisy one- or two-game mean

# Per-team metrics rolled forward. `for` = created by the team, `against` = conceded by it.
METRICS = ("xg", "goals", "shots", "sot", "insidebox", "possession")


def _to_team_rows(d: pd.DataFrame) -> pd.DataFrame:
    """One row per (fixture, team) with `for_*` / `against_*`, from home_/away_ columns.

    A per-team view is required before any rolling window: a team's last six matches are a mix of
    home and away fixtures, and rolling the home_ columns alone would compute "form at home",
    which is a different quantity and would silently halve every window.
    """
    frames = []
    for side, opp in (("home", "away"), ("away", "home")):
        blk = pd.DataFrame({
            "fixture_id": d["fixture_id"],
            "league": d["league"],
            "season": d["season"],
            "match_date": pd.to_datetime(d["match_date"], errors="coerce"),
            "team": d[f"{side}_team"],
            "opponent": d[f"{opp}_team"],
            "is_home": side == "home",
        })
        for m in METRICS:
            blk[f"for_{m}"] = pd.to_numeric(d.get(f"{side}_{m}"), errors="coerce")
            blk[f"against_{m}"] = pd.to_numeric(d.get(f"{opp}_{m}"), errors="coerce")
        frames.append(blk)
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=["match_date", "team"]).sort_values(["team", "match_date"])


def rolling_form(stats: pd.DataFrame, window: int = WINDOW,
                 min_prior: int = MIN_PRIOR) -> pd.DataFrame:
    """Per (fixture, team) rolling form over the team's PRIOR `window` matches."""
    t = _to_team_rows(stats).reset_index(drop=True)
    g = t.groupby("team", sort=False)
    for m in METRICS:
        for direction in ("for", "against"):
            col = f"{direction}_{m}"
            # ONE transform per team: shift(1) so the current match cannot enter its own feature,
            # then roll WITHIN the group.
            #
            # The first version was
            #     g[col].shift(1).rolling(w).mean().reset_index(level=0, drop=True)
            # and it was wrong twice over. `g[col].shift(1)` returns a Series on the ORIGINAL
            # index, so the subsequent `.rolling()` ran across the whole frame and mixed one
            # team's last matches into the next team's first. Worse, `reset_index(level=0,
            # drop=True)` on a single-level index REPLACES it with a RangeIndex, so assigning back
            # to `t` aligned on the wrong index and scattered values onto unrelated rows.
            #
            # The symptom was a correlation of -0.0009 between a team's prior six-match scoring
            # rate and what it scored next — suspiciously EXACT zero, which is what misalignment
            # looks like and what absence of signal does not. My leakage test passed because it
            # used a single team and a clean index, so neither defect could show.
            t[f"roll_{col}"] = g[col].transform(
                lambda s: s.shift(1).rolling(window, min_periods=min_prior).mean())
    t["n_prior"] = g.cumcount()
    return t


def league_means(stats: pd.DataFrame) -> pd.DataFrame:
    """Per (league, season) mean goals and xG PER SIDE.

    Per side, not per match. The distinction is the one place this arithmetic is easy to get
    wrong by a factor of two, and doubling every lambda pushes every BTTS probability toward 1.
    """
    t = _to_team_rows(stats)
    return (t.groupby(["league", "season"])
            .agg(lg_goals=("for_goals", "mean"), lg_xg=("for_xg", "mean"))
            .reset_index())


def fixture_lambdas(stats: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """One row per fixture with opponent-adjusted lam_home / lam_away.

        lam_home = (home attack / lg) x (away defence / lg) x lg

    `xg_source` records whether xG or goals were used, per fixture, so an evaluation can condition
    on it instead of pooling two different estimators.
    """
    form = rolling_form(stats, window=window)
    lg = league_means(stats)

    keep = ["fixture_id", "team", "is_home", "league", "season", "match_date", "n_prior",
            "roll_for_xg", "roll_against_xg", "roll_for_goals", "roll_against_goals",
            "roll_for_shots", "roll_for_sot", "roll_for_possession", "roll_for_insidebox"]
    f = form[keep]
    home = f[f["is_home"]].drop(columns="is_home").add_prefix("h_")
    away = f[~f["is_home"]].drop(columns="is_home").add_prefix("a_")
    d = home.merge(away, left_on="h_fixture_id", right_on="a_fixture_id", how="inner")
    d = d.rename(columns={"h_fixture_id": "fixture_id", "h_league": "league",
                          "h_season": "season", "h_match_date": "match_date"})
    d = d.merge(lg, on=["league", "season"], how="left")

    # xG where both sides have it, else goals. Never a substituted league average.
    use_xg = (d["h_roll_for_xg"].notna() & d["h_roll_against_xg"].notna()
              & d["a_roll_for_xg"].notna() & d["a_roll_against_xg"].notna()
              & d["lg_xg"].notna() & d["lg_xg"].gt(0))
    d["xg_source"] = np.where(use_xg, "xg", "goals")

    h_att = np.where(use_xg, d["h_roll_for_xg"], d["h_roll_for_goals"])
    h_def = np.where(use_xg, d["h_roll_against_xg"], d["h_roll_against_goals"])
    a_att = np.where(use_xg, d["a_roll_for_xg"], d["a_roll_for_goals"])
    a_def = np.where(use_xg, d["a_roll_against_xg"], d["a_roll_against_goals"])
    base = np.where(use_xg, d["lg_xg"], d["lg_goals"])

    with np.errstate(divide="ignore", invalid="ignore"):
        d["lam_home"] = (h_att / base) * (a_def / base) * base
        d["lam_away"] = (a_att / base) * (h_def / base) * base
    for c in ("lam_home", "lam_away"):
        v = pd.to_numeric(d[c], errors="coerce")
        d[c] = v.where(np.isfinite(v)).clip(lower=0.05, upper=6.0)

    d["lam_min"] = d[["lam_home", "lam_away"]].min(axis=1)
    d["lam_sum"] = d["lam_home"] + d["lam_away"]
    d["lam_asymmetry"] = ((d["lam_home"] - d["lam_away"]).abs()
                          / d["lam_sum"].replace(0, np.nan))
    d["league_base_per_side"] = base
    return d


def coverage(stats: pd.DataFrame) -> dict:
    """What fraction of fixtures can get a real lambda, and from which estimator."""
    d = fixture_lambdas(stats)
    ok = d["lam_home"].notna() & d["lam_away"].notna()
    return {
        "fixtures": int(len(d)),
        "with_lambdas": int(ok.sum()),
        "pct_with_lambdas": round(float(ok.mean()), 4) if len(d) else 0.0,
        "from_xg": int((d["xg_source"] == "xg").sum()),
        "from_goals": int((d["xg_source"] == "goals").sum()),
        "pct_from_xg": round(float((d["xg_source"] == "xg").mean()), 4) if len(d) else 0.0,
    }
