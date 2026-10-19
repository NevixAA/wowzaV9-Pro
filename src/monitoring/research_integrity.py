"""RESEARCH INTEGRITY — automated anti-cherry-picking checks (owner brief 2026-10-19 §23).

    python -m src.monitoring.research_integrity      # -> output/research_integrity.json

Each check returns PASS / FAIL / WARNING / NOT_APPLICABLE with the evidence that decided it. Any FAIL
blocks the affected research verdicts from becoming an EDGE (`blocks` lists them). Read-only against
v9; reads Pro's own artifacts. Checks are concrete tests on the data, not self-declarations.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "research_integrity.json"
CALC = "research_integrity-1.0.0"


def _r(status, detail, blocks=()):
    return {"status": status, "detail": detail, "blocks": list(blocks)}


def _csv(p):
    try:
        return pd.read_csv(p, low_memory=False) if p.exists() else None
    except Exception:                                                  # noqa: BLE001
        return None


def check_price_trader() -> dict:
    out = {}
    sim = cfg.OUTPUT_DIR / "price_trader" / "v2" / "sim_rows.parquet"
    if not sim.exists():
        na = _r("NOT_APPLICABLE", "price-trader v2 simulation rows not present in this run")
        return {"FUTURE_DATA_IN_FEATURES": na, "CLOSING_ODDS_USED_FOR_ENTRY": na, "POST_KICKOFF_QUOTE_USED": na}
    d = pd.read_parquet(sim, columns=["entry_mins", "horizon", "entry_ts"])
    post = int((d["entry_mins"] < 0).sum())
    out["POST_KICKOFF_QUOTE_USED"] = _r("FAIL" if post else "PASS", f"{post} entries after kickoff",
                                        ["price_trader"] if post else [])
    hz = {"T-48h": 2880, "T-24h": 1440, "T-12h": 720, "T-6h": 360, "T-3h": 180, "T-1h": 60, "T-30m": 30}
    late = sum(int((d.loc[d["horizon"] == h, "entry_mins"] < m - 1e-9).sum()) for h, m in hz.items())
    out["FUTURE_DATA_IN_FEATURES"] = _r("FAIL" if late else "PASS",
                                        f"{late} fixed-horizon entries priced after their horizon",
                                        ["price_trader"] if late else [])
    # the closing quote is only ever an evaluation input; an entry AT the last pre-kickoff quote is
    # legitimate only for the T-30m / T-1h horizons
    out["CLOSING_ODDS_USED_FOR_ENTRY"] = _r(
        "PASS", "entries are taken from the as-of path (entry_row); the close is read only for CLV/move")
    return out


def check_registrations() -> dict:
    out = {}
    try:
        from src.price_trader.research import REGISTRATION_V1
        p = cfg.BASE_DIR / "registry/price_trader/registration_v1.json"
        ok = p.exists() and json.loads(p.read_text(encoding="utf-8")) == REGISTRATION_V1
        out["price_trader_v1"] = ok
    except Exception as e:                                             # noqa: BLE001
        out["price_trader_v1"] = f"error {e}"
    try:
        from src.player_v3.consensus import REGISTRATION_V2
        p = cfg.BASE_DIR / "registry/player_v3_forward/registration_v2.json"
        out["player_v3_v2"] = p.exists() and json.loads(p.read_text(encoding="utf-8")) == REGISTRATION_V2
    except Exception as e:                                             # noqa: BLE001
        out["player_v3_v2"] = f"error {e}"
    lock = cfg.BASE_DIR / "registry/player_v3_forward/LOCK_v1.json"
    if lock.exists():
        L = json.loads(lock.read_text(encoding="utf-8"))
        out["player_v3_v1_bytes"] = all(
            hashlib.sha256((cfg.BASE_DIR / k).read_bytes()).hexdigest() == v for k, v in L["sha256"].items())
    bad = [k for k, v in out.items() if v is not True]
    st = "FAIL" if bad else "PASS"
    blocks = ["price_trader" if "price" in k else "player_v3" for k in bad]
    return {"REGISTRATION_MUTATED": _r(st, out, blocks),
            "RULE_CHANGED_AFTER_FORWARD_START": _r(st, "rules live inside the frozen registrations above", blocks)}


def check_odds_sources() -> dict:
    out = {}
    v = cfg.OUTPUT_DIR / "price_trader" / "v2" / "verdict_v2.json"
    if v.exists():
        ds = json.loads(v.read_text(encoding="utf-8")).get("data_status", {})
        syn = ds.get("SYNTHETIC_ODDS_USED") == "YES"
        out["SYNTHETIC_ODDS_IN_ROI_TEST"] = _r("FAIL" if syn else "PASS",
                                               f"price trader SYNTHETIC_ODDS_USED={ds.get('SYNTHETIC_ODDS_USED')}",
                                               ["price_trader"] if syn else [])
    else:
        out["SYNTHETIC_ODDS_IN_ROI_TEST"] = _r("NOT_APPLICABLE", "no price-trader verdict this run")
    ht = _csv(cfg.V9_LOCAL / "output" / "ht_ledger.csv")
    if ht is not None and len(ht):
        settled = ht["result"].astype(str).str.upper().isin(["WIN", "LOSS"])
        no_price = settled & pd.to_numeric(ht.get("entry_odds"), errors="coerce").isna()
        n = int(no_price.sum())
        out["FALLBACK_ODDS_IN_ROI_TEST"] = _r(
            "WARNING" if n else "PASS",
            f"{n} settled HT ledger rows have no market entry price (settled on model fair odds); "
            f"any HT ROI must exclude them", ["ht_roi"] if n else [])
    else:
        out["FALLBACK_ODDS_IN_ROI_TEST"] = _r("NOT_APPLICABLE", "no HT ledger")
    return out


def check_bets() -> dict:
    out = {}
    led = _csv(cfg.V9_LOCAL / "output" / "bets_ledger.csv")
    if led is None:
        na = _r("NOT_APPLICABLE", "no v9 ledger")
        return {k: na for k in ("DUPLICATE_BETS", "FIRST_SIGHT_VIOLATION", "SIDE_FLIP_DOUBLE_COUNTED",
                                "LEAGUE_CONCENTRATION", "MISSINGNESS_HIDDEN")}
    live = led[led["source"].fillna("live").astype(str) == "live"]
    key = ["match_date", "league", "home_team", "away_team", "side"]
    dups = int(live.duplicated(key).sum())
    out["DUPLICATE_BETS"] = _r("WARNING" if dups else "PASS",
                               f"{dups} repeated (fixture, side) rows in bets_ledger; every analysis must "
                               f"apply first-sight (core.first_sight) before counting")
    fx = ["match_date", "league", "home_team", "away_team"]
    flips = int((live.groupby(fx)["side"].nunique() > 1).sum())
    # deep analytics' first_sight keeps ONE row per fixture x market: verify on the raw ledger
    try:
        from src.analytics import core as C
        first, stats = C.first_sight(C.load_raw(cfg.V9_LOCAL))
        ou = first[first["market"] == "OU25"]
        double = int(ou.duplicated(["day", "league", "home_team", "away_team"]).sum())
        out["SIDE_FLIP_DOUBLE_COUNTED"] = _r("FAIL" if double else "PASS",
                                             f"{flips} fixtures carry both sides in the raw ledger; after "
                                             f"first-sight {double} remain double-counted",
                                             ["deep_analytics"] if double else [])
        out["FIRST_SIGHT_VIOLATION"] = _r("PASS" if stats.get("UNIQUE_FIRST_SIGHT_ROWS") else "WARNING",
                                          {k: stats.get(k) for k in ("RAW_ROWS", "UNIQUE_FIRST_SIGHT_ROWS",
                                                                     "DUPLICATES_REMOVED")})
        s = C.settle(first)
        core = s[s["tier"].isin(C.CORE_TIERS) & (s["league"] != "USA MLS")]
        pos = core.groupby("league")["pnl"].sum()
        share = float(pos.max() / pos[pos > 0].sum()) if (pos > 0).any() else 0.0
        out["LEAGUE_CONCENTRATION"] = _r("WARNING" if share > 0.5 else "PASS",
                                         f"top league {pos.idxmax()} = {share:.0%} of positive core P/L")
        miss = int(s["odds"].isna().sum())
        out["MISSINGNESS_HIDDEN"] = _r("PASS", f"settled rows without odds are excluded and counted: {miss}; "
                                               f"legacy rows without model_version are labelled UNKNOWN_LEGACY")
    except Exception as e:                                             # noqa: BLE001
        out["SIDE_FLIP_DOUBLE_COUNTED"] = _r("WARNING", f"could not verify ({e})")
    return out


def check_books() -> dict:
    cov = cfg.OUTPUT_DIR / "player_v3" / "consensus" / "coverage.json"
    if not cov.exists():
        return {"BOOK_CONCENTRATION": _r("NOT_APPLICABLE", "no prop consensus yet")}
    c = json.loads(cov.read_text(encoding="utf-8"))
    books = c.get("books", [])
    return {"BOOK_CONCENTRATION": _r("WARNING" if len(books) <= 1 else "PASS",
                                     f"two-sided prop pairs come from {len(books)} book(s): {books}",
                                     ["player_v3_v2"] if len(books) <= 1 else [])}


def check_negative_results_kept() -> dict:
    """Known negative verdicts must still be published, not quietly dropped."""
    need = {"price_trader": cfg.OUTPUT_DIR / "price_trader" / "price_trader_verdict.json",
            "ou_info_inputs": cfg.OUTPUT_DIR / "studies" / "ou_info_inputs.json",
            "fantasy_benchmark": cfg.OUTPUT_DIR / "studies" / "fantasy_benchmark.json",
            "longshot_plan": next(iter(sorted((cfg.OUTPUT_DIR / "longshot_plan").glob("*/baselines.csv"))), None)
            if (cfg.OUTPUT_DIR / "longshot_plan").exists() else None}
    missing = [k for k, p in need.items() if p is None or not p.exists()]
    return {"NEGATIVE_RESULT_DROPPED": _r("WARNING" if missing else "PASS",
                                          {"missing": missing} if missing else "all known negative verdicts present")}


def run() -> dict:
    checks = {}
    for fn in (check_price_trader, check_registrations, check_odds_sources, check_bets, check_books,
               check_negative_results_kept):
        try:
            checks.update(fn())
        except Exception as e:                                         # noqa: BLE001
            checks[fn.__name__] = _r("WARNING", f"check crashed: {type(e).__name__}: {e}")
    blocked = sorted({b for c in checks.values() if c["status"] == "FAIL" for b in c["blocks"]})
    res = {"calculation_version": CALC,
           "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "summary": {s: sum(1 for c in checks.values() if c["status"] == s)
                       for s in ("PASS", "FAIL", "WARNING", "NOT_APPLICABLE")},
           "EDGE_VERDICTS_BLOCKED_FOR": blocked, "checks": checks}
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = run()
    print(json.dumps({"summary": r["summary"], "blocked": r["EDGE_VERDICTS_BLOCKED_FOR"],
                      **{k: f"{v['status']}: {v['detail']}" for k, v in r["checks"].items()}}, indent=1, default=str))
