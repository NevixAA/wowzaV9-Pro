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


def _props_cal():
    r = _j("studies/props_calibration.json")
    if not r:
        return None
    l30 = r.get("last_30_days", {})
    return {"status": "Live props model vs reality (30 days): " + ", ".join(
                f"{m} predicted {c['predicted']:.0%} / happened {c['hit']:.0%}" for m, c in l30.items() if c["n"] >= 100),
            "date": r.get("generated_at"),
            "key": {m: f"{r['status'].get(m)} · gap {c['gap']:+.1%} {c['gap_ci90']} · n {c['n']}" for m, c in l30.items()},
            "report": "output/studies/PROPS_CALIBRATION.md"}


def _top_picks():
    p = OUT / "studies" / "top_picks_weekly.csv"
    if not p.exists():
        return None
    h = pd.read_csv(p)
    wk = h["week"].max()
    cur = h[h["week"] == wk]
    key = {f"{r.list} ({r.kind})": f"{r.hit_rate:.0%} hit · {r.roi:+.0%} ROI · {r.zero_days:.0%} 0/5 days · {int(r.picks)} picks"
           for r in cur.itertuples()}
    live = cur[cur["kind"] == "live_to_date"]
    status = (f"Top picks {wk}: live to date " + ", ".join(f"{r.list} {r.hit_rate:.0%}/{r.roi:+.0%}" for r in live.itertuples())
              if len(live) else f"Top picks {wk}: live record not started; backtest in the table")
    return {"status": status, "date": str(cur["updated_at"].iloc[0]), "key": key,
            "report": "output/studies/TOP_PICKS_WEEKLY.md"}


def _leagues():
    p = OUT / "studies" / "league_results_weekly.csv"
    if not p.exists():
        return None
    h = pd.read_csv(p)
    cur = h[(h["week"] == h["week"].max()) & (h["window"] == "season")].sort_values("rank")
    if cur.empty:
        return None
    lab = cur.groupby("label")["league"].apply(lambda s: ", ".join(s)).to_dict()
    status = ("Best leagues (season): proven " + (lab.get("PROVEN") or "none")
              + " · losing " + (lab.get("LOSING") or "none"))
    key = {r.league: f"{r.label} · {int(r.tips)} tips · {r.hit_rate:.0%} hit @ {r.avg_odds:.2f} · ROI {r.roi:+.0%} (shrunk {r.shrunk_roi:+.0%})"
           for r in cur.itertuples()}
    return {"status": status, "date": str(cur["updated_at"].iloc[0]), "key": key, "report": "output/studies/LEAGUE_RESULTS.md"}


def _deep():
    base = OUT / "deep_analytics"
    days = sorted(p.name for p in base.glob("20*") if (p / "answers.json").exists()) if base.exists() else []
    if not days:
        return None
    a = _j(f"deep_analytics/{days[-1]}/answers.json")
    keep = ("CORE_N", "CORE_PNL", "CORE_ROI", "RECENT_CORE_ROI", "NEW_FORMAT_ROI", "STANDARD_ROI", "BEST_LARGE_TRACK",
            "WORST_LARGE_TRACK", "BEST_ODDS_BAND", "WORST_ODDS_BAND", "BEST_TIER", "EDGE_IS_MONOTONIC_WITH_ROI",
            "WOWZA_ADDS_TO_MARKET_V11", "GLOBAL_MOVEMENT_BEATS_PLACEBO", "RECONCILIATION_STATUS")
    conv = a.get("_convergence") or {}
    return {"status": f"Deep analytics {a.get('ANALYSIS_END')}: core {a.get('CORE_N')} bets, {a.get('CORE_PNL')}u, "
                      f"ROI {float(a.get('CORE_ROI') or 0):+.1%} (recent {float(a.get('RECENT_CORE_ROI') or 0):+.1%}); "
                      f"strong convergence: {', '.join(conv.get('STRONG_CONVERGENCE', [])) or 'none'}",
            "date": a.get("ANALYSIS_END"), "key": {k: a.get(k) for k in keep},
            "report": f"output/deep_analytics/{days[-1]}/WOWZA_Deep_Analytics_{days[-1]}.md"}


