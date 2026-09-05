"""
Tournament model for UCL / UEL / UECL.
======================================
    python -m src.pipelines.tourney --mode evaluate   # does cross-league calibration help?
    python -m src.pipelines.tourney --mode predict    # price upcoming European ties
    python -m src.pipelines.tourney --mode all

WHAT IT IS. Not a new goals model — the missing SCALE between the ones we have. Domestic
Dixon-Coles fits pin mean attack to zero inside each league, so a rating is comparable within a
competition and meaningless across one. A European tie is precisely the case that breaks, and
`src/combo/league_strength.py` supplies the per-league offset that makes the two sides comparable.

WHAT DRIVES IT. Current domestic form, not tournament history. Clubs from different leagues meet
twice a decade with turned-over squads, so a "past European record" feature is mostly noise about
different teams. Each side is rated from how it is playing in its OWN league now; the strength
term says how hard that league is.

IT IS RESEARCH UNTIL IT BEATS THE NULL. `--mode evaluate` fits on earlier ties and scores later
ones against the honest null of no calibration at all (s = 0, i.e. using domestic ratings
naively). If the calibrated model does not beat that out of sample, it carries no information and
must not be tiered or bet — the same bar the 1X2 model was held to, and failed.

DATA IT NEEDS, AND WHY IT MAY REPORT THAT IT HAS NONE. Both sides of a tie need domestic form.
v9's config gained 17 top divisions on 2026-09-05 for exactly this reason: before that, UEFA
clubs had ~15% coverage because we collected second divisions while they play top-flight. That
backfill runs through pro_team_stats, so until it completes this pipeline will honestly report
too few rated ties rather than fitting on a handful and pretending.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from src.combo import dixon_coles as dc
from src.combo import league_strength as ls

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output"
CAL_FILE = OUT / "tourney_calibration.json"
PRED_FILE = OUT / "tourney_predictions.csv"

TOURNAMENTS = ("Champions League", "Europa League", "Conference League")


def _history(extra: str = "") -> pd.DataFrame:
    from src.data import season_store as store
    need = {"home_team", "away_team", "home_goals", "away_goals", "match_date", "league"}
    parts = []
    for t in ("team_match_stats", "settlements_backfill"):
        try:
            d = store.read(t)
        except Exception:                                        # noqa: BLE001
            continue
        if not d.empty and need.issubset(d.columns):
            parts.append(d[list(need)])
    if extra:
        import glob
        for f in glob.glob(extra, recursive=True):
            try:
                e = pd.read_parquet(f)
            except Exception:                                    # noqa: BLE001
                continue
            if need.issubset(e.columns):
                parts.append(e[list(need)])
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    # dixon_coles.fit_league reads `_d` for its time-decay weights, not `match_date`.
    d["_d"] = d["match_date"]
    d = d.dropna(subset=["match_date", "home_goals", "away_goals"])
    return d.drop_duplicates(subset=["match_date", "home_team", "away_team"]).sort_values(
        "match_date")


def _domestic_models(d: pd.DataFrame) -> tuple[dict, dict]:
    """Per-league Dixon-Coles fits, and each club's domestic league."""
    dom = d[~d["league"].isin(TOURNAMENTS)]
    models, home_of = {}, {}
    for lg, g in dom.groupby("league"):
        if len(g) < dc.MIN_MATCHES_PER_LEAGUE:
            continue
        m = dc.fit_league(g)
        if m is None:
            continue
        models[lg] = m
        for t in m["teams"]:
            # A club is rated by the league it plays MOST in — a guard against a club appearing
            # once in a neighbouring competition and being mis-assigned.
            home_of.setdefault(t, lg)
    return models, home_of


def _ties(d: pd.DataFrame, home_of: dict) -> pd.DataFrame:
    """European fixtures, tagged with each side's domestic league."""
    t = d[d["league"].isin(TOURNAMENTS)].copy()
    if t.empty:
        return t
    t["home_league"] = t["home_team"].map(home_of)
    t["away_league"] = t["away_team"].map(home_of)
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("evaluate", "predict", "all"), default="all")
    ap.add_argument("--extra-history", default="",
                    help="glob of extra scoreline parquet (research runs; never written back)")
    args = ap.parse_args()

    d = _history(args.extra_history)
    if d.empty:
        print("[tourney] no scoreline history available")
        return 1
    models, home_of = _domestic_models(d)
    ties = _ties(d, home_of)
    print(f"[tourney] {len(d):,} fixtures | {len(models)} domestic league model(s) | "
          f"{len(ties)} European tie(s) in the store")
    if ties.empty:
        print("[tourney] no European fixtures stored yet — pro_team_stats collects them; "
              "nothing to fit on.")
        return 0

    rated = ls.prepare(ties, models)
    both = len(rated)
    print(f"[tourney] {both} of {len(ties)} tie(s) have a domestic rating for BOTH sides "
          f"({100*both/max(len(ties),1):.0f}%)")
    if both < ls.MIN_ANCHORS:
        # Deliberately refuses rather than fitting on a handful. The 17 top divisions added to
        # v9's config on 2026-09-05 are what closes this gap, via pro_team_stats.
        print(f"[tourney] NOT FITTING: {both} rated tie(s) is under the {ls.MIN_ANCHORS} floor. "
              f"This is the expected state until the top-division backfill completes.")
        return 0

    if args.mode in ("evaluate", "all"):
        ev = ls.evaluate(rated)
        print(f"[tourney] evaluation: {ev}")
        if ev.get("ok") and not ev.get("calibration_helps"):
            print("[tourney] the calibration does NOT beat the uncalibrated null out of sample — "
                  "research only, do not tier or bet.")

    if args.mode in ("predict", "all"):
        cal = ls.fit(rated)
        if not cal.get("ok"):
            print(f"[tourney] no calibration: {cal.get('reason')}")
            return 0
        OUT.mkdir(exist_ok=True)
        CAL_FILE.write_text(json.dumps(cal, indent=2, sort_keys=True), encoding="utf-8")
        upcoming = rated[rated["home_goals"].isna()] if "home_goals" in rated.columns \
            else pd.DataFrame()
        rows = []
        for _, r in upcoming.iterrows():
            p = ls.predict(r, cal)
            if p:
                rows.append({"match_date": r.get("match_date"), "league": r.get("league"),
                             "home_team": r.get("home_team"), "away_team": r.get("away_team"),
                             "home_league": r.get("home_league"),
                             "away_league": r.get("away_league"), **p})
        if rows:
            pd.DataFrame(rows).to_csv(PRED_FILE, index=False, encoding="utf-8")
            print(f"[tourney] wrote {PRED_FILE.name} ({len(rows)} tie(s))")
        else:
            print("[tourney] no upcoming rated ties to price yet")
        top = sorted(cal["strength"].items(), key=lambda kv: -kv[1])[:5]
        print(f"[tourney] strongest leagues by fitted offset: "
              f"{[(k, round(v, 3)) for k, v in top]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
