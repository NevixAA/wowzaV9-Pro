"""Deep-analytics core: canonical first-sight bets, flat-stake metrics, windows, breakdown tables.

FIRST SIGHT (owner brief section 2). Ledgers can hold repeated observations of one future fixture as
prices and model outputs update. A bet is the EARLIEST valid tip per
    O/U 2.5      (match_date, league, home_team, away_team)
    side market  (match_date, league, home_team, away_team, market)
    half-time    (match_date, league, home_team, away_team, market)
ordered by generated_at. A later row with the OPPOSITE side is the model flipping, not a second bet:
it is dropped and counted in CONFLICTING_SIDE_ROWS_FOUND (v9's first-tip-freeze semantics).

FLAT STAKE. 1 unit per bet: WIN -> odds - 1, LOSS -> -1, VOID/PUSH -> 0 (counted in N, not in hit).
ROI = PnL / N. Hit = W / (W + L). Break-even hit = mean(1/odds) (v9 README rule: never 1/mean(odds)).
Uncertainty: bootstrap over MATCH DAYS (bets on one day are not independent), 90% and 95%.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TIERS = ("SNIPER", "MARKSMAN", "VALUABLE")
CORE_TIERS = ("SNIPER", "MARKSMAN")
SIDE_MARKET = {"btts": "BTTS", "over15": "OVER15", "over35": "OVER35"}
RNG_SEED = 20261018
N_BOOT = 1000

ODDS_BANDS = [(0, 1.50, "<1.50"), (1.50, 1.60, "1.50-1.59"), (1.60, 1.80, "1.60-1.79"), (1.80, 2.00, "1.80-1.99"),
              (2.00, 2.25, "2.00-2.24"), (2.25, 2.50, "2.25-2.49"), (2.50, 2.75, "2.50-2.74"),
              (2.75, 3.00, "2.75-2.99"), (3.00, 3.50, "3.00-3.49"), (3.50, 99, "3.50+")]
EDGE_BANDS = [(-9, 0.04, "<4%"), (0.04, 0.06, "4-5.99%"), (0.06, 0.08, "6-7.99%"), (0.08, 0.10, "8-9.99%"),
              (0.10, 0.12, "10-11.99%"), (0.12, 0.15, "12-14.99%"), (0.15, 0.20, "15-19.99%"), (0.20, 9, "20%+")]
PROB_BANDS = [(0, 0.40, "<40%"), (0.40, 0.45, "40-44.9%"), (0.45, 0.50, "45-49.9%"), (0.50, 0.55, "50-54.9%"),
              (0.55, 0.60, "55-59.9%"), (0.60, 0.65, "60-64.9%"), (0.65, 0.70, "65-69.9%"), (0.70, 1.01, "70%+")]


# ── loading ──────────────────────────────────────────────────────────────────────────────────
def _edge_fraction(s: pd.Series) -> pd.Series:
    e = pd.to_numeric(s, errors="coerce")
    return e / 100.0 if e.abs().median() > 1.0 else e


def load_raw(v9_dir) -> pd.DataFrame:
    """All three v9 ledgers in one schema, every row (before first-sight)."""
    from pathlib import Path
    out = Path(v9_dir) / "output"
    parts = []
    p = out / "bets_ledger.csv"
    if p.exists():
        m = pd.read_csv(p, low_memory=False)
        m = m.assign(ledger="ou25", market="OU25", side=m["side"].astype(str).str.upper(),
                     tier=m["signal_tier"], model_prob=np.nan)
        parts.append(m)
    p = out / "side_bets_ledger.csv"
    if p.exists():
        s = pd.read_csv(p, low_memory=False)
        s = s.assign(ledger="side", market=s["market"].astype(str).str.lower().map(SIDE_MARKET).fillna(
            s["market"].astype(str).str.upper()), side=s["side"].fillna("YES").astype(str).str.upper(),
            tier=s["signal_tier"])
        parts.append(s)
    p = out / "ht_ledger.csv"
    if p.exists():
        h = pd.read_csv(p, low_memory=False)
        h = h.assign(ledger="ht", market="HT_" + h["market"].astype(str).str.upper(),
                     side=h["side"].astype(str).str.upper(), tier="HT", odds=h["entry_odds"],
                     model_type="standard", edge_pct=np.nan)
        parts.append(h)
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    d["source"] = d["source"].fillna("live").astype(str)
    d["day"] = d["match_date"].astype(str).str[:10]
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d["closing_odds"] = pd.to_numeric(d.get("closing_odds"), errors="coerce")
    d["clv"] = pd.to_numeric(d.get("clv_pct"), errors="coerce")
    d["clv"] = d["clv"] / 100.0 if d["clv"].abs().median() > 1.0 else d["clv"]
    d["edge"] = _edge_fraction(d["edge_pct"])
    d["kelly"] = pd.to_numeric(d.get("kelly_pct"), errors="coerce")
    mp = pd.to_numeric(d["model_prob"], errors="coerce")
    d["model_p"] = mp.where(mp.notna(), 1.0 / d["odds"] + d["edge"])
    d["model"] = d["model_type"].fillna("unknown").astype(str).replace({"nan": "unknown", "": "unknown"})
    d["result"] = d["result"].fillna("").astype(str).str.upper().str.strip()
    d["ledger_pnl"] = pd.to_numeric(d["pnl"], errors="coerce")
    d["generated_at"] = pd.to_datetime(d["generated_at"], errors="coerce", utc=True)
    return d


def first_sight(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Canonical bets + the counts the brief asks for. Live rows only."""
    live = d[d["source"].eq("live")].copy()
    stats = {"RAW_ROWS": int(len(d)), "LIVE_ROWS": int(len(live))}
    live["_key"] = (live["day"] + "|" + live["league"].astype(str) + "|" + live["home_team"].astype(str) + "|"
                    + live["away_team"].astype(str) + "|" + live["market"].astype(str))
    live = live.sort_values(["generated_at"], kind="mergesort", na_position="last")
    sides = live.groupby("_key")["side"].nunique()
    conflict_keys = set(sides[sides > 1].index)
    first = live.drop_duplicates("_key", keep="first")
    stats["UNIQUE_FIRST_SIGHT_ROWS"] = int(len(first))
    stats["DUPLICATES_REMOVED"] = int(len(live) - len(first))
    stats["CONFLICTING_SIDE_KEYS"] = int(len(conflict_keys))
    stats["CONFLICTING_SIDE_ROWS_FOUND"] = int(live[live["_key"].isin(conflict_keys)].shape[0] - len(conflict_keys))
    return first.drop(columns="_key").reset_index(drop=True), stats