def _longshot():
    base = OUT / "longshot_plan"
    days = sorted(p.name for p in base.glob("20*")) if base.exists() else []
    if not days:
        return None
    d = base / days[-1]
    try:
        wf = pd.read_csv(d / "baselines.csv")
        prop = json.loads((d / "betting_eligibility_PROPOSED.json").read_text(encoding="utf-8"))
    except Exception:                                                # noqa: BLE001
        return None
    lg = prop.get("leagues", {})
    return {"status": "Longshot plan (BET_ENABLED candidates, plan only): FALSE " +
                      ", ".join(k for k, v in lg.items() if v.get("candidate") == "FALSE"),
            "date": prop.get("generated_from"),
            "key": {r.strategy: f"N {r.N} · PnL {r.PnL:+.1f}u · ROI {r.ROI:+.1%}" for r in wf.itertuples() if r.PnL == r.PnL},
            "report": f"output/longshot_plan/{days[-1]}/WOWZA_LONGSHOT_PROFIT_ENGINE_MASTER_PLAN.md"}


def _lineage():
    a = _j("model_lineage/answers.json")
    if not a:
        return None
    h = a.get("CHAMPION_HEALTH", {})
    return {"status": f"Champion high-water mark: {a.get('RETRAIN_ATTEMPTS_ANALYZED')} retrains, "
                      f"{a.get('PROMOTIONS')} promoted, churn {a.get('MODEL_CHURN_RATE')}; "
                      f"health " + ", ".join(f"{k} {v}" for k, v in sorted(h.items())),
            "date": a.get("GENERATED_AT"),
            "key": {"best proven improvement": a.get("BEST_PROVEN_CHAMPION_IMPROVEMENT"),
                    "head-to-head graded": a.get("H2H_GRADED"),
                    **{f"champion {k}": v for k, v in (a.get("CURRENT_CHAMPION_BY_MODEL") or {}).items()}},
            "report": "output/model_lineage/MODEL_LINEAGE_REPORT.md"}


def _ou_info():
    r = _j("studies/ou_info_inputs.json")
    if not r:
        return None
    fc = _j("studies/ou_info_inputs_forward_check.json") or {}
    cov = {f"{x['track']} covered": f"{x.get('verdict')} (Δ log loss {x['delta']:+.4f}, n {x['n']})"
           for x in r.get("results", []) if x.get("scope") == "covered"}
    return {"status": "Injuries as O/U model inputs (v9 trainer, walk-forward): " +
                      "; ".join(f"{k}: {v.split(' (')[0]}" for k, v in cov.items()),
            "date": r.get("generated_at"),
            "key": {**cov, "duplicate match rows removed from v9 frame": (r.get("dedup") or {}).get("duplicates_dropped"),
                    "prospective leak check": fc.get("verdict")},
            "report": "output/studies/ou_info_inputs.json"}


def _ou_lineups():
    r = _j("studies/ou_lineups.json")
    if not r:
        return None
    cov = {f"{x['track']} with lineups": f"{x['verdict']} (Δ log loss {x['delta']:+.4f}, n {x['n']})"
           for x in r.get("results", []) if x.get("scope") == "covered"}
    return {"status": f"Lineups as O/U model inputs: {r.get('verdict')} (earlier pass was a same-match leak, withdrawn)",
            "date": r.get("generated_at"), "key": cov, "report": "output/studies/ou_lineups.json"}


