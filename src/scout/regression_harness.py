"""Existing-league regression harness: does adding a new league HURT the leagues Wowza already has?

    python -m src.scout.regression_harness --league-id 129      # -> output/scout/regression/<id>.json + .md

WHY. v9's new-format model is ONE global model. Onboarding a league adds its matches to the training
set of every new-format league's model, so a league can be perfectly good on its own and still make
the model worse for MLS, Brazil or Japan. Weekly promotion (src/scout/promotion.py) therefore stops a
passing league at SHADOW_APPROVED until this test has run (owner OK 2026-10-14 to build it).

HOW (fixed before any result, 2026-10-14):
  * existing leagues = v9's new-format leagues in Pro's leak-free prediction-lab dataset (v9's own
    fd_history + af_history); candidate = the scout's finished results for that league;
  * one chronological cut: the 80th-percentile date of the existing leagues. Holdout = existing-league
    fixtures on/after the cut. The candidate NEVER appears in the holdout;
  * CHAMPION trains on existing fixtures before the cut; CHALLENGER trains on the same rows PLUS the
    candidate's fixtures before the cut. Same features, same recipe, same seed - the only difference
    is the candidate's rows;
  * features: goals-only families (BASE, FORM, STRENGTH, REST, H2H) - what a new-format league has;
    candidate team names are prefixed so a club name shared across countries never merges histories;
  * recipe: a REPLICA of v9's team recipe (StandardScaler + LogisticRegression C=0.5, and
    GradientBoosting 300 x depth 4, lr 0.05, subsample 0.8, min leaf 20; Platt on the last 15% of
    training; members averaged). Pro cannot import v9's src/model.py (both repos own a top-level
    `config`), so the replica is stated, not hidden; v9's LightGBM member and meta blend are omitted.
  * targets: over25 (the main market) and btts.

RULE:
  INSUFFICIENT_CANDIDATE_HISTORY  candidate has < 300 fixtures before the cut
  FAIL   pooled holdout delta (challenger - champion log loss) 90% CI upper > +0.002, OR any existing
         league with >= 150 holdout fixtures that is significantly worse at a BONFERRONI-corrected
         one-sided 5% level (lower bound at quantile 0.05 / number of leagues tested)
  PASS   otherwise, for BOTH targets
The CI is a bootstrap over whole match days.

AMENDED 2026-10-14, after the first run (league 129) and before any league was decided by it: the
per-league check originally used an uncorrected 90% CI per league. With ~15 leagues x 2 targets that
is ~30 one-sided 5% tests, so a perfectly harmless league would fail ~75-80% of the time by chance.
That is a design error independent of any result, so it was corrected (Bonferroni) and a SEED CONTROL
was added: the champion recipe refitted with a different random seed, scored the same way. It
measures pure fitting noise; it is reported next to every verdict so a "harm" can be compared to it. PASS does not open a PR or change v9; it moves the
promotion route to REGRESSION_PASSED, and v9 onboarding stays an owner decision.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

REGISTERED_ON = "2026-10-14"
TARGETS = ("over25", "btts")
FAMILIES = ("BASE", "FORM", "STRENGTH", "REST", "H2H")
CUT_QUANTILE = 0.80
MIN_CANDIDATE_ROWS = 300
POOLED_MARGIN = 0.002
LEAGUE_MIN_N = 150
OUT = cfg.OUTPUT_DIR / "scout" / "regression"


def candidate_frame(league_id: int) -> pd.DataFrame:
    """The candidate's finished matches, shaped like prediction_lab.data.load_fixtures()."""
    from src.prediction_lab import data as D
    from src.scout.collect import _results
    r = _results()
    r = r[(r["league_id"].astype(int) == int(league_id)) & r["status"].isin(["FT", "AET", "PEN"])].copy()
    if r.empty:
        return pd.DataFrame()
    r = r.drop_duplicates("fixture_id", keep="last")
    lg = f"scout:{int(league_id)}"
    d = pd.DataFrame({
        "date": pd.to_datetime(r["match_date"].astype(str).str[:10], errors="coerce"),
        "league": lg, "season": r["season"].astype(str),
        "home_team": "c|" + D._norm_team(r["home_team"]), "away_team": "c|" + D._norm_team(r["away_team"]),
        "home_goals": pd.to_numeric(r["home_goals"], errors="coerce"),
        "away_goals": pd.to_numeric(r["away_goals"], errors="coerce"),
        "ht_home_goals": pd.to_numeric(r.get("ht_home"), errors="coerce"),
        "ht_away_goals": pd.to_numeric(r.get("ht_away"), errors="coerce"),
    }).dropna(subset=["date", "home_goals", "away_goals"])
    d["fixture_key"] = d["date"].dt.strftime("%Y-%m-%d") + "|" + lg + "|" + d["home_team"] + "|" + d["away_team"]
    d["model_type"] = "new_format"
    d["season_label"] = D._season_label(d["date"])
    return D._attach_targets(d.reset_index(drop=True))