def settle(d: pd.DataFrame) -> pd.DataFrame:
    """Flat 1u results; keeps settled rows only (WIN / LOSS / VOID / PUSH)."""
    s = d[d["result"].isin(["WIN", "LOSS", "VOID", "PUSH"])].copy()
    s = s[s["odds"] > 1.0]
    # side "AVOID" is the model declining the fixture, not a bet (122 such O/U rows, all VOID): never a bet.
    s = s[s["side"].astype(str).str.upper() != "AVOID"]
    s["win"] = (s["result"] == "WIN").astype(int)
    s["loss"] = (s["result"] == "LOSS").astype(int)
    s["void"] = s["result"].isin(["VOID", "PUSH"]).astype(int)
    s["pnl"] = np.where(s["win"] == 1, s["odds"] - 1.0, np.where(s["loss"] == 1, -1.0, 0.0))
    s["implied"] = 1.0 / s["odds"]
    s["date"] = pd.to_datetime(s["day"], errors="coerce")
    s["month"] = s["date"].dt.strftime("%Y-%m")
    s["week"] = s["date"].dt.strftime("%G-W%V")
    s["track"] = s["model"] + "|" + s["market"]
    return s.sort_values(["date", "generated_at"], kind="mergesort").reset_index(drop=True)


def universes(s: pd.DataFrame, paper_leagues, policy: dict) -> dict[str, pd.DataFrame]:
    paper = set(paper_leagues or ())
    tracks = (policy or {}).get("tracks", {})
    state = s["track"].map(lambda t: tracks.get(t, {}).get("state", "UNLISTED"))
    non_paper = ~s["league"].isin(paper)
    team = s["tier"].isin(TIERS)
    return {
        "ALL_LIVE": s[team],
        "NON_MLS": s[team & non_paper],
        "CORE": s[s["tier"].isin(CORE_TIERS) & non_paper],
        "VALUABLE": s[(s["tier"] == "VALUABLE") & non_paper],
        "CURRENT_ACTIVE_POLICY": s[s["tier"].isin(CORE_TIERS) & non_paper & state.isin(["ACTIVE", "ACTIVE_LOW"])],
        "PAPER_TRACKS": s[team & non_paper & state.eq("PAPER")],
        "BLOCKED_TRACKS": s[team & non_paper & state.str.startswith("BLOCKED")],
        "HT": s[s["tier"] == "HT"],
    }