def _market_anchor():
    r = _j("studies/market_anchor.json")
    if not r:
        return None
    s = (r.get("tracks") or {}).get("standard", {})
    d = s.get("dLL_MARKET_minus_V9", {})
    ub = (s.get("bets", {}).get("V9", {}).get("VALUABLE", {}).get("UNDER") or {})
    return {"status": "Market-anchored O/U (standard): the pre-match price beats v9; weight on v9 when anchored ~0 - "
                      "anchoring leaves no tips",
            "date": r.get("generated_at"),
            "key": {"market minus v9, log loss": f"{d.get('delta')} (90% CI {d.get('ci90')})",
                    "v9 probability spread vs market": f"{s.get('prob_spread_sd', {}).get('V9')} vs "
                                                       f"{s.get('prob_spread_sd', {}).get('MARKET')}",
                    "v9 UNDER bets (edge>=3%)": f"n {ub.get('n')}, ROI {ub.get('roi_pct')}%, claimed hit "
                                                f"{ub.get('claimed_hit')} vs real {ub.get('real_hit')}",
                    "new-format": "price data invalid for this test"},
            "report": "output/studies/market_anchor.json"}


def _standard_repair():
    r = _j("standard_repair/results.json")
    if not r:
        return None
    key = {}
    for m, v in (r.get("verdict") or {}).items():
        M = r["markets"][m]
        b = v.get("best_holdout_arm")
        d = M["arms"][b]["holdout"]["dLL_vs_market"]
        v9 = M["arms"]["V9"]["holdout"]["dLL_vs_market"]
        key[f"{m} (team model, standard)"] = (f"beats market: {v.get('beats_market') or 'none'}; best {b} "
                                             f"dLL {d['delta']:+.4f} (95% CI {d['ci95']}); v9 dLL {v9['delta']:+.4f}")
    return {"status": "Standard repair: no model adds information after the de-vigged market on holdout; "
                      "nothing pre-registered (team models, standard leagues)",
            "date": r.get("generated_at"), "key": key,
            "report": "docs/STANDARD_REPAIR_PROGRAM_2026_10.md"}


def _league_calibration():
    r = _j("studies/league_calibration.json")
    if not r:
        return None
    key = {f"{t} per-league calibration vs v9": f"{x['verdict']} (Δ log loss {x['dLL_PER_LEAGUE_CAL_minus_V9']['delta']:+.4f})"
           for t, x in (r.get("tracks") or {}).items()}
    return {"status": "Per-league calibration of v9 O/U: fixes each league's level but does not improve predictions",
            "date": r.get("generated_at"), "key": key, "report": "output/studies/league_calibration.json"}


def _valuable():
    p = OUT / "valuable_deep_dive" / "valuable_summary.csv"
    if not p.exists():
        return None
    s = pd.read_csv(p)
    pooled = s[(s.tier == "VALUABLE") & s.market.str.startswith("ALL")].set_index("window")
    by = s[s.tier == "VALUABLE"].set_index(["window", "market"])
    f = lambda w: f"{pooled.at[w, 'ROI_pct']:+.1f}% (n {int(pooled.at[w, 'N'])})" if w in pooled.index else "-"
    g = lambda w, m: (f"{by.at[(w, m), 'ROI_pct']:+.1f}% (n {int(by.at[(w, m), 'N'])})" if (w, m) in by.index else "-")
    return {"status": "VALUABLE deep dive: OU25 edge does not rank outcomes; BTTS 4-8% is the stable candidate "
                      "(7 hypotheses registered, shadow started) - production unchanged",
            "date": "2026-10-20",
            "key": {"last 14 days (pooled)": f("last14"), "last 30 days": f("last30"), "since Aug 26": f("since_aug26"),
                    "OU25 since Aug 26": g("since_aug26", "over25"), "BTTS since Aug 26": g("since_aug26", "btts"),
                    "OU25 3-4 / 4-6 / 6-8 since Aug": "-5.8% / +3.1% / +16.3% (CLV falls as edge rises)",
                    "BTTS fair edge 4-8": "new_format +19.6% (n87), standard +31.1% (n34)"},
            "report": "output/valuable_deep_dive/VALUABLE_DEEP_DIVE.md"}


