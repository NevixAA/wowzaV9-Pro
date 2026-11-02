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
    from pathlib import Path
    p = Path(root or cfg.V9_LOCAL) / FIRST_HALF_FILE
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


FLAG = "CLV_FIRST_HALF_CONTAMINATED"
QUARANTINE_COL = "clv_quarantine"


def quarantine_first_half_clv(df: pd.DataFrame, *, root=None, listing: pd.DataFrame | None = None,
                              cols=("clv_pct", "closing_odds"), label: str = "") -> pd.DataFrame:
    """A COPY of a bets_ledger-grain frame with v9's first-half-contaminated closes taken out of CLV.

    Data Truth round 5 (owner rule: apply v9's list in EVERY Pro study that reads bets_ledger
    clv_pct, not only the settlements importer). For each listed row `cols` (the recorded close and
    the CLV derived from it) become NaN and `clv_quarantine` says why; every other column, and v9's
    ledger itself, is unchanged. Rows already carrying the CLV_FIRST_HALF_CONTAMINATED quality flag
    (Pro's settlements) are quarantined too. Apply it to the O/U 2.5 ledger frame BEFORE it is
    concatenated with the side ledger: the list's key has no market column, so on a side-ledger
    row (Over 1.5 / Over 3.5 on the same fixture) it would be a false match.
    """
    if df is None:
        return df
    if len(df) == 0:
        out = df.copy()
        out[QUARANTINE_COL] = pd.Series(dtype="string")
        return out
    lst = (first_half_contaminated(root) if listing is None else listing)
    out = df.copy()
    hit = (first_half_contaminated_mask(out, lst) if not lst.empty
           else pd.Series(False, index=out.index, dtype=bool))
    if "market" in out.columns:
        # The list is O/U 2.5 only; on a mixed-market frame the key match is limited to O/U 2.5.
        hit = hit & out["market"].astype("string").str.upper().isin(["OU25", "OVER25"]).fillna(False)
    if "quality_flags" in out.columns:
        hit = hit | out["quality_flags"].astype("string").str.contains(FLAG, regex=False).fillna(False)
    hit = hit.astype(bool)
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").mask(hit)
    prev = (out[QUARANTINE_COL].astype("string").fillna("") if QUARANTINE_COL in out.columns
            else pd.Series("", index=out.index, dtype="string"))
    out[QUARANTINE_COL] = prev.mask(hit, FLAG)
    tag = f"[v9_corrections{(' ' + label) if label else ''}]"
    if lst.empty and "quality_flags" not in out.columns:
        print(f"{tag} v9 list {FIRST_HALF_FILE} not found - no first-half closes excluded")
    elif hit.any():
        print(f"{tag} {int(hit.sum())} first-half-contaminated close(s) excluded from CLV "
              f"(ledger values unchanged)")
    return out