def _fit_predict(Xtr: pd.DataFrame, ytr: np.ndarray, Xte: pd.DataFrame, seed: int = 42) -> np.ndarray:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    med = Xtr.median().fillna(0.0)
    Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)                     # train medians only
    cut = int(len(Xtr) * 0.85)
    preds = []
    for clf in (LogisticRegression(max_iter=2000, C=0.5, solver="lbfgs"),
                GradientBoostingClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                                           subsample=0.8, min_samples_leaf=20, random_state=seed)):
        pipe = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
        pipe.fit(Xtr.iloc[:cut], ytr[:cut])
        platt = LogisticRegression(C=1.0, max_iter=1000)
        platt.fit(pipe.predict_proba(Xtr.iloc[cut:])[:, 1].reshape(-1, 1), ytr[cut:])
        preds.append(np.clip(platt.predict_proba(pipe.predict_proba(Xte)[:, 1].reshape(-1, 1))[:, 1], 0.001, 0.999))
    return np.mean(preds, axis=0)


def run(league_id: int, *, existing: pd.DataFrame | None = None) -> dict:
    from src.prediction_lab import data as D
    from src.prediction_lab import features as F
    from src.studies.common import block_ci, logloss
    if existing is None:
        fx = D.load_fixtures()
        existing = fx[fx["model_type"] == "new_format"].reset_index(drop=True)
    cand = candidate_frame(league_id)
    cut = existing["date"].quantile(CUT_QUANTILE).normalize()
    res = {"league_id": int(league_id), "registered_on": REGISTERED_ON, "cut_date": str(cut.date()),
           "existing_leagues": int(existing["league"].nunique()), "candidate_rows_total": int(len(cand)),
           "candidate_rows_before_cut": int((cand["date"] < cut).sum()) if len(cand) else 0,
           "recipe": "replica of v9 team recipe (LR C=0.5 + GB 300x4, Platt last 15%, mean); goals-only families",
           "targets": {}}
    if res["candidate_rows_before_cut"] < MIN_CANDIDATE_ROWS:
        res["verdict"] = "INSUFFICIENT_CANDIDATE_HISTORY"
        return res
    allf = F.build(pd.concat([existing, cand], ignore_index=True))
    cols = F.feature_columns(allf, FAMILIES)
    is_cand = allf["league"].astype(str).str.startswith("scout:")
    train_a = allf[~is_cand & (allf["date"] < cut)]
    train_b = allf[allf["date"] < cut].sort_values("date", kind="mergesort")
    hold = allf[~is_cand & (allf["date"] >= cut)]
    train_a = train_a.sort_values("date", kind="mergesort")
    verdicts = []
    day = hold["date"].dt.strftime("%Y-%m-%d").to_numpy()
    groups = {lg: hold.index.get_indexer(idx) for lg, idx in hold.groupby("league").groups.items()}
    n_tested = sum(1 for m in groups.values() if len(m) >= LEAGUE_MIN_N) or 1
    q_lo = 0.05 / n_tested                                           # Bonferroni, one-sided 5%

    def _per_league(diff):
        per = []
        for lg, m in groups.items():
            ci = block_ci(diff[m], day[m]) if len(m) >= 30 else [None, None]
            lo = block_ci(diff[m], day[m], q=(q_lo, 1 - q_lo))[0] if len(m) >= LEAGUE_MIN_N else None
            per.append({"league": lg, "n": int(len(m)), "delta": round(float(diff[m].mean()), 5), "ci90": ci,
                        "bonferroni_lower": lo, "significantly_worse": bool(lo is not None and lo > 0)})
        return per

    for t in TARGETS:
        y = hold[t].to_numpy()
        pa = _fit_predict(train_a[cols], train_a[t].to_numpy(), hold[cols])
        pb = _fit_predict(train_b[cols], train_b[t].to_numpy(), hold[cols])
        ps = _fit_predict(train_a[cols], train_a[t].to_numpy(), hold[cols], seed=43)   # seed control
        diff = logloss(pb, y) - logloss(pa, y)                       # + = challenger worse
        noise = logloss(ps, y) - logloss(pa, y)
        pooled_ci = block_ci(diff, day)
        per = _per_league(diff)
        noise_per = _per_league(noise)
        worse = [p["league"] for p in per if p["significantly_worse"]]
        fail = (pooled_ci[1] is not None and pooled_ci[1] > POOLED_MARGIN) or bool(worse)
        verdicts.append("FAIL" if fail else "PASS")
        res["targets"][t] = {"n_holdout": int(len(y)), "logloss_champion": round(float(logloss(pa, y).mean()), 5),
                             "logloss_challenger": round(float(logloss(pb, y).mean()), 5),
                             "pooled_delta": round(float(diff.mean()), 5), "pooled_ci90": pooled_ci,
                             "leagues_significantly_worse": worse, "per_league": per,
                             "bonferroni_quantile": round(q_lo, 5),
                             "seed_control": {"pooled_delta": round(float(noise.mean()), 5),
                                              "pooled_ci90": block_ci(noise, day),
                                              "mean_abs_league_delta": round(float(np.mean([abs(p["delta"]) for p in noise_per])), 5),
                                              "leagues_flagged": [p["league"] for p in noise_per if p["significantly_worse"]]},
                             "verdict": verdicts[-1]}
    res["verdict"] = "PASS" if all(v == "PASS" for v in verdicts) else "FAIL"
    return res


