"""Serie B BTTS YES: is the edge the league or the model? (frozen forward test, owner 2026-10-29)

    python -m src.studies.btts_league_regime    # -> output/studies/btts_league_regime.json + .md

Reads registry/btts_league_regime/registration_v1.json (definitions NEVER edited here). Two arms on
the same forward Serie B matches, both priced at the FIRST pre-kickoff two-sided BTTS quote in v9's
Standard side-market capture:

  REGIME   BTTS YES on every match, no model           (H-BTTS-REGIME-SB)
  MODEL    the H-GATE-13 picks (v9 raw edge >= 0.02) vs the matches it did NOT pick  (H-BTTS-MODEL-SB)

The question for MODEL is the difference, not the level: Argentina BTTS showed a league can pay
whatever the model does. Results come from API-Football, cached per day (C.results).
Research only. Production behaviour is unchanged.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import v9_config
from src.studies import common as C

REG = cfg.BASE_DIR / "registry" / "btts_league_regime" / "registration_v1.json"
SHADOW = cfg.OUTPUT_DIR / "valuable_shadow" / "valuable_shadow.csv"
PRICES = "output/standard_sidemarket_odds_history.csv"
MAX_ODDS, OVR = 3.2, (1.0, 1.15)      # first-half / garbage quotes out (same rule as the 2026-10-29 study)


def prices(raw: pd.DataFrame, league: str, start: str) -> pd.DataFrame:
    """One row per match: entry (first) and close (last) pre-kickoff two-sided BTTS quotes."""
    p = raw[(raw["league"] == league) & raw["market"].isin(["btts_yes", "btts_no"])].copy()
    p["odds"] = pd.to_numeric(p["odds"], errors="coerce")        # fetch_csv reads everything as str
    p["snapshot_ts"] = pd.to_datetime(p["snapshot_ts"], utc=True, errors="coerce")
    p["kickoff_utc"] = pd.to_datetime(p["kickoff_utc"], utc=True, errors="coerce")
    p = p[(p["match_date"].astype(str) >= start) & (p["kickoff_utc"].isna() | (p["snapshot_ts"] < p["kickoff_utc"]))]
    if p.empty:
        return pd.DataFrame()
    w = p.pivot_table(index=["league", "match", "match_date", "snapshot_ts"], columns="market",
                      values="odds", aggfunc="median").reset_index()
    if not {"btts_yes", "btts_no"} <= set(w.columns):
        return pd.DataFrame()
    w = w.dropna(subset=["btts_yes", "btts_no"])
    ovr = 1 / w["btts_yes"] + 1 / w["btts_no"]
    w = w[(ovr > OVR[0]) & (ovr < OVR[1]) & (w["btts_yes"] <= MAX_ODDS) & (w["btts_no"] <= MAX_ODDS)]
    if w.empty:
        return pd.DataFrame()
    g = w.sort_values("snapshot_ts").groupby(["league", "match", "match_date"])
    m = g.head(1).merge(g.tail(1), on=["league", "match", "match_date"], suffixes=("", "_close"))
    m[["home_team", "away_team"]] = m["match"].str.split(" vs ", n=1, expand=True)
    return m[["league", "match_date", "home_team", "away_team", "btts_yes", "btts_yes_close"]].reset_index(drop=True)


def _roi(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"n": 0, "matchdays": 0, "roi_pct": None, "roi_ci95": [None, None], "clv_mean_pct": None}
    ci = C.block_ci(d["pnl"], d["match_date"], q=(0.025, 0.975))
    return {"n": int(len(d)), "matchdays": int(d["match_date"].nunique()),
            "hit": round(float(d["y"].mean()), 3), "avg_odds": round(float(d["btts_yes"].mean()), 3),
            "roi_pct": round(float(d["pnl"].mean() * 100), 1),
            "roi_ci95": [None if v is None else round(v * 100, 1) for v in ci],
            "clv_mean_pct": round(float(d["clv"].mean() * 100), 2)}


def _diff_ci(a: pd.DataFrame, b: pd.DataFrame, n_boot: int = 3000) -> list:
    """95% CI of ROI(a) - ROI(b), resampling matchdays jointly."""
    days = np.union1d(a["match_date"].unique(), b["match_date"].unique())
    if len(days) < 3 or a.empty or b.empty:
        return [None, None]
    sa, sb = a.groupby("match_date")["pnl"].agg(["sum", "count"]), b.groupby("match_date")["pnl"].agg(["sum", "count"])
    sa, sb = sa.reindex(days, fill_value=0), sb.reindex(days, fill_value=0)
    idx = C.RNG.integers(0, len(days), size=(n_boot, len(days)))
    with np.errstate(invalid="ignore", divide="ignore"):
        ra = sa["sum"].to_numpy()[idx].sum(1) / sa["count"].to_numpy()[idx].sum(1)
        rb = sb["sum"].to_numpy()[idx].sum(1) / sb["count"].to_numpy()[idx].sum(1)
    d = (ra - rb)[np.isfinite(ra - rb)]
    return [round(float(np.quantile(d, 0.025)) * 100, 1), round(float(np.quantile(d, 0.975)) * 100, 1)] if len(d) else [None, None]


def evaluate(reg: dict, board: pd.DataFrame, picked: pd.Series) -> dict:
    """board: settled forward matches (y, pnl, clv, match_date, btts_yes); picked: bool per board row."""
    h_reg, h_mod = reg["hypotheses"]
    r = _roi(board)
    if r["n"] >= h_reg["min_forward_n"] and r["roi_ci95"][1] is not None and r["roi_ci95"][1] < 0:
        st = "REJECTED"
    elif r["n"] >= 2 * h_reg["min_forward_n"] and (r["roi_pct"] or 0) <= 0:
        st = "REJECTED"
    elif (r["n"] >= h_reg["min_forward_n"] and r["matchdays"] >= h_reg["required_matchdays"]
          and r["roi_ci95"][0] is not None and r["roi_ci95"][0] > 0 and (r["clv_mean_pct"] or 0) >= 0):
        st = "FORWARD_SUPPORTED"
    else:
        st = "ACCRUING" if r["n"] else "REGISTERED"
    a, b = board[picked.to_numpy(bool)], board[~picked.to_numpy(bool)]
    ra, rb = _roi(a), _roi(b)
    d = _diff_ci(a, b)
    need = h_mod["min_forward_n_each_arm"]
    if ra["n"] >= need and rb["n"] >= need and d[0] is not None and d[0] > 0:
        sm = "MODEL_ADDS"
    elif ra["n"] >= need and rb["n"] >= need and d[1] is not None and d[1] < 5.0:
        sm = "MODEL_ADDS_NOTHING"
    else:
        sm = "ACCRUING" if len(board) else "REGISTERED"
    return {h_reg["id"]: {"status": st, **r, "progress_pct": round(min(100, 100 * r["n"] / h_reg["min_forward_n"]), 1)},
            h_mod["id"]: {"status": sm, "picked": ra, "not_picked": rb, "roi_difference_ci95_pp": d,
                          "picked_share": round(float(picked.mean()), 3) if len(picked) else None}}


def _board(reg: dict) -> tuple[pd.DataFrame, pd.Series]:
    from src.data.v9_source import fetch_csv
    h = reg["hypotheses"][0]
    start = h["forward_start"]
    end = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    pr = prices(fetch_csv(PRICES), h["league"], start)
    if pr.empty or end < start:
        return pd.DataFrame(), pd.Series(dtype=bool)
    # ALL Wowza league ids, not just Serie B: C.results caches each day filtered to the ids it was
    # asked for, so a Serie-B-only call would poison the shared day cache for ou_studies / ou_challenger.
    res = C.results(start, end, v9_config.league_ids())
    res = res[res["league"] == h["league"]].reset_index(drop=True) if len(res) else res
    if res.empty:
        return pd.DataFrame(), pd.Series(dtype=bool)
    k = C.match_frames(pr, res)
    pr = pr[k.notna()].copy()
    res = res.loc[k.dropna().astype(int).to_numpy()].reset_index(drop=True)
    pr["y"] = C.outcome("BTTS", res["hg"].to_numpy(), res["ag"].to_numpy())
    pr["pnl"] = np.where(pr["y"] == 1, pr["btts_yes"] - 1, -1.0)
    pr["clv"] = pr["btts_yes"] / pr["btts_yes_close"] - 1
    pr = pr.reset_index(drop=True)
    picked = pd.Series(False, index=pr.index)
    if SHADOW.exists():
        s = pd.read_csv(SHADOW, low_memory=False)
        s = s[(s["league"] == h["league"]) & (s["market"] == "btts") & (s["side"] == "YES")
              & (pd.to_numeric(s["raw_edge"], errors="coerce") / 100 >= 0.02)]
        if len(s):
            s = s.assign(match_date=pd.to_datetime(s["kickoff"], utc=True).dt.strftime("%Y-%m-%d"))
            hit = C.match_frames(pr, s.reset_index(drop=True))
            picked = hit.notna()
    return pr, picked


def run() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    board, picked = _board(reg)
    ev = evaluate(reg, board, picked) if len(board) else evaluate(reg, pd.DataFrame(
        columns=["y", "pnl", "clv", "match_date", "btts_yes"]), pd.Series(dtype=bool))
    out = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
           "registry": "registry/btts_league_regime/registration_v1.json",
           "forward_start": reg["hypotheses"][0]["forward_start"], "production_changed": "NO", "hypotheses": ev}
    C.write("btts_league_regime", out)
    a, m = ev["H-BTTS-REGIME-SB"], ev["H-BTTS-MODEL-SB"]
    md = ["# Serie B BTTS YES - league or model? (forward from " + out["forward_start"] + ")", "",
          f"Every match, no model: **{a['status']}** - n {a['n']}/150, ROI {a['roi_pct']}% CI {a['roi_ci95']}, CLV {a['clv_mean_pct']}%", "",
          f"Model picks vs the rest: **{m['status']}** - picked n {m['picked']['n']} ROI {m['picked']['roi_pct']}%, "
          f"not picked n {m['not_picked']['n']} ROI {m['not_picked']['roi_pct']}%, difference CI {m['roi_difference_ci95_pp']} pp", "",
          "Research only; production unchanged."]
    (cfg.OUTPUT_DIR / "studies" / "BTTS_LEAGUE_REGIME.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    r = run()
    for k, v in r["hypotheses"].items():
        print(k, v["status"], {x: v[x] for x in ("n", "roi_pct", "roi_ci95") if x in v})