# ── windows ──────────────────────────────────────────────────────────────────────────────────
def windows(end: pd.Timestamp) -> dict[str, tuple]:
    end = pd.Timestamp(end).normalize()
    month0 = end.replace(day=1)
    prev0 = (month0 - pd.Timedelta(days=1)).replace(day=1)
    wk0 = end - pd.Timedelta(days=end.weekday())
    return {"full_history": (pd.Timestamp("2000-01-01"), end), "since_2026-08-26": (pd.Timestamp("2026-08-26"), end),
            "since_2026-09-01": (pd.Timestamp("2026-09-01"), end), "since_2026-09-24": (pd.Timestamp("2026-09-24"), end),
            "last_60_days": (end - pd.Timedelta(days=59), end), "last_30_days": (end - pd.Timedelta(days=29), end),
            "last_14_days": (end - pd.Timedelta(days=13), end), "last_7_days": (end - pd.Timedelta(days=6), end),
            "current_month": (month0, end), "previous_month": (prev0, month0 - pd.Timedelta(days=1)),
            "current_iso_week": (wk0, end)}


def in_window(s: pd.DataFrame, w: tuple) -> pd.DataFrame:
    return s[(s["date"] >= w[0]) & (s["date"] <= w[1])]


# ── metrics ──────────────────────────────────────────────────────────────────────────────────
def confidence_label(n: int) -> str:
    return ("VERY_SMALL" if n < 10 else "SMALL" if n < 25 else "EARLY" if n < 50 else "BUILDING" if n < 100
            else "MEANINGFUL" if n < 200 else "MATURE")


def _boot(g: pd.DataFrame, seed: int = RNG_SEED) -> dict:
    by = g.groupby("day").agg(pnl=("pnl", "sum"), n=("pnl", "size"), w=("win", "sum"), wl=("result", lambda r: r.isin(["WIN", "LOSS"]).sum()))
    if len(by) < 5:
        return {}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(by), size=(N_BOOT, len(by)))
    roi = by["pnl"].to_numpy()[idx].sum(1) / by["n"].to_numpy()[idx].sum(1)
    wl = by["wl"].to_numpy()[idx].sum(1)
    hit = by["w"].to_numpy()[idx].sum(1) / np.where(wl == 0, np.nan, wl)
    q = lambda a, p: float(np.nanquantile(a, p))  # noqa: E731
    return {"roi_ci_lo_90": q(roi, 0.05), "roi_ci_hi_90": q(roi, 0.95), "roi_ci_lo_95": q(roi, 0.025),
            "roi_ci_hi_95": q(roi, 0.975), "hit_ci_lo_90": q(hit, 0.05), "hit_ci_hi_90": q(hit, 0.95)}


