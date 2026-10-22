"""Daily progress of the frozen candidate forward tests (P1-4, 2026-10-22).

    python -m src.studies.candidate_forward     # -> output/edge_reassessment/candidate_forward_progress.json

Reads registry/candidate_forward_tests.json (frozen 2026-10-20; definitions NEVER edited here) and the
Pro low-edge shadow (output/valuable_shadow/valuable_shadow.csv: every first-sight candidate from
2026-10-21, settled, CLV certified only within 30 min of kickoff). Three windows are kept strictly apart:

  HISTORICAL_DISCOVERY      the fit / validation / holdout numbers the candidate was chosen on (as registered)
  POST_DISCOVERY_NOT_COUNTED rows between discovery (2026-10-06) and forward start - shown, never counted
  TRUE_FORWARD              rows from forward_start (2026-10-21) - the only rows a pass or fail uses

Status: REGISTERED / ACCRUING / REJECTED / FORWARD_SUPPORTED (BH-adjusted across the H-GATE family).
CONFIRMED is never assigned here. Production behaviour is unchanged.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

REG = cfg.BASE_DIR / "registry" / "candidate_forward_tests.json"
SHADOW = cfg.BASE_DIR / "output" / "valuable_shadow" / "valuable_shadow.csv"
OUT = cfg.BASE_DIR / "output" / "edge_reassessment" / "candidate_forward_progress.json"
MARKET = {"ou25": "over25", "btts": "btts", "over15": "over15", "over35": "over35"}


def _boot(pnl, days, n=2000, seed=11):
    if len(pnl) < 10:
        return (None, None)
    rng = np.random.default_rng(seed)
    u = np.unique(days)
    idx = {k: np.where(days == k)[0] for k in u}
    b = [pnl[np.concatenate([idx[k] for k in rng.choice(u, len(u))])].mean() for _ in range(n)]
    lo, hi = np.percentile(b, [2.5, 97.5]) * 100
    return (round(float(lo), 1), round(float(hi), 1))


def _bh(p: list) -> list:
    v = np.array([np.nan if x is None else x for x in p], float)
    ok = ~np.isnan(v)
    q = np.full(len(v), np.nan)
    if ok.sum():
        w = v[ok]
        o = np.argsort(w)
        qq = w[o] * len(w) / (np.arange(len(w)) + 1)
        qq = np.minimum.accumulate(qq[::-1])[::-1]
        r = np.empty(len(w))
        r[o] = np.minimum(qq, 1)
        q[ok] = r
    return [None if np.isnan(x) else round(float(x), 4) for x in q]


def candidates(shadow: pd.DataFrame) -> pd.DataFrame:
    """First-sight candidates as production would pick them: OU25 = the larger-edge side; BTTS = YES."""
    s = shadow.copy()
    s["edge"] = pd.to_numeric(s["raw_edge"], errors="coerce") / 100
    ou = s[s["market"] == "over25"].sort_values("edge", ascending=False).drop_duplicates("fixture_id")
    side = s[(s["market"] != "over25") & ((s["market"] != "btts") | (s["side"] == "YES"))]
    out = pd.concat([ou, side], ignore_index=True)
    out["gen"] = pd.to_datetime(out["generated_at"], utc=True)
    out["md"] = pd.to_datetime(out["kickoff"], utc=True).dt.tz_convert(None).dt.normalize()
    return out


def evaluate(reg: dict, shadow: pd.DataFrame) -> list[dict]:
    c = candidates(shadow) if len(shadow) else pd.DataFrame()
    start = pd.Timestamp(reg["hypotheses"][0]["forward_start"]) if reg["hypotheses"] else None
    rows = []
    for h in reg["hypotheses"]:
        r = {"id": h["id"], "league": h["league"], "market": h["market"], "model_type": h["model_type"],
             "candidate_gate": h["candidate_gate"], "production_gates": h["production_gates"],
             "required_n": h["min_forward_n"], "required_matchdays": h["required_matchdays"],
             "HISTORICAL_DISCOVERY": h["historical"], "POST_DISCOVERY_NOT_COUNTED": "see edge_reassessment "
             "candidates_forward.csv (snapshot record 2026-10-06 .. 10-20); never counted"}
        if h["candidate_gate"] is None or c.empty:
            x = pd.DataFrame()
        else:
            x = c[(c["league"] == h["league"]) & (c["market"] == MARKET.get(h["market"], h["market"]))
                  & (c["model_type"] == h["model_type"]) & (c["edge"] >= float(h["candidate_gate"]))
                  & (c["gen"] >= pd.Timestamp(h["forward_start"]))]
        s = x[x["result"].isin(["WIN", "LOSS"])] if len(x) else x
        pnl = pd.to_numeric(s["flat_pnl"], errors="coerce").to_numpy(float) if len(s) else np.array([])
        clv = pd.to_numeric(s["clv"], errors="coerce") if len(s) else pd.Series(dtype=float)
        lo, hi = _boot(pnl, s["md"].values) if len(s) else (None, None)
        p = None
        if len(pnl) >= 5 and pnl.std() > 0:
            from math import erfc, sqrt
            z = pnl.mean() / (pnl.std(ddof=1) / sqrt(len(pnl)))
            p = 0.5 * erfc(z / sqrt(2))                                     # one-sided, ROI > 0
        r["TRUE_FORWARD"] = {"candidates_logged": int(len(x)), "n": int(len(s)), "matchdays": int(s["md"].nunique()) if len(s) else 0,
                             "roi_pct": round(float(pnl.mean() * 100), 1) if len(pnl) else None,
                             "roi_ci95": [lo, hi], "clv_coverage_pct": round(float(clv.notna().mean() * 100), 1) if len(clv) else 0.0,
                             "clv_mean": round(float(clv.mean()), 2) if clv.notna().any() else None, "p_one_sided": p}
        r["progress_pct"] = round(min(100.0, 100 * len(s) / h["min_forward_n"]), 1)
        rows.append(r)
    qs = _bh([r["TRUE_FORWARD"]["p_one_sided"] for r in rows])
    for r, q, h in zip(rows, qs, reg["hypotheses"]):
        f = r["TRUE_FORWARD"]
        f["q_bh"] = q
        if h["candidate_gate"] is None:
            r["status"] = "DISCOVERY"
        elif f["n"] == 0:
            r["status"] = "REGISTERED"
        elif (f["n"] >= 2 * h["min_forward_n"] and (f["roi_pct"] or 0) <= 0) or \
                (f["n"] >= h["min_forward_n"] and f["roi_ci95"][1] is not None and f["roi_ci95"][1] < 0):
            r["status"] = "REJECTED"
        elif (f["n"] >= h["min_forward_n"] and f["matchdays"] >= h["required_matchdays"] and f["roi_ci95"][0] is not None
              and f["roi_ci95"][0] > 0 and q is not None and q <= 0.10
              and (f["clv_coverage_pct"] < 50 or (f["clv_mean"] or 0) >= 0)):
            r["status"] = "FORWARD_SUPPORTED"
        else:
            r["status"] = "ACCRUING"
    return rows


def run() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    shadow = pd.read_csv(SHADOW, low_memory=False) if SHADOW.exists() else pd.DataFrame()
    rows = evaluate(reg, shadow)
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
           "registry": "registry/candidate_forward_tests.json", "forward_start": reg["hypotheses"][0]["forward_start"],
           "confirmed_assignable_here": False, "production_changed": "NO",
           "status_counts": pd.Series([r["status"] for r in rows]).value_counts().to_dict(), "hypotheses": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = run()
    print(r["status_counts"])
    for h in r["hypotheses"]:
        f = h["TRUE_FORWARD"]
        print(f"{h['id']} {h['league'][:22]:22s} {h['market']:5s} n {f['n']:3d}/{h['required_n']} roi {f['roi_pct']} {h['status']}")
