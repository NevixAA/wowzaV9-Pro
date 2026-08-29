"""
Train and evaluate the Dixon-Coles 1X2 model.
=============================================
    python -m src.pipelines.train_1x2 [--test-days 120] [--half-life 180]

WHY THIS EXISTS. `src/combo/dixon_coles.py` was written and then imported by nothing — a model
file with no trainer, no artefact and no evaluation, which looks like a feature and is not one.
The 1X2 legs appearing in bet-builder combos do NOT come from it: they are read off the score
matrix fitted to O1.5/O2.5/O3.5/BTTS, so they are a by-product of the goals model. This trains
the real thing and, more importantly, says how good it is.

CHRONOLOGICAL, PER LEAGUE, NO EXCEPTIONS

Train strictly before a cutoff, score strictly after it. A random split leaks future form into
past predictions through the team ratings, which is the whole reason walk-forward is the house
rule (invariant 6). Leagues are fitted separately because an attack rating is only meaningful
against the opponents actually faced.

WHAT THE NUMBERS CAN AND CANNOT TELL YOU -- READ THIS BEFORE QUOTING THEM

The benchmark here is the LEAGUE BASE RATE: home/draw/away frequencies from the training period,
the best you can do knowing nothing but which league it is. Beating it proves the model has
learned something about teams.

It does NOT prove the model has an edge. That question needs the MARKET, and the market is
available: v9's sharp tracker has been storing h2h prices all along, in output/sharp_history/*.json
-- nested under `opening` and `snapshots[].odds`, which is why a first pass looking for a
top-level `odds_home` found none. 1,093 fixtures across 19 leagues, median 50 snapshots each.

So this evaluates against BOTH: the league base rate (did it learn anything about teams) and the
de-vigged closing market price (does it know anything the market does not). The second is the one
that decides whether a model is worth money -- v11 exists because "the model disagrees with the
book" turned out to be a longshot machine, and a model that loses to the closing line is research
regardless of how far it beats a base rate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.combo import dixon_coles as dc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output"
MODEL_FILE = OUT / "model_1x2.json"
EVAL_FILE = OUT / "model_1x2_eval.csv"

DEFAULT_TEST_DAYS = 120


def _matches() -> pd.DataFrame:
    """One row per fixture, with a scoreline."""
    from src.data import season_store as store
    need = {"home_team", "away_team", "home_goals", "away_goals", "match_date", "league"}
    parts = []
    for t in ("team_match_stats", "settlements_backfill"):
        try:
            d = store.read(t)
        except Exception:                                       # noqa: BLE001
            continue
        if not d.empty and need.issubset(d.columns):
            parts.append(d[list(need)])
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    d["_d"] = pd.to_datetime(d["match_date"], errors="coerce")
    d = d.dropna(subset=["_d", "home_goals", "away_goals"])
    # A team-match table can carry two rows per fixture; one fixture must not be counted twice
    # in a likelihood or it silently doubles its weight.
    return d.drop_duplicates(subset=["_d", "home_team", "away_team"]).sort_values("_d")


def _outcome(hg, ag) -> int:
    return 0 if hg > ag else (1 if hg == ag else 2)


def _market() -> pd.DataFrame:
    """De-vigged CLOSING 1X2 probabilities from v9's sharp tracker.

    The prices are nested -- `opening` and `snapshots[].odds` -- not top level, which is why a
    first look for `odds_home` found none and wrongly concluded no 1X2 odds existed anywhere.
    The LAST snapshot is the closing line, which is the honest thing to be measured against:
    beating an opening price can just mean being slower than the market.

    De-vigged by normalising the three implied probabilities to sum to 1 (the proportional
    method). Cruder than the power method v11 uses, and it is applied to BOTH sides of the
    comparison in the sense that the market is only ever compared with itself here, so the choice
    cannot flatter the model.
    """
    import glob
    import os
    roots = [os.getenv("V9_LOCAL", ""), str(ROOT / "_v9"), str(ROOT.parent / "v9")]
    files: list[str] = []
    for r in roots:
        if r and Path(r).exists():
            files = sorted(glob.glob(str(Path(r) / "output" / "sharp_history" / "*.json")))
            if files:
                break
    rows = []
    for f in files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for v in (d.values() if isinstance(d, dict) else d):
            for s in (v if isinstance(v, list) else [v]):
                if not isinstance(s, dict) or s.get("market") != "h2h":
                    continue
                snaps = s.get("snapshots") or []
                close = (snaps[-1].get("odds") if snaps else None) or s.get("opening") or {}
                oh, od, oa = (close.get("odds_home"), close.get("odds_draw"),
                              close.get("odds_away"))
                if not (oh and od and oa):
                    continue
                inv = np.array([1 / float(oh), 1 / float(od), 1 / float(oa)])
                rows.append({"home_team": s.get("home"), "away_team": s.get("away"),
                             "_d": pd.to_datetime(str(s.get("date"))[:10], errors="coerce"),
                             "m_home": inv[0] / inv.sum(), "m_draw": inv[1] / inv.sum(),
                             "m_away": inv[2] / inv.sum(), "overround": float(inv.sum())})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-days", type=int, default=DEFAULT_TEST_DAYS)
    ap.add_argument("--half-life", type=float, default=dc.HALF_LIFE_DAYS)
    args = ap.parse_args()

    d = _matches()
    if d.empty:
        print("[1x2] no match data with scorelines — nothing to train")
        return 1
    cutoff = d["_d"].max() - pd.Timedelta(days=args.test_days)
    print(f"[1x2] {len(d):,} fixtures {d['_d'].min():%Y-%m-%d}..{d['_d'].max():%Y-%m-%d}; "
          f"train < {cutoff:%Y-%m-%d} < test")

    mkt = _market()
    print(f"[1x2] market: {len(mkt):,} fixtures with a de-vigged closing 1X2 price")
    models, rows, skipped, preds = {}, [], {}, []
    for lg, g in d.groupby("league"):
        tr, te = g[g["_d"] < cutoff], g[g["_d"] >= cutoff]
        if len(tr) < dc.MIN_MATCHES_PER_LEAGUE:
            skipped[lg] = f"only {len(tr)} training matches"
            continue
        m = dc.fit_league(tr, half_life=args.half_life)
        if m is None:
            skipped[lg] = "fit returned None"
            continue
        models[lg] = m
        if te.empty:
            continue
        # The benchmark: what you would say knowing only the league. Taken from TRAIN so it is
        # not itself peeking at the test period.
        base = np.array([
            float((tr["home_goals"] > tr["away_goals"]).mean()),
            float((tr["home_goals"] == tr["away_goals"]).mean()),
            float((tr["home_goals"] < tr["away_goals"]).mean())])
        P, B, Y = [], [], []
        for _, r in te.iterrows():
            pr = dc.predict(m, str(r["home_team"]), str(r["away_team"]))
            if not pr:
                continue                       # a team unseen in training has no rating
            P.append([pr["p_home"], pr["p_draw"], pr["p_away"]])
            B.append(base)
            Y.append(_outcome(r["home_goals"], r["away_goals"]))
            preds.append({"league": lg, "home_team": r["home_team"],
                          "away_team": r["away_team"], "_d": r["_d"],
                          "p_home": pr["p_home"], "p_draw": pr["p_draw"],
                          "p_away": pr["p_away"], "y": Y[-1]})
        if len(P) < 30:
            skipped[lg] = f"only {len(P)} scoreable test matches"
            continue
        P, B, Y = np.array(P), np.array(B), np.array(Y)
        rows.append({
            "league": lg, "train_matches": len(tr), "test_matches": len(P),
            "converged": m["converged"], "home_adv": round(m["home_adv"], 4),
            "rho": round(m["rho"], 4),
            "logloss": round(dc.multiclass_logloss(P, Y), 4),
            "logloss_baseline": round(dc.multiclass_logloss(B, Y), 4),
            "brier": round(dc.multiclass_brier(P, Y), 4),
            "brier_baseline": round(dc.multiclass_brier(B, Y), 4),
            "rps": round(dc.rps(P, Y), 4),
            "rps_baseline": round(dc.rps(B, Y), 4),
            "accuracy": round(float((P.argmax(1) == Y).mean()), 4),
            "accuracy_baseline": round(float((B.argmax(1) == Y).mean()), 4),
        })


    # ── THE TEST THAT ACTUALLY DECIDES ANYTHING ───────────────────────────────
    # Beating a base rate says the model learned about teams. Beating the CLOSING PRICE says it
    # knows something the market does not, and only the second is worth money. Reported even
    # when it is unflattering — especially then.
    mrep = {"joined": 0, "note": "no market rows"}
    if preds and not mkt.empty:
        pf = pd.DataFrame(preds)
        pf["_d"] = pd.to_datetime(pf["_d"]).dt.normalize()
        mk = mkt.dropna(subset=["_d"]).copy()
        mk["_d"] = mk["_d"].dt.normalize()
        mk = mk.drop_duplicates(subset=["_d", "home_team", "away_team"])
        j = pf.merge(mk, on=["_d", "home_team", "away_team"], how="inner")
        # Club names differ between sources (invariant 11), so the join rate is REPORTED rather
        # than assumed. A low rate means the comparison rests on a biased subset, not that the
        # market is unavailable.
        mrep = {"joined": len(j), "of_predictions": len(pf),
                "join_rate_pct": round(100.0 * len(j) / max(len(pf), 1), 1)}
        if len(j) >= 30:
            Pm = j[["p_home", "p_draw", "p_away"]].to_numpy()
            Mm = j[["m_home", "m_draw", "m_away"]].to_numpy()
            Yj = j["y"].to_numpy()
            mrep.update({
                "model_logloss": round(dc.multiclass_logloss(Pm, Yj), 4),
                "market_logloss": round(dc.multiclass_logloss(Mm, Yj), 4),
                "model_rps": round(dc.rps(Pm, Yj), 4),
                "market_rps": round(dc.rps(Mm, Yj), 4),
                "mean_overround": round(float(j["overround"].mean()), 4),
            })
            # A 50/50 blend: if the model carries information the market lacks, mixing beats both.
            Bl = (Pm + Mm) / 2.0
            mrep["blend_logloss"] = round(dc.multiclass_logloss(Bl, Yj), 4)
            mrep["model_beats_market"] = bool(mrep["model_logloss"] < mrep["market_logloss"])
            mrep["blend_beats_market"] = bool(mrep["blend_logloss"] < mrep["market_logloss"])
        else:
            mrep["note"] = f"only {len(j)} joined fixtures — too few to conclude anything"
    print(f"[1x2] MARKET TEST: {mrep}")

    if not rows:
        print(f"[1x2] nothing evaluable. skipped: {skipped}")
        return 1
    ev = pd.DataFrame(rows).sort_values("test_matches", ascending=False)
    ev["logloss_gain"] = (ev["logloss_baseline"] - ev["logloss"]).round(4)
    ev["beats_baseline"] = ev["logloss_gain"] > 0

    OUT.mkdir(exist_ok=True)
    ev.to_csv(EVAL_FILE, index=False, encoding="utf-8")
    MODEL_FILE.write_text(json.dumps(
        {"trained_at_cutoff": str(cutoff.date()), "half_life_days": args.half_life,
         "calc_version": dc.CALC_VERSION, "leagues": models,
         "market_benchmark": mrep,
         "skipped": skipped}, indent=2, sort_keys=True, default=float), encoding="utf-8")

    n = len(ev)
    beat = int(ev["beats_baseline"].sum())
    tot = ev["test_matches"].sum()
    wl = float((ev["logloss"] * ev["test_matches"]).sum() / tot)
    wb = float((ev["logloss_baseline"] * ev["test_matches"]).sum() / tot)
    print(f"\n[1x2] {n} leagues, {tot:,} out-of-sample matches")
    print(f"[1x2]   log-loss {wl:.4f} vs base rate {wb:.4f}  "
          f"({100*(wb-wl)/wb:+.1f}%)   beats baseline in {beat}/{n} leagues")
    print(f"[1x2]   accuracy {float((ev['accuracy']*ev['test_matches']).sum()/tot):.3f} "
          f"vs {float((ev['accuracy_baseline']*ev['test_matches']).sum()/tot):.3f}")
    if skipped:
        print(f"[1x2]   skipped {len(skipped)} league(s): "
              f"{list(skipped.items())[:3]}{' ...' if len(skipped) > 3 else ''}")
    # Said every time the model is trained, so no one quotes the gain as an edge.
    print("[1x2] NOTE: beating the base rate means it learned about teams. Whether it beats "
          "the CLOSING PRICE is the market test above — that is the number that decides whether "
          "this is worth money.")
    print(f"[1x2] wrote {MODEL_FILE.name} and {EVAL_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
