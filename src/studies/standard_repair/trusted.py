"""TRUSTED_FROM per evidence family (owner brief 2026-10-28).

Evidence collected before a structural fix is not evidence about the fixed system. Each family below
names the v9 commits that changed what it measures (verified with `git show -s` on v9 origin/main,
2026-10-28) and the instant from which rows in that family are trusted. Commit times are the commit's
own timestamp converted to UTC; a fix can only protect data produced AFTER it is deployed, so this is a
lower bound on when the fix took effect, never an upper one.

PRE_REPAIR_FORWARD vs POST_REPAIR_FORWARD: forward evidence of the SERVED Standard model is
PRE_REPAIR until a repaired recipe is registered as an immutable forward experiment (STD-V9R-*); the
boundary is that registration's `frozen_at`. The two are never pooled.
"""
from __future__ import annotations

import pandas as pd

OWNER_LIVE_WINDOW = "2026-09-01T00:00:00Z"   # owner: August live evidence carried a known bug

FIXES = {
    "23c3787d": ("2026-08-15T16:01:56Z", "Resolve OddsAPI club names against football-data history (46% of standard fixtures had no form)"),
    "b8ddfe3c": ("2026-08-15T16:28:29Z", "Write NaN instead of invented values when enrichment does not run (29 stand-in columns)"),
    "d4bd8ba5": ("2026-08-15T16:34:18Z", "Never bet a fixture with no rolling-form history"),
    "a397f7a8": ("2026-08-06T11:49:48Z", "Season rollover 2025->2026 for live collection"),
    "f40ea158": ("2026-08-21T15:54:54Z", "OddsAPI Ligue 2 sport key (Ligue 2 had never been fetchable)"),
    "8d9962c6": ("2026-08-23T08:26:13Z", "BTTS capture parser stored the FIRST-HALF market as full-match"),
    "a5423ade": ("2026-08-23T11:22:34Z", "Filter first-half BTTS out of both model read paths"),
    "f9d6f5c3": ("2026-09-06T10:47:03Z", "data_loader season list derived (was a year stale: live season never downloaded)"),
    "9956950b": ("2026-09-07T08:07:01Z", "NEAR odds capture unreachable 2026-08-29..09-07"),
    "ed8b86a9": ("2026-09-22T07:17:58Z", "Backtest: a filled price is not a price (O1.5 certified on a constant 1.40)"),
    "3c2f2a84": ("2026-09-23T06:49:20Z", "Four seasons of corners / half-time goals / O-U price frozen out of training"),
    "6c80672f": ("2026-09-24T08:32:49Z", "One club becoming two teams (v9 _canonicalise_clubs)"),
    "a938a199": ("2026-09-24T08:46:30Z", "Backtest archive (2020+) added to training"),
    "62d395b6": ("2026-09-28T12:23:30Z", "74% of HT training labels fabricated"),
    "6744fb37": ("2026-10-08T08:29:25Z", "Ligue 2 is API-Football league 62, not 65"),
    "39ca20c6": ("2026-10-22T06:22:07Z", "A closing price counts only within 30 min of kickoff"),
}

FAMILIES = {
    "STANDARD_LIVE_SETTLEMENT_AND_ENTRY_PRICE": {
        "fixes": ["23c3787d", "f40ea158"], "floor": OWNER_LIVE_WINDOW,
        "meaning": "a live Standard tip's settlement and the price it was tipped at"},
    "STANDARD_SERVED_MODEL_INPUTS": {
        "fixes": ["23c3787d", "b8ddfe3c", "f9d6f5c3", "3c2f2a84", "6c80672f", "a938a199"], "floor": OWNER_LIVE_WINDOW,
        "meaning": "the served probability was computed by a model trained on a frame with the live season, "
                   "the four recovered seasons of corners/HT/O-U price and v9's club canonicaliser",
        "open_defects": ["residual alias collisions in v9's frame (identity.py) - not fixed in v9",
                         "batch-median imputation, home_advantage constant live, away-HT scope, cross-league "
                         "rolling order (R1 / identity.rolling_order_leak) - not fixed in v9"]},
    "STANDARD_SIDE_MARKET_REAL_PRICE_ENTRY": {
        "fixes": ["8d9962c6", "a5423ade"], "floor": None,
        "meaning": "a BTTS/O1.5 quote captured forward is a full-match price (1H filter applied on read)"},
    "STANDARD_FORWARD_CLOSE_T30": {
        "fixes": ["8d9962c6", "9956950b", "39ca20c6"], "floor": None,
        "meaning": "a certified T-30m close exists (capture ran inside the window)"},
    "STANDARD_HISTORICAL_SIDE_MARKET_ROI": {
        "fixes": ["ed8b86a9"], "floor": None, "never": True,
        "meaning": "historical BTTS/O1.5/O3.5 ROI: no real two-sided timed price exists historically; "
                   "constant fills (1.85/1.40/2.60) are never certifiable"},
    "LIGUE2_API_FOOTBALL_DERIVED": {
        "fixes": ["6744fb37"], "floor": None,
        "meaning": "Ligue 2 data fetched by API-Football league id (player history, injuries, AF quotes)"},
    "HT_TARGETS": {"fixes": ["62d395b6"], "floor": None, "meaning": "half-time labels (not Standard O/U)"},
}


def trusted_from(family: str) -> str | None:
    f = FAMILIES[family]
    if f.get("never"):
        return None
    ts = [pd.Timestamp(FIXES[s][0]) for s in f["fixes"]]
    if f.get("floor"):
        ts.append(pd.Timestamp(f["floor"]))
    return max(ts).isoformat()


def table() -> dict:
    out = {}
    for fam, f in FAMILIES.items():
        out[fam] = {"trusted_from": trusted_from(fam) if not f.get("never") else "NEVER (forward only)",
                    "meaning": f["meaning"],
                    "fixes": [{"v9_commit": s, "committed_utc": FIXES[s][0], "what": FIXES[s][1]} for s in f["fixes"]],
                    "open_defects": f.get("open_defects", [])}
    return out


def forward_phase(ts, post_repair_from: str | None) -> str:
    """PRE_REPAIR_FORWARD / POST_REPAIR_FORWARD for a forward row observed at `ts`."""
    if not post_repair_from:
        return "PRE_REPAIR_FORWARD"
    def utc(x):
        t = pd.Timestamp(x)
        return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return "POST_REPAIR_FORWARD" if utc(ts) >= utc(post_repair_from) else "PRE_REPAIR_FORWARD"