def to_md(r: dict) -> str:
    L = [f"# Existing-league regression — candidate league {r['league_id']}", "",
         f"Rule registered {r['registered_on']} (module docstring). Cut {r['cut_date']}; "
         f"{r['existing_leagues']} existing new-format leagues; candidate rows before the cut "
         f"{r['candidate_rows_before_cut']:,}. Recipe: {r['recipe']}.", "",
         f"**Verdict: {r['verdict']}**", ""]
    for t, x in r.get("targets", {}).items():
        L += [f"## {t} — {x['verdict']}",
              f"Holdout {x['n_holdout']:,} existing-league fixtures. Log loss champion {x['logloss_champion']} · "
              f"with candidate {x['logloss_challenger']} · Δ {x['pooled_delta']:+.5f}, 90% CI {x['pooled_ci90']} "
              f"(fail if upper > +{POOLED_MARGIN}).", "",
              f"Seed control (champion vs itself, other seed = pure noise): Δ {x['seed_control']['pooled_delta']:+.5f}, "
              f"mean |league Δ| {x['seed_control']['mean_abs_league_delta']}, leagues flagged "
              f"{x['seed_control']['leagues_flagged'] or 'none'}.", "",
              "| League | n | Δ log loss | 90% CI | Bonferroni lower | Significantly worse |", "|---|---|---|---|---|---|"]
        L += [f"| {p['league']} | {p['n']} | {p['delta']:+.5f} | {p['ci90']} | {p['bonferroni_lower']} | "
              f"{'YES' if p['significantly_worse'] else ''} |"
              for p in sorted(x["per_league"], key=lambda p: -p["n"])]
        L.append("")
    L.append("PASS opens no PR and changes no v9 config; onboarding stays an owner decision.")
    return "\n".join(L) + "\n"


def save(r: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{r['league_id']}.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / f"{r['league_id']}.md").write_text(to_md(r), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league-id", type=int, required=True)
    a = ap.parse_args()
    r = run(a.league_id)
    save(r)
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
