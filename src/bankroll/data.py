"""Prospective betting record + v9's policy reader, both read-only from the v9 checkout.

One row per SENT staked tip (SNIPER/MARKSMAN, live source, paper leagues removed), settled:
    date, fixture, league, model_type, market, side, signal_tier, odds, result, unit (P/L per
    1 unit staked, from the ledger), clv (ledger clv_pct / 100 when recorded)
"""
from __future__ import annotations

import importlib.util
import sys

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.bankroll import PERFORMANCE_CUTOFF

SIDE_MARKET = {"btts": "BTTS", "over15": "OVER15", "over35": "OVER35"}


def v9_reader():
    """Import v9's src/bankroll_policy.py by path — the single sizing implementation."""
    path = cfg.V9_LOCAL / "src" / "bankroll_policy.py"
    spec = importlib.util.spec_from_file_location("v9_bankroll_policy", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["v9_bankroll_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


def production_policy() -> dict:
    return v9_reader().load_policy(cfg.V9_LOCAL / "config" / "bankroll_policy.json")


def _paper_leagues() -> set[str]:
    try:
        txt = (cfg.V9_LOCAL / "config.py").read_text(encoding="utf-8")
        import re
        m = re.search(r"PAPER_LEAGUES\s*=\s*(\{[^}]*\}|\[[^\]]*\]|frozenset\([^)]*\))", txt)
        if m:
            return set(re.findall(r"[\"']([^\"']+)[\"']", m.group(1)))
    except Exception:
        pass
    return {"USA MLS"}


def load_bets(from_date: str = PERFORMANCE_CUTOFF, include_unsettled: bool = False) -> pd.DataFrame:
    out = cfg.V9_LOCAL / "output"
    parts = []
    m = pd.read_csv(out / "bets_ledger.csv", low_memory=False)
    parts.append(pd.DataFrame({
        "source": m.get("source"), "generated_at": m.get("generated_at"), "date": m["match_date"],
        "league": m["league"], "home": m["home_team"], "away": m["away_team"],
        "model_type": m.get("model_type"), "market": "OU25", "side": m["side"].astype(str).str.upper(),
        "signal_tier": m["signal_tier"], "odds": m["odds"], "result": m["result"], "pnl": m["pnl"],
        "clv_pct": m.get("clv_pct"), "edge_pct": m.get("edge_pct")}))
    s = pd.read_csv(out / "side_bets_ledger.csv", low_memory=False)
    parts.append(pd.DataFrame({
        "source": s.get("source"), "generated_at": s.get("generated_at"), "date": s["match_date"],
        "league": s["league"], "home": s["home_team"], "away": s["away_team"],
        "model_type": s.get("model_type"), "market": s["market"].map(SIDE_MARKET),
        "side": np.where(s["market"].eq("btts"), "YES", "OVER"), "signal_tier": s["signal_tier"],
        "odds": s["odds"], "result": s["result"], "pnl": s["pnl"], "clv_pct": s.get("clv_pct"),
        "edge_pct": s.get("edge_pct")}))
    d = pd.concat(parts, ignore_index=True)
    d = d[d["source"].fillna("live").astype(str).eq("live")]
    d = d[~d["league"].isin(_paper_leagues())]
    # VALUABLE INCLUDED (2026-10-22). This filter used to drop every VALUABLE tip, so the staking
    # research never saw the tier the live record says works best on OU25 - while Pro's own VALUABLE
    # study and edge reassessment said the opposite of the ladder. Whether a tier is STAKED is the
    # policy's job (tier multipliers); evidence for a track uses its staked tiers (see staked()).
    d = d[d["signal_tier"].isin(["SNIPER", "MARKSMAN", "VALUABLE"]) & d["market"].notna()]
    d["date"] = pd.to_datetime(d["date"].astype(str).str[:10], errors="coerce")
    d = d[d["date"] >= pd.Timestamp(from_date)]
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d["unit"] = pd.to_numeric(d["pnl"], errors="coerce")
    d["clv"] = pd.to_numeric(d["clv_pct"], errors="coerce") / 100.0
    d["edge"] = pd.to_numeric(d["edge_pct"], errors="coerce")
    d["model_type"] = d["model_type"].fillna("unknown").astype(str)
    d["result"] = d["result"].astype(str).str.upper()
    if not include_unsettled:
        d = d[d["unit"].notna()]
    d["fixture"] = d["date"].dt.strftime("%Y-%m-%d") + "|" + d["home"].astype(str) + "|" + d["away"].astype(str)
    d["track"] = d["model_type"] + "|" + d["market"]
    d["month"] = d["date"].dt.to_period("M").astype(str)
    return (d.drop(columns=["source", "pnl", "clv_pct", "edge_pct"])
             .sort_values(["date", "fixture", "track"], kind="mergesort").reset_index(drop=True))


def v11_league_residual() -> pd.DataFrame:
    """v11's per-league 'does Wowza add to the market' (Brier, market vs market+Wowza)."""
    import io

    import requests
    url = "https://raw.githubusercontent.com/NevixAA/wowza_v11/main/output/v11_residual.csv"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return pd.read_csv(io.StringIO(r.text))
    except Exception:
        pass
    return pd.DataFrame(columns=["scope", "n", "brier_market", "brier_market_wowza", "wowza_helps"])


def tier_multiplier(policy: dict, track: str, tier: str) -> float:
    """The multiplier v9's reader applies: the track override if present, else the global ladder."""
    tt = (policy.get("track_tier_multipliers") or {}).get(track)
    return float((tt if tt is not None else policy.get("tier_multipliers", {})).get(str(tier), 0.0))


def staked(bets: pd.DataFrame, policy: dict) -> pd.DataFrame:
    """Only the rows the policy actually stakes (tier multiplier > 0) - the evidence for a track."""
    if bets.empty:
        return bets
    keep = [tier_multiplier(policy, tr, t) > 0 for tr, t in zip(bets["track"], bets["signal_tier"])]
    return bets[keep]
