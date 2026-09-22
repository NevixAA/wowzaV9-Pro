"""Can we predict WHICH PLAYERS SCORE -- and does that knowledge flow to the match markets?

    python -m src.prediction_lab.player_goals

TWO QUESTIONS, run as one experiment because they share a dataset.

    (a) Can the player data predict a goalscorer better than the obvious baselines?
    (b) Does player information improve MATCH prediction, and does match information improve
        PLAYER prediction? (rules 11 and 12)

THE ROCK IS NOT THE BASE RATE HERE. Players score in 8.3% of appearances, so "nobody scores"
is 91.7% accurate and utterly useless. The baseline that matters is A PLAYER'S OWN PRIOR SCORING
RATE: strikers score more than full-backs, and a model that merely rediscovers that has learned
nothing. So the comparison ladder is global rate -> position rate -> the player's own history ->
the full model, and only the last gap is a result.

ELIGIBILITY IS THE HARD PART, AND IT IS WHERE THIS KIND OF STUDY USUALLY CHEATS.
`player_history.parquet` is a log of players who APPEARED. It contains no row for a player who
was left out, so "every squad candidate" cannot be reconstructed from it. That matters because
whether a player appears is most of whether he scores, and a model scored only on players who
played has been handed the single most valuable fact for free. Three populations are therefore
reported separately and never pooled:

    appeared        every row. THE APPEARANCE IS NOT KNOWN PRE-MATCH, so this is an explanatory
                    upper bound and is labelled as one. It is not a deployable number.
    started         started == 1. Lineups publish about an hour before kickoff, so this IS
                    knowable pre-match -- but only an hour before, not the morning of.
    exp_minutes_60  selected on the player's OWN PRIOR rolling minutes, not on this match.
                    Fully pre-match, deployable, and the honest headline.

FEATURES ARE REBUILT HERE RATHER THAN REUSED. `player_history` already ships 67 columns named
`*_pg` that look like prior-only per-game rates, and they may well be. "May well be" is not good
enough for a leakage claim, so this module builds its own rolling features with the same
shift-then-roll discipline as the match lab, and separately perturbation-tests v9's precomputed
columns so the answer is measured rather than assumed.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.prediction_lab import data as D
from src.prediction_lab import experiments as E
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M
from src.prediction_lab import run as R

CALC_VERSION = "1.0.0"
WINDOWS = (5, 10)
POPULATIONS = ("appeared", "started", "exp_minutes_60")


def load_players() -> pd.DataFrame:
    for base in ("../v9/player_history.parquet", "player_history.parquet"):
        try:
            d = pd.read_parquet(base)
            break
        except Exception:
            continue
    else:
        raise RuntimeError("player_history.parquet not found")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date", "player_id"])
    for c in ("goals", "minutes", "started", "shots_total", "shots_on_target", "assists",
              "key_passes", "rating", "penalty_scored", "penalty_won"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["scored"] = (d["goals"].fillna(0) > 0).astype(int)
    d["fixture_key"] = (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"].astype(str) + "|"
                        + d["home_team"].astype(str).str.strip() + "|"
                        + d["away_team"].astype(str).str.strip())
    return d.sort_values(["player_id", "date"], kind="mergesort").reset_index(drop=True)


def build_player_features(d: pd.DataFrame) -> pd.DataFrame:
    """Rolling per-player features over HIS OWN PRIOR appearances. Shift first, always."""
    base = ["goals", "minutes", "started", "shots_total", "shots_on_target", "assists",
            "key_passes", "rating"]
    base = [c for c in base if c in d.columns]
    g = d.groupby("player_id", sort=False)
    sh = g[base].shift(1)
    sh["player_id"] = d["player_id"].to_numpy()
    out = pd.DataFrame(index=d.index)
    for w in WINDOWS:
        r = sh.groupby("player_id", sort=False)[base].rolling(w, min_periods=2).mean()
        r.index = r.index.droplevel(0)
        r = r.reindex(d.index)
        for c in base:
            out[f"pl_{c}_r{w}"] = r[c]
    # Career to date: appearances, goals, and goals per appearance. Expanding, shifted.
    out["pl_apps_prior"] = g.cumcount().to_numpy()
    cum_goals = g["goals"].cumsum() - d["goals"].fillna(0)
    out["pl_career_goals"] = cum_goals
    out["pl_career_gpa"] = np.where(out["pl_apps_prior"] > 0,
                                    cum_goals / out["pl_apps_prior"].replace(0, np.nan), np.nan)
    cum_min = g["minutes"].cumsum() - d["minutes"].fillna(0)
    out["pl_career_g_per90"] = np.where(cum_min > 0, cum_goals / (cum_min / 90.0), np.nan)
    out["pl_career_minutes"] = cum_min
    # Scoring rate per 90 over the recent window, the single most natural feature.
    for w in WINDOWS:
        mins = out[f"pl_minutes_r{w}"].replace(0, np.nan)
        out[f"pl_g_per90_r{w}"] = out[f"pl_goals_r{w}"] / (mins / 90.0)
        out[f"pl_sot_per90_r{w}"] = out[f"pl_shots_on_target_r{w}"] / (mins / 90.0)
    out["pl_is_home"] = d["is_home"].astype(float) if "is_home" in d.columns else np.nan
    if "position" in d.columns:
        out["pl_position"] = pd.Categorical(d["position"].astype(str)).codes.astype(float)
    return out


def _position_prior(d: pd.DataFrame) -> pd.Series:
    """Prior scoring rate of the player's POSITION, from strictly earlier dates."""
    t = d[["position", "date", "scored"]].copy()
    t["position"] = t["position"].astype(str)
    per = (t.groupby(["position", "date"])["scored"].agg(s="sum", n="count")
             .reset_index().sort_values("date", kind="mergesort"))
    cs = per.groupby("position", sort=False)[["s", "n"]].cumsum()
    per["prior"] = np.where(cs["n"] - per["n"] > 0,
                            (cs["s"] - per["s"]) / (cs["n"] - per["n"]), np.nan)
    m = d[["position", "date"]].copy()
    m["position"] = m["position"].astype(str)
    out = m.merge(per[["position", "date", "prior"]], on=["position", "date"], how="left")
    out.index = d.index
    return out["prior"]