def summarize(g: pd.DataFrame, ci: bool = True) -> dict:
    n = len(g)
    if n == 0:
        return {"N": 0, "confidence_label": "VERY_SMALL"}
    w, lo, v = int(g["win"].sum()), int(g["loss"].sum()), int(g["void"].sum())
    clv = g["clv"].dropna()
    out = {"sample_start": g["day"].min(), "sample_end": g["day"].max(), "N": n, "W": w, "L": lo, "void": v,
           "hit_rate": w / (w + lo) if (w + lo) else np.nan, "pnl_units": float(g["pnl"].sum()),
           "roi": float(g["pnl"].sum() / n), "avg_odds": float(g["odds"].mean()), "median_odds": float(g["odds"].median()),
           "avg_implied_probability": float(g["implied"].mean()), "break_even_hit_rate": float(g["implied"].mean()),
           "avg_edge": float(g["edge"].mean()) if g["edge"].notna().any() else np.nan,
           "median_edge": float(g["edge"].median()) if g["edge"].notna().any() else np.nan,
           "avg_model_probability": float(g["model_p"].mean()) if g["model_p"].notna().any() else np.nan,
           "median_model_probability": float(g["model_p"].median()) if g["model_p"].notna().any() else np.nan,
           "avg_kelly_pct": float(g["kelly"].mean()) if g["kelly"].notna().any() else np.nan,
           "median_kelly_pct": float(g["kelly"].median()) if g["kelly"].notna().any() else np.nan,
           "clv_n": int(len(clv)), "avg_clv": float(clv.mean()) if len(clv) else np.nan,
           "median_clv": float(clv.median()) if len(clv) else np.nan,
           "pct_positive_clv": float((clv > 0).mean()) if len(clv) else np.nan,
           "confidence_label": confidence_label(n)}
    out["hit_minus_break_even_pp"] = (out["hit_rate"] - out["break_even_hit_rate"]) * 100 if out["hit_rate"] == out["hit_rate"] else np.nan
    if ci and n >= 10:
        out.update(_boot(g))
    return out


def recent_cols(g: pd.DataFrame, end: pd.Timestamp, recent_from: str) -> dict:
    out = {}
    r = g[g["date"] >= pd.Timestamp(recent_from)]
    out.update({"recent_N": len(r), "recent_W": int(r["win"].sum()), "recent_L": int(r["loss"].sum()),
                "recent_PnL": float(r["pnl"].sum()), "recent_ROI": float(r["pnl"].sum() / len(r)) if len(r) else np.nan})
    for days in (30, 14, 7):
        x = g[g["date"] > end - pd.Timedelta(days=days)]
        out[f"last{days}_N"] = len(x)
        out[f"last{days}_ROI"] = float(x["pnl"].sum() / len(x)) if len(x) else np.nan
    return out


