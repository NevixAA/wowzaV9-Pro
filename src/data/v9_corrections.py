"""
v9's published corrections, read ONCE here for every Pro consumer.
==================================================================
v9 writes corrections beside its ledgers (output/corrections/). Pro reads them read-only from the v9
checkout (cfg.V9_LOCAL) and never copies the lists: a second copy would drift.

clv_first_half_contaminated.csv (v9 round 2, V2): 170 bets_ledger rows (new_format O/U, archive
2026-07-13 -> 08-23) whose recorded "close" is a FIRST-HALF price - |clv_pct| > 50, e.g. Palmeiras v
Internacional Over 2.5 at 1.91 "closing" at 4.50. They are excluded from every CLV consumer; the
ledger keeps its values. Absent file -> nothing is excluded and that is said out loud.
"""
from __future__ import annotations

import pandas as pd

from config import pro_config as cfg

FIRST_HALF_FILE = "output/corrections/clv_first_half_contaminated.csv"
_KEY = ("match_date", "league", "home_team", "away_team", "side")


def first_half_contaminated(root=None) -> pd.DataFrame:
    """v9's list, or an empty frame when the v9 checkout does not carry it."""
    p = (root or cfg.V9_LOCAL) / FIRST_HALF_FILE
    if not p.exists():
        return pd.DataFrame(columns=list(_KEY))
    try:
        return pd.read_csv(p, dtype=str, keep_default_na=False)
    except Exception as e:                                         # noqa: BLE001
        print(f"[v9_corrections] could not read {p.name}: {type(e).__name__}: {e}")
        return pd.DataFrame(columns=list(_KEY))


def _keys(df: pd.DataFrame) -> pd.Series:
    parts = []
    for k in _KEY:
        s = df[k] if k in df.columns else pd.Series("", index=df.index)
        s = s.astype("string").fillna("").str.strip()
        if k == "match_date":
            s = s.str[:10]
        elif k == "side":
            s = s.str.upper()
        parts.append(s)
    out = parts[0]
    for s in parts[1:]:
        out = out + "|" + s
    return out


def first_half_contaminated_mask(df: pd.DataFrame, listing: pd.DataFrame | None = None) -> pd.Series:
    """True for rows of `df` (match_date, league, home_team, away_team, side) that v9 lists as
    first-half-contaminated closes. A frame without club names cannot be matched -> all False."""
    if df is None or len(df) == 0:
        return pd.Series(False, index=getattr(df, "index", None), dtype=bool)
    lst = first_half_contaminated() if listing is None else listing
    if lst.empty:
        return pd.Series(False, index=df.index, dtype=bool)
    if not {"home_team", "away_team"} <= set(df.columns) or df["home_team"].isna().all():
        return pd.Series(False, index=df.index, dtype=bool)
    bad = set(_keys(lst))
    return _keys(df).isin(bad).fillna(False).astype(bool)