def _learned_tiers():
    r = _j("studies/learned_tiers/learned_tiers.json")
    if not r:
        return None
    key = {}
    for track, v in (r.get("comparison") or {}).items():
        p = v["PRODUCTION"]["ALL_TIPS"]
        lp = (v.get("LEARNED_LEAGUE_PROTECTED") or v["LEARNED"])["ALL_TIPS"]
        key[track] = (f"today's tiers {p.get('roi_pct')}% (n {p.get('n')}) vs learned, leagues protected "
                      f"{lp.get('roi_pct')}% (n {lp.get('n')})")
    return {"status": "Learned per-league tiers (challenger): weekly retrain; re-ranks inside leagues, never switches one "
                      "off (owner: league-off needs >= 600 tips); swap only on prospective rows from 2026-10-21",
            "date": r.get("generated_at"), "key": key, "report": "output/studies/learned_tiers/learned_tiers.json"}


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


def _btts_contradiction():
    r = _j("studies/btts_contradiction.json")
    v = r.get("verdict") or {}
    if not v:
        return None
    h = (r.get("headline") or {}).get("all_nf_tips", {}).get("first_logged", {})
    ex = (r.get("D_league_and_regime") or {}).get("ex_argentina", {})
    return {"status": f"NF BTTS {h.get('roi', 0):+.1%} on {h.get('n')} tips = {str(v.get('PRIMARY_EXPLANATION')).replace('_', ' ').lower()}"
                      f" (Argentina {100 * float(v.get('ARGENTINA_UNITS_SHARE') or 0):.0f}% of units; ex-Argentina "
                      f"{ex.get('roi', 0):+.1%}); not model skill, no stake change",
            "date": r.get("generated_at"),
            "key": {k: v.get(k) for k in ("PRIMARY_EXPLANATION", "TIMING_PRICE_ARTIFACT", "CERTIFIED_CLV_POSITIVE",
                                          "MODEL_ADDS_TO_MARKET", "BEATS_MODEL_FREE_PRICE_RULE", "PROFITABLE_EX_ARGENTINA",
                                          "REGIME_COOLED", "STAKE_CHANGE_RECOMMENDED")},
            "report": "output/studies/BTTS_CONTRADICTION.md"}


STUDIES = [
    ("btts_contradiction", "NF BTTS contradiction: ROI vs CLV", "tips", _btts_contradiction),
    ("player_v3", "Player Model V3 / Edge Lab", "players", _player_v3),
    ("player_v3_forward", "Player V3 forward test (pre-registered)", "players", _forward),
    ("fantasy_v3", "Fantasy (FPL): v9 vs Player V3 projections", "players", _fantasy_v3),
    ("props_calibration", "Props calibration monitor (daily)", "players", _props_cal),
    ("top_picks_weekly", "Top picks — weekly table", "tips", _top_picks),
    ("league_results", "Best leagues — results by league", "tips", _leagues),
    ("deep_analytics", "Deep analytics snapshot (weekly)", "tips", _deep),
    ("longshot_plan", "Longshot Profit Engine — BET_ENABLED plan", "money", _longshot),
    ("model_lineage", "Model lineage — champion high-water mark", "models", _lineage),
    ("ou_info_inputs", "O/U inputs: injuries (lineups / news / movement next)", "models", _ou_info),
    ("ou_lineups", "O/U inputs: starting lineups", "models", _ou_lineups),
    ("market_anchor", "Market-anchored O/U review", "models", _market_anchor),
    ("league_calibration", "Per-league calibration of O/U", "models", _league_calibration),
    ("standard_repair", "Standard repair programme (league x market x side)", "models", _standard_repair),
    ("valuable_deep_dive", "VALUABLE tier deep dive", "tips", _valuable),
    ("learned_tiers", "Learned per-league tiers (challenger)", "tips", _learned_tiers),
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
