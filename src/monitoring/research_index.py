"""Research index — one file listing every Pro study's LATEST verdict, for the dashboard.

    python -m src.monitoring.research_index      # -> output/research_index.json

WHY (owner, 2026-10-14): the dashboard's Pro and V11 pages showed only the older studies, so they read
more pessimistic than what had since been learned. Each study already writes a machine-readable verdict;
this module reads them all and writes one index the dashboard renders as-is. Adding a study means adding
ONE entry to STUDIES below - the dashboard needs no change. Runs daily (pro_studies.yml).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR
GH = "https://github.com/NevixAA/wowzaV9-Pro/blob/main/"


def _j(rel: str) -> dict:
    p = OUT / rel
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def _player_v3():
    v = _j("player_v3/player_v3_verdict.json")
    if not v:
        return None
    by = v.get("PLAYER_WOWZA_ADDS_TO_MARKET_BY_MARKET", {})
    return {"status": f"Wowza adds to the prop market: {v.get('PLAYER_WOWZA_ADDS_TO_MARKET')} "
                      f"({', '.join(k for k, x in by.items() if x == 'YES')}) - accuracy level only, profit not shown",
            "date": v.get("generated_at"),
            "key": {"adds to market": v.get("PLAYER_WOWZA_ADDS_TO_MARKET"), "best market": v.get("BEST_MARKET_FOR_INCREMENTAL_EDGE"),
                    "SOT count model beats binary": v.get("SOT_COUNT_MODEL_BEATS_BINARY"),
                    "expected minutes beats v9": v.get("EXPECTED_MINUTES_BEATS_CURRENT_HEURISTIC"),
                    "opponent personnel helps": v.get("OPPONENT_PERSONNEL_HELPS"), "safe to promote": v.get("SAFE_TO_PROMOTE_V3")},
            "report": "output/player_v3/PLAYER_V3_REPORT.md"}


def _forward():
    f = _j("player_v3/forward_test.json")
    if not f:
        return None
    m = {k: (e.get("rule") or {}).get("verdict") for k, e in f.get("markets", {}).items()}
    return {"status": f"{f.get('props_in_window', 0)} settled props since {f.get('window_from')}: " +
                      ", ".join(f"{k} {x}" for k, x in m.items()),
            "date": f.get("generated_at"), "key": m, "report": "output/player_v3/FORWARD_TEST.md"}


def _calibration():
    c = _j("studies/calibration_form.json")
    rows = c.get("rows", [])
    if not rows:
        return None
    better = [r for r in rows if r.get("ci95") and r["ci95"][1] < 0]
    return {"status": f"Log-odds Platt beats v9's probability Platt on {len(better)} of {len(rows)} models "
                      f"(player and team); team models stay compressed (slope > 1)",
            "date": c.get("generated_at"),
            "key": {r["model"]: f"{r['delta_logit_minus_v9']:+.4f} (slope {r['slope_v9_form']} -> {r['slope_logit_form']})" for r in rows},
            "report": "output/studies/CALIBRATION_FORM.md"}


def _cal_shadow():
    c = _j("studies/calibration_shadow.json")
    if not c:
        return None
    fam = {f"{k} {m}": f"{x['verdict']} (n {x['n']}/{x['n_min']}, Δ {x['delta_logloss']:+.5f})"
           for k in ("team", "props") for m, x in (c.get(k) or {}).items()}
    return {"status": f"Live shadow of log-odds calibration in v9: {c.get('overall')}",
            "date": c.get("generated_at"), "key": fam, "report": "output/studies/CALIBRATION_SHADOW.md"}


def _fantasy_v3():
    f = _j("studies/fantasy_v3.json")
    if not f:
        return None
    fair = (f.get("fair_slice") or {}).get("variants", {})
    v3, v9 = fair.get("V3_FULL", {}), fair.get("V9", {})
    return {"status": f"Fantasy (FPL): V3 vs v9 on players who played last week - V3 {v3.get('verdict')}, "
                      f"top-11 {v9.get('top11_pts')} -> {v3.get('top11_pts')} pts/week {v3.get('top11_diff_ci90')}",
            "date": f.get("generated_at"),
            "key": {v: f"{e.get('verdict', 'baseline')} · MAE {e['mae']} · top-11 {e['top11_pts']} · captain {e['captain_pts']}"
                    for v, e in fair.items()},
            "report": "output/studies/FANTASY_V3.md"}


def _segments():
    s = _j("studies/props_segments.json")
    if not s:
        return None
    cells = s.get("cells", {})
    return {"status": f"{s.get('tips_in_window', 0)} qualifying props since {s.get('window_from')}; "
                      f"{sum(1 for c in cells.values() if c.get('verdict') == 'EDGE')} EDGE cells",
            "date": s.get("generated_at"), "key": {k: c.get("verdict") for k, c in cells.items()},
            "report": "output/studies/PROPS_SEGMENTS.md"}


def _price_trader():
    v = _j("price_trader/price_trader_verdict.json")
    if not v:
        return None
    return {"status": f"Price-trading edge: movement beats placebo {v.get('MOVEMENT_BEATS_PLACEBO')}, "
                      f"full green profitable {v.get('FULL_GREEN_PROFITABLE_AFTER_COSTS')}, "
                      f"prospective {v.get('PROSPECTIVE_CONFIRMATION')}",
            "date": v.get("generated_at"),
            "key": {k: v.get(k) for k in ("MOVEMENT_SIGNAL_EXISTS", "MOVEMENT_BEATS_PLACEBO", "FULL_GREEN_PROFITABLE_AFTER_COSTS",
                                          "TRADING_BEATS_HOLD", "EXECUTABLE_PRICE_DATA_SUFFICIENT", "PROSPECTIVE_CONFIRMATION")},
            "report": "output/price_trader/PRICE_TRADER_REPORT.md"}


def _bankroll():
    r = _j("bankroll/current_policy_recommendation.json")
    if not r:
        return None
    rv = r.get("review", {})
    return {"status": f"Recommended: {rv.get('RECOMMENDED_POLICY')} · change {rv.get('POLICY_CHANGE_RECOMMENDED')} · "
                      f"allocator {rv.get('walk_forward', {}).get('status')}",
            "date": r.get("generated_at"),
            "key": {k: f"{t.get('state')} {100 * float(t.get('base_fraction', 0)):.2f}%" for k, t in r.get("tracks", {}).items()},
            "report": "output/bankroll/MONTHLY_REVIEW.md"}


def _promotion():
    r = _j("scout/weekly_promotion_review.json")
    if not r:
        return None
    return {"status": f"{r.get('leagues_monitored')} leagues monitored · candidates {r.get('counts', {}).get('new_candidates')} · "
                      f"promoted {r.get('counts', {}).get('promoted')}", "date": r.get("generated_at"),
            "key": r.get("counts", {}), "report": "output/scout/WEEKLY_PROMOTION_REVIEW.md"}


def _props_learner():
    r = _j("studies/props_learner.json")
    if not r:
        return None
    return {"status": r.get("recommendation"), "date": r.get("generated"),
            "key": {m["market"]: m.get("verdict") for m in r.get("markets", [])},
            "report": "output/studies/PROPS_LEARNER.md"}


def _ou_studies():
    r = _j("studies/ou_challenger.json") or {}
    e = _j("studies/evidence.json") or {}
    if not r and not e:
        return None
    return {"status": "October upgrade studies (O/U challenger, Argentina BTTS, per-league evidence) - see report",
            "date": r.get("generated_at") or e.get("generated_at"), "key": {}, "report": "output/studies/REPORT.md"}


STUDIES = [
    ("player_v3", "Player Model V3 / Edge Lab", "players", _player_v3),
    ("player_v3_forward", "Player V3 forward test (pre-registered)", "players", _forward),
    ("fantasy_v3", "Fantasy (FPL): v9 vs Player V3 projections", "players", _fantasy_v3),
    ("calibration_form", "Calibration form: v9 vs log-odds Platt", "models", _calibration),
    ("calibration_shadow", "Calibration shadow in v9 (pre-registered)", "models", _cal_shadow),
    ("props_segments", "Props segments: attacking D / M (pre-registered)", "players", _segments),
    ("props_learner", "Props learner: classic GB vs HGB", "players", _props_learner),
    ("price_trader", "Price Trader / back-to-lay lab", "market", _price_trader),
    ("bankroll", "Monthly bankroll review", "money", _bankroll),
    ("league_promotion", "Weekly league promotion", "leagues", _promotion),
    ("upgrade_studies", "October upgrade studies", "models", _ou_studies),
]


def build() -> dict:
    items = []
    for sid, title, area, fn in STUDIES:
        try:
            r = fn()
        except Exception as e:                                        # noqa: BLE001 - one bad file never hides the rest
            r = {"status": f"index error: {type(e).__name__}", "date": None, "key": {}, "report": None}
        if not r:
            continue
        items.append({"id": sid, "title": title, "area": area, **r,
                      "report_url": GH + r["report"] if r.get("report") else None})
    items.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    return {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"), "items": items}


def main() -> int:
    r = build()
    (OUT / "research_index.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    for i in r["items"]:
        print(f"- {i['title']}: {i['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