def table(s: pd.DataFrame, by: list[str], end: pd.Timestamp, recent_from: str, ci: bool = True) -> pd.DataFrame:
    rows = []
    for key, g in s.groupby(by, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        r.update(summarize(g, ci))
        r.update(recent_cols(g, end, recent_from))
        rows.append(r)
    return pd.DataFrame(rows)


def band(x: pd.Series, bands) -> pd.Series:
    out = pd.Series(pd.NA, index=x.index, dtype="object")
    for lo, hi, lab in bands:
        out[(x >= lo) & (x < hi)] = lab
    return out


# ── season projection ────────────────────────────────────────────────────────────────────────
SEASON_DAYS = 300          # a European season Aug -> May; documented in the Methodology sheet
SHRINK_K = 200             # conservative scenario: shrunk ROI = N / (N + K) x ROI


def projection(g: pd.DataFrame, start: str, recent_from: str, end: pd.Timestamp) -> dict:
    def part(x, frm):
        days = max(1, (end - pd.Timestamp(frm)).days + 1)
        n = len(x)
        roi = float(x["pnl"].sum() / n) if n else np.nan
        tips = n / days * SEASON_DAYS
        return n, days, n / days, roi, float(x["pnl"].sum()), tips, tips * roi if n else np.nan
    a = part(g[g["date"] >= pd.Timestamp(start)], start)
    b = part(g[g["date"] >= pd.Timestamp(recent_from)], recent_from)
    shrunk = a[0] / (a[0] + SHRINK_K) * a[3] if a[0] else np.nan
    return {"current_N": a[0], "days_observed": a[1], "bets_per_day": a[2], "current_ROI": a[3], "current_PnL": a[4],
            "full_window_projected_tips": a[5], "full_window_projected_PnL": a[6],
            "recent_N": b[0], "recent_days": b[1], "recent_bets_per_day": b[2], "recent_ROI": b[3],
            "recent_projected_tips": b[5], "recent_projected_PnL": b[6],
            "shrunk_ROI": shrunk, "conservative_projected_PnL": a[5] * shrunk if a[0] else np.nan}


# ── risk ─────────────────────────────────────────────────────────────────────────────────────
def drawdown(g: pd.DataFrame) -> dict:
    if g.empty:
        return {"N": 0}
    c = g["pnl"].cumsum()
    dd = (c.cummax().clip(lower=0) - c)
    streak = lambda v: int(max((sum(1 for _ in grp) for k, grp in __import__("itertools").groupby(v) if k), default=0))  # noqa: E731
    daily = g.groupby("date")["pnl"].sum()
    full = daily.reindex(pd.date_range(daily.index.min(), daily.index.max()), fill_value=0)
    r7, r30 = full.rolling(7).sum(), full.rolling(30).sum()
    return {"N": len(g), "PnL": float(c.iloc[-1]), "max_drawdown_units": float(dd.max()),
            "max_drawdown_pct_of_100u": float(dd.max()) / 100.0,
            "longest_losing_streak": streak((g["result"] == "LOSS").tolist()),
            "longest_winning_streak": streak((g["result"] == "WIN").tolist()),
            "worst_day": str(daily.idxmin().date()), "worst_day_pnl": float(daily.min()),
            "best_day": str(daily.idxmax().date()), "best_day_pnl": float(daily.max()),
            "worst_7d_pnl": float(r7.min()) if r7.notna().any() else np.nan,
            "best_7d_pnl": float(r7.max()) if r7.notna().any() else np.nan,
            "worst_30d_pnl": float(r30.min()) if r30.notna().any() else np.nan,
            "best_30d_pnl": float(r30.max()) if r30.notna().any() else np.nan}


def curve(g: pd.DataFrame, name: str) -> pd.DataFrame:
    by = g.groupby("date").agg(n=("pnl", "size"), pnl=("pnl", "sum")).reset_index()
    by["cumulative_bets"], by["cumulative_pnl"] = by["n"].cumsum(), by["pnl"].cumsum()
    by["running_roi"] = by["cumulative_pnl"] / by["cumulative_bets"]
    return by.assign(track=name)[["track", "date", "cumulative_bets", "cumulative_pnl", "running_roi"]]


def rolling(g: pd.DataFrame, name: str) -> pd.DataFrame:
    g = g.reset_index(drop=True)
    out = pd.DataFrame({"track": name, "bet_no": range(1, len(g) + 1), "date": g["date"]})
    for k in (20, 50, 100):
        out[f"roi_{k}_bets"] = g["pnl"].rolling(k).mean()
        out[f"hit_{k}_bets"] = g["win"].rolling(k).mean()
        out[f"clv_{k}_bets"] = g["clv"].rolling(k, min_periods=max(5, k // 4)).mean()
    daily = g.groupby("date").agg(pnl=("pnl", "sum"), n=("pnl", "size"))
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max()), fill_value=0) if len(daily) else daily
    for d in (7, 14, 30):
        p, n = daily["pnl"].rolling(d).sum(), daily["n"].rolling(d).sum()
        m = pd.DataFrame({f"pnl_{d}d": p, f"roi_{d}d": p / n.replace(0, np.nan)})
        out = out.merge(m, left_on="date", right_index=True, how="left")
    return out