def population_mask(d: pd.DataFrame, feats: pd.DataFrame, pop: str) -> np.ndarray:
    if pop == "appeared":
        return np.ones(len(d), dtype=bool)
    if pop == "started":
        return (d["started"].fillna(0) > 0).to_numpy()
    if pop == "exp_minutes_60":
        # Selected on PRIOR rolling minutes -- never on this match's minutes.
        return (feats["pl_minutes_r5"].fillna(0) >= 60).to_numpy()
    raise KeyError(pop)


def leakage_check_v9_columns(d: pd.DataFrame, cols: list[str], *, seed: int = 5) -> pd.DataFrame:
    """Do v9's shipped `*_pg` columns survive a future-perturbation test?

    They cannot be rebuilt (they arrive precomputed in the parquet), so this instead asks a
    weaker but still meaningful question: does a column's value on a row CORRELATE with that
    same row's own outcome more than a genuinely prior-only column of the same kind does? A
    prior-only rate has no access to today's goals; one that silently includes the current match
    will show a step change in single-column AUC. Reported, not adjudicated.
    """
    rows = []
    y = d["scored"].to_numpy().astype(float)
    for c in cols:
        x = pd.to_numeric(d[c], errors="coerce").to_numpy()
        m = np.isfinite(x)
        if m.sum() < 500:
            continue
        rows.append({"column": c, "n": int(m.sum()),
                     "auc_vs_own_outcome": round(M.auc(y[m], x[m]), 4),
                     "coverage": round(float(m.mean()), 4)})
    return pd.DataFrame(rows).sort_values("auc_vs_own_outcome", ascending=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-match-link", action="store_true")
    a = ap.parse_args()
    out = D.out_dir()

    d = load_players()
    feats = build_player_features(d)
    d["pos_prior"] = _position_prior(d)
    print(f"[player] {len(d):,} player-match rows, {d.player_id.nunique():,} players, "
          f"{d.date.min().date()}..{d.date.max().date()}")
    print(f"[player] overall scoring rate {d.scored.mean():.4f} -- so 'nobody scores' is "
          f"{1 - d.scored.mean():.1%} accurate and worthless")

    fcols = [c for c in feats.columns]
    work = pd.concat([d[["fixture_key", "date", "league", "player_id", "scored", "pos_prior",
                         "started", "minutes"]], feats], axis=1)
    work["model_type"] = "player"

    rows, oofs = [], {}
    for pop in POPULATIONS:
        m = population_mask(d, feats, pop)
        sub = work[m].sort_values("date", kind="mergesort").reset_index(drop=True)
        if len(sub) < 6000:
            continue
        fl = FO.rolling_folds(sub, n_folds=3, min_train=3000)
        # Baselines, then the model.
        specs = {
            "global_rate": [],
            "position_prior": ["pos_prior"],
            "own_history": ["pl_career_gpa", "pl_apps_prior"],
            "full_player_model": fcols + ["pos_prior"],
        }
        for name, cols in specs.items():
            if not cols:
                y = sub["scored"].to_numpy()
                dates = pd.to_datetime(sub["date"]).to_numpy()
                parts = []
                for f in fl:
                    parts.append(pd.DataFrame({
                        "fixture_key": sub["fixture_key"].to_numpy()[f.test], "date": dates[f.test],
                        "league": sub["league"].to_numpy()[f.test], "model_type": "player",
                        "fold": f.name, "target": "scored", "model": name,
                        "p": float(y[f.train].mean()), "y": y[f.test],
                        "threshold": 0.5, "threshold_bal": 0.5}))
                oof = pd.concat(parts, ignore_index=True)
            else:
                oof = E.walk_forward(sub, "scored", cols, model="hgb", fold_list=fl)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{pop}/{name}")
            r.update({"population": pop, "spec": name, "n_rows_pop": int(m.sum())})
            rows.append(r)
            if name == "full_player_model":
                oofs[pop] = oof
            print(f"  {pop:<16}{name:<20}n={r['n']:>7,} ll={r['log_loss']:.5f} "
                  f"brier={r['brier']:.5f} auc={r['auc']:.4f} base={r['base_rate']:.4f}")

    tab = pd.DataFrame(rows)
    tab.to_csv(out / "player_goalscorer_performance.csv", index=False)

    # v9's shipped prior columns -- do they look prior-only?
    pg = [c for c in d.columns if c.endswith("_pg")][:30]
    lk = leakage_check_v9_columns(d, pg)
    lk.to_csv(out / "player_v9_column_check.csv", index=False)
    print("\n[player] v9 precomputed *_pg columns, single-column AUC against the same row's "
          "own outcome (a prior-only rate should sit near 0.55-0.65, not near 1.0):")
    print(lk.head(8).to_string(index=False))

    if a.skip_match_link or "exp_minutes_60" not in oofs:
        return 0

    # -----------------------------------------------------------------------------------------
    # The two-way link (rules 11 and 12), on the leagues where both datasets exist.
    # -----------------------------------------------------------------------------------------
    match = R.load()
    mkt_oof = pd.read_parquet(out / "oof_probabilities.parquet")
    wide = mkt_oof.pivot_table(index="fixture_key", columns="target", values="p", aggfunc="last")
    wide.columns = [f"p_{c}" for c in wide.columns]

    po = oofs["exp_minutes_60"]
    linked = po[po.fixture_key.isin(set(match.fixture_key))]
    print(f"\n[player] {linked.fixture_key.nunique():,} fixtures carry BOTH player probabilities "
          f"and match probabilities (the leagues where the two warehouses overlap)")
    if linked.fixture_key.nunique() < 400:
        print("[player] too few overlapping fixtures for a meaningful two-way test; stopping here")
        return 0

    # (11) FORWARD: do player signals improve MATCH prediction?
    agg = (linked.groupby("fixture_key")["p"]
                 .agg(max_scorer_p="max", mean_scorer_p="mean", sum_scorer_p="sum",
                      n_players="size")
                 .reset_index())
    top2 = (linked.sort_values("p", ascending=False).groupby("fixture_key")["p"]
                  .apply(lambda s: s.head(2).sum()).rename("top2_scorer_p").reset_index())
    n20 = (linked.assign(hi=lambda x: (x.p >= 0.20).astype(int))
                 .groupby("fixture_key")["hi"].sum().rename("n_above_20pct").reset_index())
    agg = agg.merge(top2, on="fixture_key").merge(n20, on="fixture_key")
    mm = match.merge(agg, on="fixture_key", how="inner").reset_index(drop=True)
    print(f"[player] match-side test frame: {len(mm):,} fixtures")

    pl_cols = ["max_scorer_p", "mean_scorer_p", "sum_scorer_p", "top2_scorer_p",
               "n_players", "n_above_20pct"]
    fwd = []
    if len(mm) >= 1200:
        mfl = FO.rolling_folds(mm, n_folds=3, min_train=600)
        fc = F.feature_columns(mm, F.FOOTBALL_FAMILIES)
        for t in ("btts", "over15", "over25", "over35"):
            for name, cols in (("football_only", fc),
                               ("football_plus_player", fc + pl_cols),
                               ("player_only", F.feature_columns(mm, ("BASE",)) + pl_cols)):
                oof = E.walk_forward(mm, t, cols, model="hgb", fold_list=mfl)
                if oof.empty:
                    continue
                r = E.score(oof, label=f"{t}/{name}")
                r.update({"target": t, "spec": name, "direction": "player_to_match"})
                fwd.append(r)
                print(f"  match<-player  {t:<8}{name:<24}ll={r['log_loss']:.5f} "
                      f"auc={r['auc']:.4f} n={r['n']:,}")

    # (12) REVERSE: do match signals improve PLAYER prediction?
    rev = []
    pl = work[population_mask(d, feats, "exp_minutes_60")].copy()
    pl = pl.merge(wide.reset_index(), on="fixture_key", how="inner")
    pl = pl.sort_values("date", kind="mergesort").reset_index(drop=True)
    mcols = [c for c in pl.columns if c.startswith("p_")]
    print(f"[player] player rows with match probabilities attached: {len(pl):,}")
    if len(pl) >= 6000 and mcols:
        pfl = FO.rolling_folds(pl, n_folds=3, min_train=3000)
        for name, cols in (("player_only", fcols + ["pos_prior"]),
                           ("player_plus_match", fcols + ["pos_prior"] + mcols)):
            oof = E.walk_forward(pl, "scored", cols, model="hgb", fold_list=pfl)
            if oof.empty:
                continue
            r = E.score(oof, label=f"scored/{name}")
            r.update({"target": "scored", "spec": name, "direction": "match_to_player"})
            rev.append(r)
            print(f"  player<-match  {'scored':<8}{name:<24}ll={r['log_loss']:.5f} "
                  f"auc={r['auc']:.4f} n={r['n']:,}")

    inter = pd.DataFrame(fwd + rev)
    if not inter.empty:
        inter.to_csv(out / "player_match_interactions.csv", index=False)
        print(f"\n[player] wrote player_match_interactions.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
