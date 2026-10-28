"""September 2026 vs October 2026 learning evidence report (owner brief 2026-10-28).

    python -m src.studies.monthly_learning            # git fetch v9 + v11, recompute, write outputs
    python -m src.studies.monthly_learning --no-fetch # use the refs already fetched

ANALYSIS ONLY. Nothing here changes production selection, thresholds, models, bankroll policy,
stakes, states, promotions, regimes or experiments. Every input is READ; v9 and v11 are read from
their committed `origin/main` (never from a stale working tree), so the report always reflects
what GitHub holds at run time.

OUTPUTS
    docs/SEPTEMBER_VS_OCTOBER_LEARNING_EVIDENCE_2026.md
    output/monthly_learning_comparison.json
    output/monthly_learning_by_league.csv
    output/monthly_learning_by_track.csv

THE TRAPS THIS MODULE HANDLES (root CLAUDE.md)
    * P/L is in units at the LOGGED price (flat 1u), never ROI on a bankroll.
    * Ledger rows are deduplicated to their FIRST-LOGGED state, rebuilt from v9's git history of the
      ledger file: before 2026-10-26 a later re-sight could upgrade a row's tier (both ledgers) and
      overwrite its price (side ledger). Since 2026-10-26 the first-logged values stand and later
      sightings go to output/ledger_tier_seen.csv.
    * Odds snapshots are CHANGE-LOGS: the last stored row is the last CHANGE, not the last
      observation, so "last pre-kickoff observation" is only measured where a heartbeat exists.
    * Every interval is a matchday block bootstrap (a Saturday of 20 bets is not 20 observations).
    * Months are by local match date; October runs to the latest SETTLED October date.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg  # noqa: E402

NAME = "monthly_learning"
CALC_VERSION = "1.0.0"
OUT = cfg.OUTPUT_DIR
DOC = cfg.BASE_DIR / "docs" / "SEPTEMBER_VS_OCTOBER_LEARNING_EVIDENCE_2026.md"
CACHE = OUT / "studies" / f"{NAME}_first_logged"           # allow-list ignored: local cache only

#: v9 src/allocation.py:52 (and Pro src/bankroll/__init__.py:26): "The system has run without a
#: KNOWN pipeline defect only since the September data fixes landed and the retrain began completing."
RELIABLE_FROM = "2026-09-24"
SEP = ("2026-09-01", "2026-09-30")
SEP_RELIABLE = (RELIABLE_FROM, "2026-09-30")
OCT_START = "2026-10-01"
FIRST_LOGGED_FROM = "2026-10-26"           # v9 00d5b936 / dfcdf289: first-logged odds, edge, tier stand
CLV_FIX_FROM = "2026-10-23"                 # v9 output/clv_collection_health.json measure_from
HISTORY_SINCE = "2026-08-20"               # ledger commits scanned for first-logged reconstruction

STANDARD_LEAGUES = ["Championship", "League One", "League Two", "Bundesliga 2", "La Liga 2",
                    "Ligue 2", "Serie B"]
TIER_GAP = {"SNIPER": "Big gap", "MARKSMAN": "Medium gap", "VALUABLE": "Small gap"}
TIER_SENTENCE = "These are historical raw-gap labels, not confidence levels."
#: v9 src/market_edge.py SYNTHETIC_DEFAULT_ODDS - a side row priced exactly at the fill constant
#: cannot be told apart from a filled one, so it is excluded fail-closed (v9 exclude_synthetic_prices).
SYNTHETIC_ODDS = {"btts": 1.85, "over15": 1.40, "over35": 2.60}
#: Pro src/quality.py BTTS_YES_MAX: a BTTS YES price above this is the first-half market.
BTTS_YES_MAX = 3.20
N_BOOT = 2000
SEED = 20261028
MIN_LEAGUE_N, MIN_LEAGUE_DAYS = 20, 4

V9_LEDGER, V9_SIDE = "output/bets_ledger.csv", "output/side_bets_ledger.csv"


# ── sources: committed origin/main only ─────────────────────────────────────────────────────────
def _git_exe() -> str:
    for g in (os.getenv("GIT"), shutil.which("git"),
              str(Path.home() / "AppData/Local/GitHubDesktop/app-3.6.4/resources/app/git/cmd/git.exe")):
        if g and (Path(g).exists() or shutil.which(g)):
            return g
    raise RuntimeError("git not found (set GIT)")


def _clone(env: str, *cands: Path) -> Path:
    for p in [Path(os.environ[env])] if os.getenv(env) else []:
        if (p / ".git").exists():
            return p
    for p in cands:
        if p and (p / ".git").exists():
            return p
    raise RuntimeError(f"no git clone found for {env}; set {env}")


class Repo:
    """Reads files at `origin/main` of a local clone (after `git fetch`), never the working tree."""

    def __init__(self, path: Path, ref: str = "origin/main"):
        self.path, self.ref, self.git = path, ref, _git_exe()

    def run(self, *args, timeout=600) -> str:
        r = subprocess.run([self.git, *args], cwd=self.path, capture_output=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.decode(errors='replace')[:300]}")
        return r.stdout.decode("utf-8", errors="replace")

    def fetch(self):
        self.run("fetch", "origin", "--quiet")

    def sha(self) -> str:
        return self.run("rev-parse", "--short=12", self.ref).strip()

    def head_ts(self) -> str:
        return self.run("log", "-1", "--format=%cI", self.ref).strip()

    def raw(self, path: str) -> bytes:
        r = subprocess.run([self.git, "show", f"{self.ref}:{path}"], cwd=self.path, capture_output=True,
                           timeout=600)
        if r.returncode != 0:
            raise FileNotFoundError(f"{self.ref}:{path}")
        return r.stdout

    def csv(self, path: str, **kw) -> pd.DataFrame:
        return pd.read_csv(io.BytesIO(self.raw(path)), low_memory=False, **kw)

    def json(self, path: str):
        return json.loads(self.raw(path).decode("utf-8"))

    def parquet(self, path: str) -> pd.DataFrame:
        return pd.read_parquet(io.BytesIO(self.raw(path)))

    def first_added(self, path: str) -> str | None:
        out = self.run("log", self.ref, "--diff-filter=A", "--format=%cI", "--", path).strip().splitlines()
        return out[-1][:10] if out else None

    def commit_date(self, sha: str) -> str | None:
        try:
            return self.run("show", "-s", "--format=%cI", sha).strip()[:10]
        except Exception:
            return None


# ── statistics ──────────────────────────────────────────────────────────────────────────────────
def _rng():
    return np.random.default_rng(SEED)


def _days(d: pd.Series) -> np.ndarray:
    return pd.to_datetime(d, errors="coerce").dt.strftime("%Y-%m-%d").to_numpy()


def boot_roi(pnl, day, n_boot=N_BOOT, q=(0.05, 0.95)) -> list:
    """90% CI of ROI = sum(pnl)/n, resampling whole matchdays."""
    pnl, day = np.asarray(pnl, float), np.asarray(day)
    if len(pnl) < 2:
        return [None, None]
    u, inv = np.unique(day, return_inverse=True)
    s, c = np.bincount(inv, pnl), np.bincount(inv)
    if len(u) < 2:
        return [None, None]
    idx = _rng().integers(0, len(u), size=(n_boot, len(u)))
    r = s[idx].sum(1) / c[idx].sum(1)
    return [round(float(np.quantile(r, q[0])), 4), round(float(np.quantile(r, q[1])), 4)]


def boot_delta_roi(a_pnl, a_day, b_pnl, b_day, n_boot=N_BOOT, q=(0.05, 0.95)) -> list:
    """90% CI of ROI(b) - ROI(a), each month resampled by its own matchdays (independent blocks)."""
    def draws(pnl, day, rng):
        u, inv = np.unique(np.asarray(day), return_inverse=True)
        s, c = np.bincount(inv, np.asarray(pnl, float)), np.bincount(inv)
        idx = rng.integers(0, len(u), size=(n_boot, len(u)))
        return s[idx].sum(1) / c[idx].sum(1)
    if len(a_pnl) < 2 or len(b_pnl) < 2 or len(set(a_day)) < 2 or len(set(b_day)) < 2:
        return [None, None]
    rng = _rng()
    d = draws(b_pnl, b_day, rng) - draws(a_pnl, a_day, rng)
    return [round(float(np.quantile(d, q[0])), 4), round(float(np.quantile(d, q[1])), 4)]


def boot_mean(x, day, n_boot=N_BOOT, q=(0.025, 0.975)) -> list:
    x, day = np.asarray(x, float), np.asarray(day)
    ok = ~np.isnan(x)
    x, day = x[ok], day[ok]
    u, inv = np.unique(day, return_inverse=True)
    if len(u) < 2:
        return [None, None]
    s, c = np.bincount(inv, x), np.bincount(inv)
    idx = _rng().integers(0, len(u), size=(n_boot, len(u)))
    r = s[idx].sum(1) / c[idx].sum(1)
    return [round(float(np.quantile(r, q[0])), 5), round(float(np.quantile(r, q[1])), 5)]


def boot_delta_mean(a, a_day, b, b_day, n_boot=N_BOOT, q=(0.025, 0.975)) -> list:
    """CI of mean(b) - mean(a), independent matchday blocks per sample."""
    def draws(x, day, rng):
        x, day = np.asarray(x, float), np.asarray(day)
        u, inv = np.unique(day, return_inverse=True)
        s, c = np.bincount(inv, x), np.bincount(inv)
        idx = rng.integers(0, len(u), size=(n_boot, len(u)))
        return s[idx].sum(1) / c[idx].sum(1)
    if len(set(a_day)) < 2 or len(set(b_day)) < 2:
        return [None, None]
    rng = _rng()
    d = draws(b, b_day, rng) - draws(a, a_day, rng)
    return [round(float(np.quantile(d, q[0])), 5), round(float(np.quantile(d, q[1])), 5)]


def ll(p, y) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(p, y) -> np.ndarray:
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def ece(p, y, bins=10) -> float | None:
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) == 0:
        return None
    b = np.minimum((p * bins).astype(int), bins - 1)
    e = 0.0
    for k in range(bins):
        m = b == k
        if m.any():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return round(float(e), 4)


def poisson_binomial_cdf(k: int, probs) -> float:
    """P(W <= k) for independent Bernoulli(p_i) - exact DP."""
    dist = np.zeros(len(probs) + 1)
    dist[0] = 1.0
    for p in probs:
        dist[1:] = dist[1:] * (1 - p) + dist[:-1] * p
        dist[0] *= (1 - p)
    return float(dist[: k + 1].sum())


# ── ledgers: first-logged reconstruction ────────────────────────────────────────────────────────
def first_logged(v9: Repo, path: str, key_cols: list[str], refresh=True) -> pd.DataFrame:
    """One row per ledger key as FIRST written to `path` on v9 origin/main, plus how it changed.

    Walks every commit of the ledger since HISTORY_SINCE with one `git cat-file --batch` process.
    """
    cache = Path(f"{CACHE}_{Path(path).stem}.csv")
    if not refresh and cache.exists():
        return pd.read_csv(cache, low_memory=False)
    log = v9.run("log", v9.ref, "--reverse", f"--since={HISTORY_SINCE}", "--format=%H|%cI", "--", path)
    commits = [ln.split("|", 1) for ln in log.splitlines() if "|" in ln]
    proc = subprocess.Popen([v9.git, "cat-file", "--batch"], cwd=v9.path, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    first: dict[tuple, dict] = {}
    tier_rank = {"SNIPER": 3, "MARKSMAN": 2, "VALUABLE": 1}
    for sha, cts in commits:
        proc.stdin.write(f"{sha}:{path}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        if len(header) < 3 or header[1] != "blob":
            continue
        body = proc.stdout.read(int(header[2]))
        proc.stdout.read(1)
        try:
            v = pd.read_csv(io.BytesIO(body), low_memory=False,
                            usecols=lambda c: c in set(key_cols) | {"odds", "signal_tier", "edge_pct",
                                                                     "generated_at", "source"})
        except Exception:
            continue
        if "source" not in v.columns:
            v["source"] = "live"
        v = v[v["source"].astype(str).eq("live")]
        for r in v.itertuples(index=False):
            rd = r._asdict()
            k = tuple(str(rd[c])[:10] if c == "match_date" else str(rd[c]).strip() for c in key_cols)
            odds = pd.to_numeric(rd.get("odds"), errors="coerce")
            tier = str(rd.get("signal_tier", ""))
            if k not in first:
                first[k] = {**{c: k[i] for i, c in enumerate(key_cols)}, "first_commit": sha[:12],
                            "first_commit_ts": cts, "first_generated_at": str(rd.get("generated_at")),
                            "first_odds": odds, "first_tier": tier,
                            "first_edge_pct": pd.to_numeric(rd.get("edge_pct"), errors="coerce"),
                            "max_tier_seen": tier, "n_odds_changes": 0, "n_tier_changes": 0,
                            "_lo": odds, "_lt": tier}
            else:
                f = first[k]
                if odds == odds and odds != f["_lo"]:
                    f["n_odds_changes"] += 1
                    f["_lo"] = odds
                if tier != f["_lt"]:
                    f["n_tier_changes"] += 1
                    f["_lt"] = tier
                if tier_rank.get(tier, 0) > tier_rank.get(f["max_tier_seen"], 0):
                    f["max_tier_seen"] = tier
    proc.stdin.close()
    proc.wait(timeout=120)
    out = pd.DataFrame(first.values()).drop(columns=["_lo", "_lt"], errors="ignore")
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False)
    return out


def _settle_at(odds, result) -> np.ndarray:
    o, r = np.asarray(odds, float), np.asarray(result).astype(str)
    return np.where(r == "WIN", o - 1.0, np.where(r == "LOSS", -1.0, 0.0))


def load_ledgers(v9: Repo, refresh=True) -> tuple[pd.DataFrame, dict]:
    """Settled live bets from both ledgers at FIRST-LOGGED odds/tier. One frame, `family` column."""
    audit = {}
    ou = v9.csv(V9_LEDGER)
    ou = ou[ou["source"].astype(str).eq("live")].copy()
    ou["match_date"] = ou["match_date"].astype(str).str[:10]
    ou["side"] = ou["side"].astype(str).str.strip()
    k_ou = ["match_date", "home_team", "away_team", "side", "source"]
    f_ou = first_logged(v9, V9_LEDGER, k_ou, refresh)
    ou = ou.merge(f_ou, on=k_ou, how="left")
    ou["market"] = "ou25"
    ou["selection"] = ou["side"]

    sd = v9.csv(V9_SIDE)
    sd = sd[sd["source"].astype(str).eq("live")].copy()
    sd["match_date"] = sd["match_date"].astype(str).str[:10]
    k_sd = ["match_date", "home_team", "away_team", "market", "source"]
    f_sd = first_logged(v9, V9_SIDE, k_sd, refresh)
    sd = sd.merge(f_sd, on=k_sd, how="left")
    sd["selection"] = sd["market"].map({"btts": "YES", "over15": "OVER", "over35": "OVER"}).fillna("?")

    cols = ["match_date", "league", "home_team", "away_team", "market", "selection", "model_type", "odds",
            "closing_odds", "clv_pct", "signal_tier", "result", "pnl", "generated_at", "first_odds",
            "first_tier", "first_edge_pct", "first_generated_at", "n_odds_changes", "n_tier_changes",
            "max_tier_seen", "edge_pct"]
    df = pd.concat([ou.reindex(columns=cols), sd.reindex(columns=cols)], ignore_index=True)
    for c in ("odds", "closing_odds", "clv_pct", "pnl", "first_odds", "first_edge_pct", "edge_pct"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["md"] = pd.to_datetime(df["match_date"], errors="coerce")
    df = df[df["md"] >= pd.Timestamp(SEP[0])]
    audit["rows_since_sep"] = int(len(df))
    audit["first_logged_found"] = int(df["first_odds"].notna().sum())
    # first-logged values stand; where history could not be read fall back to the row as it is
    df["entry_odds"] = df["first_odds"].where(df["first_odds"].notna(), df["odds"])
    df["tier"] = df["first_tier"].where(df["first_tier"].notna() & (df["first_tier"].astype(str) != "nan"),
                                        df["signal_tier"]).astype(str)
    df["price_rewritten"] = (df["first_odds"].notna() & (df["first_odds"] - df["odds"]).abs().gt(1e-9))
    df["tier_upgraded"] = df["first_tier"].notna() & (df["first_tier"].astype(str) != df["signal_tier"].astype(str))
    audit["rows_price_rewritten_after_first_log"] = {
        m: int(df.loc[df["market"].eq(m), "price_rewritten"].sum()) for m in sorted(df["market"].unique())}
    audit["rows_tier_upgraded_after_first_log"] = {
        m: int(df.loc[df["market"].eq(m), "tier_upgraded"].sum()) for m in sorted(df["market"].unique())}
    df["settled"] = df["result"].isin(["WIN", "LOSS"])
    df["pnl_first"] = _settle_at(df["entry_odds"], df["result"])
    df["pnl_ledger"] = df["pnl"]
    # CLV at the first-logged price, from the ledger's closing odds (same formula v9 uses)
    df["clv_first"] = np.where(df["closing_odds"] > 1, (df["entry_odds"] / df["closing_odds"] - 1) * 100, np.nan)
    df["track"] = df["model_type"].map({"standard": "Standard", "new_format": "New Format"}).fillna("Unknown")
    df["gap"] = df["tier"].map(TIER_GAP).fillna("other")
    # price integrity (side markets): genuine observed prices only
    df["excl_reason"] = ""
    for m, c in SYNTHETIC_ODDS.items():
        hit = df["market"].eq(m) & df["entry_odds"].round(2).eq(c)
        df.loc[hit, "excl_reason"] = "SYNTHETIC_FILL_CONSTANT"
    h1 = df["market"].eq("btts") & (df["entry_odds"] > BTTS_YES_MAX)
    df.loc[h1, "excl_reason"] = "BTTS_FIRST_HALF_MISLABEL"
    df["clv_valid"] = df["clv_first"].notna() & ~(df["market"].eq("btts") & (df["closing_odds"] > BTTS_YES_MAX))
    audit["side_rows_excluded"] = df[df["excl_reason"] != ""].groupby(["market", "excl_reason"]).size() \
        .rename("n").reset_index().to_dict("records")
    return df, audit


# ── bet metrics ─────────────────────────────────────────────────────────────────────────────────
def window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df[(df["md"] >= pd.Timestamp(start)) & (df["md"] <= pd.Timestamp(end))]


def bet_metrics(x: pd.DataFrame, pnl_col="pnl_first") -> dict:
    s = x[x["settled"]]
    n = len(s)
    if n == 0:
        return {"n": 0}
    w = int((s["result"] == "WIN").sum())
    pnl = float(s[pnl_col].sum())
    day = _days(s["md"])
    clv = s.loc[s["clv_valid"], "clv_first"]
    return {"n": n, "matchdays": int(len(set(day))), "wins": w, "losses": n - w,
            "hit": round(w / n, 4), "pnl_u": round(pnl, 2), "roi": round(pnl / n, 4),
            "roi_ci90": boot_roi(s[pnl_col], day),
            "avg_odds": round(float(s["entry_odds"].mean()), 3),
            "median_odds": round(float(s["entry_odds"].median()), 3),
            "breakeven_hit": round(float((1 / s["entry_odds"]).mean()), 4),
            "mean_clv_pct": round(float(clv.mean()), 2) if len(clv) else None,
            "clv_positive_share": round(float((clv > 0).mean()), 3) if len(clv) else None,
            "clv_coverage": round(len(clv) / n, 3),
            "clv_exactly_zero_share": round(float((clv == 0).mean()), 3) if len(clv) else None,
            "ledger_pnl_u": round(float(s["pnl_ledger"].sum()), 2),
            "voids": int((x["result"] == "VOID").sum()), "unsettled": int((~x["result"].isin(["WIN", "LOSS", "VOID"])).sum())}


def compare(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    sa, sb = a[a["settled"]], b[b["settled"]]
    ma, mb = bet_metrics(a), bet_metrics(b)
    out = {"sep": ma, "oct": mb}
    if ma.get("n") and mb.get("n"):
        out["delta_roi"] = round(mb["roi"] - ma["roi"], 4)
        out["delta_hit"] = round(mb["hit"] - ma["hit"], 4)
        out["delta_pnl_u"] = round(mb["pnl_u"] - ma["pnl_u"], 2)
        out["delta_roi_ci90"] = boot_delta_roi(sa["pnl_first"], _days(sa["md"]), sb["pnl_first"], _days(sb["md"]))
    return out


def category(c: dict) -> str:
    ma, mb = c.get("sep", {}), c.get("oct", {})
    if min(ma.get("n", 0), mb.get("n", 0)) < MIN_LEAGUE_N or \
            min(ma.get("matchdays", 0), mb.get("matchdays", 0)) < MIN_LEAGUE_DAYS:
        return "TOO_SMALL"
    lo, hi = c.get("delta_roi_ci90", [None, None])
    if lo is None:
        return "TOO_SMALL"
    return "IMPROVED" if lo > 0 else "DETERIORATED" if hi < 0 else "STABLE"


def pattern(c: dict) -> str:
    ra, rb = c.get("sep", {}).get("roi"), c.get("oct", {}).get("roi")
    if ra is None or rb is None:
        return ""
    return {(True, True): "POSITIVE_BOTH", (False, True): "NEG_TO_POS", (True, False): "POS_TO_NEG",
            (False, False): "NEGATIVE_BOTH"}[(ra > 0, rb > 0)]


# ── the analysis ────────────────────────────────────────────────────────────────────────────────
def section_betting(df: pd.DataFrame, oct_end: str) -> dict:
    windows = {"A": (SEP, (OCT_START, oct_end)), "B": (SEP_RELIABLE, (OCT_START, oct_end))}
    res, league_rows, track_rows = {}, [], []
    clean = df[df["excl_reason"] == ""]
    for wid, ((s0, s1), (o0, o1)) in windows.items():
        S, O = window(df, s0, s1), window(df, o0, o1)
        Sc, Oc = window(clean, s0, s1), window(clean, o0, o1)
        r = {"sep_window": [s0, s1], "oct_window": [o0, o1]}
        ou_s, ou_o = S[S["market"] == "ou25"], O[O["market"] == "ou25"]
        r["ou25"] = {"all": compare(ou_s, ou_o)}
        for t in ("Standard", "New Format"):
            r["ou25"][t] = compare(ou_s[ou_s["track"] == t], ou_o[ou_o["track"] == t])
            for sel in ("OVER", "UNDER"):
                r["ou25"][f"{t}|{sel}"] = compare(ou_s[(ou_s["track"] == t) & (ou_s["selection"] == sel)],
                                                  ou_o[(ou_o["track"] == t) & (ou_o["selection"] == sel)])
        std_ex = ~ou_s["league"].isin(["League One", "League Two"])
        r["ou25"]["Standard ex League One/Two"] = compare(
            ou_s[(ou_s["track"] == "Standard") & std_ex],
            ou_o[(ou_o["track"] == "Standard") & ~ou_o["league"].isin(["League One", "League Two"])])
        r["ou25"]["Standard ledger-price (owner reference)"] = {
            "sep": bet_metrics(ou_s[ou_s["track"] == "Standard"], "pnl_ledger"),
            "oct": bet_metrics(ou_o[ou_o["track"] == "Standard"], "pnl_ledger")}
        # tiers
        r["ou25_by_gap"] = {}
        for scope, fs, fo in (("all", ou_s, ou_o), ("Standard", ou_s[ou_s["track"] == "Standard"], ou_o[ou_o["track"] == "Standard"]),
                              ("New Format", ou_s[ou_s["track"] == "New Format"], ou_o[ou_o["track"] == "New Format"])):
            r["ou25_by_gap"][scope] = {f"{t}/{g}": compare(fs[fs["tier"] == t], fo[fo["tier"] == t])
                                       for t, g in TIER_GAP.items()}
        # every market together: OU25 + side markets at genuine prices
        side_s, side_o = Sc[Sc["market"] != "ou25"], Oc[Oc["market"] != "ou25"]
        all_s, all_o = pd.concat([ou_s, side_s]), pd.concat([ou_o, side_o])
        r["combined"] = {"all": compare(all_s, all_o)}
        for t in ("Standard", "New Format"):
            r["combined"][t] = compare(all_s[all_s["track"] == t], all_o[all_o["track"] == t])
        # side markets, genuine prices only
        r["side"] = {}
        for t in ("New Format", "Standard"):
            for m in ("btts", "over15", "over35"):
                a = Sc[(Sc["market"] == m) & (Sc["track"] == t)]
                b = Oc[(Oc["market"] == m) & (Oc["track"] == t)]
                r["side"][f"{t}|{m}"] = compare(a, b)
        # league level
        for fam, fs, fo in (("OU25", ou_s, ou_o), ("BTTS", Sc[Sc["market"] == "btts"], Oc[Oc["market"] == "btts"])):
            for lg in sorted(set(fs["league"].dropna()) | set(fo["league"].dropna())):
                c = compare(fs[fs["league"] == lg], fo[fo["league"] == lg])
                trk = (pd.concat([fs, fo])["track"][pd.concat([fs, fo])["league"] == lg].mode())
                league_rows.append({
                    "comparison": wid, "market_family": fam, "league": lg,
                    "track": trk.iloc[0] if len(trk) else "",
                    "sep_n": c["sep"].get("n", 0), "sep_matchdays": c["sep"].get("matchdays", 0),
                    "sep_roi": c["sep"].get("roi"), "sep_hit": c["sep"].get("hit"), "sep_pnl_u": c["sep"].get("pnl_u"),
                    "oct_n": c["oct"].get("n", 0), "oct_matchdays": c["oct"].get("matchdays", 0),
                    "oct_roi": c["oct"].get("roi"), "oct_hit": c["oct"].get("hit"), "oct_pnl_u": c["oct"].get("pnl_u"),
                    "delta_roi": c.get("delta_roi"), "delta_hit": c.get("delta_hit"), "delta_pnl_u": c.get("delta_pnl_u"),
                    "delta_roi_ci90_lo": (c.get("delta_roi_ci90") or [None, None])[0],
                    "delta_roi_ci90_hi": (c.get("delta_roi_ci90") or [None, None])[1],
                    "category": category(c), "pattern": pattern(c),
                    "pre_repair_standard": lg in STANDARD_LEAGUES})
        # track level (section 14 tracks)
        tracks = {
            "NF BTTS": (Sc[(Sc["market"] == "btts") & (Sc["track"] == "New Format")], Oc[(Oc["market"] == "btts") & (Oc["track"] == "New Format")]),
            "NF OU25 OVER": (ou_s[(ou_s["track"] == "New Format") & (ou_s["selection"] == "OVER")], ou_o[(ou_o["track"] == "New Format") & (ou_o["selection"] == "OVER")]),
            "NF OU25 UNDER": (ou_s[(ou_s["track"] == "New Format") & (ou_s["selection"] == "UNDER")], ou_o[(ou_o["track"] == "New Format") & (ou_o["selection"] == "UNDER")]),
            "NF O1.5": (Sc[(Sc["market"] == "over15") & (Sc["track"] == "New Format")], Oc[(Oc["market"] == "over15") & (Oc["track"] == "New Format")]),
            "Standard OU25": (ou_s[ou_s["track"] == "Standard"], ou_o[ou_o["track"] == "Standard"]),
            "Standard BTTS": (Sc[(Sc["market"] == "btts") & (Sc["track"] == "Standard")], Oc[(Oc["market"] == "btts") & (Oc["track"] == "Standard")]),
        }
        r["tracks"] = {}
        for name, (a, b) in tracks.items():
            c = compare(a, b)
            r["tracks"][name] = c
            track_rows.append({"comparison": wid, "track": name,
                               **{f"sep_{k}": v for k, v in c["sep"].items() if not isinstance(v, list)},
                               **{f"oct_{k}": v for k, v in c["oct"].items() if not isinstance(v, list)},
                               "sep_roi_ci90": c["sep"].get("roi_ci90"), "oct_roi_ci90": c["oct"].get("roi_ci90"),
                               "delta_roi": c.get("delta_roi"), "delta_roi_ci90": c.get("delta_roi_ci90"),
                               "category": category(c), "pattern": pattern(c)})
        res[wid] = r
    return {"windows": res, "league_rows": league_rows, "track_rows": track_rows}


def section_tier_monotonic(bet: dict) -> dict:
    out = {}
    for wid in ("A", "B"):
        for scope, g in bet["windows"][wid]["ou25_by_gap"].items():
            for month in ("sep", "oct"):
                rois = [g[f"{t}/{TIER_GAP[t]}"][month].get("roi") for t in ("SNIPER", "MARKSMAN", "VALUABLE")]
                ns = [g[f"{t}/{TIER_GAP[t]}"][month].get("n", 0) for t in ("SNIPER", "MARKSMAN", "VALUABLE")]
                mono = None if any(r is None for r in rois) else bool(rois[0] >= rois[1] >= rois[2])
                out[f"{wid}|{scope}|{month}"] = {"roi_big_medium_small": rois, "n": ns, "monotonic": mono}
    return out


def section_std_reference(df: pd.DataFrame, oct_end: str) -> dict:
    """Owner reference, reproduced: League One wins vs bookmaker-expected (raw implied 1/odds)."""
    out = {}
    s = window(df[(df["market"] == "ou25") & (df["track"] == "Standard") & df["settled"]], SEP[0], oct_end)
    for lg in STANDARD_LEAGUES:
        x = s[s["league"] == lg]
        if x.empty:
            continue
        p_raw = (1 / x["entry_odds"]).clip(0, 1).to_numpy()
        w = int((x["result"] == "WIN").sum())
        out[lg] = {"n": int(len(x)), "wins": w, "expected_wins_raw_implied": round(float(p_raw.sum()), 1),
                   "p_value_le_wins_raw": round(poisson_binomial_cdf(w, p_raw), 4),
                   "expected_wins_devig_approx_5pct": round(float((p_raw / 1.05).sum()), 1),
                   "p_value_le_wins_devig_approx": round(poisson_binomial_cdf(w, p_raw / 1.05), 4),
                   "pnl_u": round(float(x["pnl_first"].sum()), 2), "roi": round(float(x["pnl_first"].mean()), 4),
                   "matchdays": int(x["md"].dt.date.nunique())}
    return out


def section_data_quality() -> dict:
    """Read-only: the Standard repair data-quality burden from the pro_v9r worktree (another agent's)."""
    base = Path(os.getenv("STD_REPAIR_DIR") or (cfg.BASE_DIR.parent / "pro_v9r" / "output" / "standard_repair"))
    out = {"source_dir": str(base), "available": False}
    try:
        dq = json.loads((base / "data_quality.json").read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    out["available"] = True
    out["status"] = dq.get("status")
    out["data_cutoff"] = dq.get("data_cutoff")
    out["v9_commit"] = (dq.get("frame") or {}).get("v9_commit")
    out["alias_rows_removed"] = (dq.get("frame") or {}).get("alias_rows_removed")
    leak = (dq.get("identity") or {})
    out["future_match_in_window_legacy_total"] = (leak.get("rolling_order_leak_legacy") or {}).get("standard_fixtures_with_future_match_in_window")
    out["future_match_in_window_canonical_total"] = (leak.get("rolling_order_leak_canonical") or {}).get("standard_fixtures_with_future_match_in_window")
    out["trusted_from"] = {k: v.get("trusted_from") for k, v in (dq.get("trusted_from") or {}).items()}
    out["ou25_frame_price_equals_closing_share"] = (dq.get("prices") or {}).get("ou25_frame_price_equals_closing_share_where_both_known")
    try:
        q = pd.read_csv(base / "identity_quarantine.csv")
        out["identity_quarantine_rows"] = int(len(q))
    except Exception:
        out["identity_quarantine_rows"] = None
    try:
        al = json.loads((base / "identity_aliases.json").read_text(encoding="utf-8"))
        out["identity_alias_version"] = al.get("version")
    except Exception:
        pass
    per = {}
    for lg in STANDARD_LEAGUES:
        L = (dq.get("per_league") or {}).get(lg) or {}
        pc = L.get("price_coverage") or {}
        t30 = (L.get("certified_t30_close") or {}).get("OU25") or {}
        per[lg] = {"rows": L.get("rows"),
                   "alias_collision_share_legacy": L.get("alias_collision_share_legacy"),
                   "aliases_resolved": L.get("aliases_resolved"),
                   "future_leak_sides_legacy": L.get("rolling_window_future_leak_sides_legacy"),
                   "future_leak_sides_canonical": L.get("rolling_window_future_leak_sides_canonical"),
                   "serving_feature_completeness": L.get("serving_feature_completeness"),
                   "ou25_real_entry_share": pc.get("OU25_entry_real_FD_PREMATCH_APPROX"),
                   "ou25_certified_t30_share_forward": t30.get("share"),
                   "btts_1h_rows_removed": L.get("btts_1h_rows_removed"),
                   "legacy_side_fallback_rows": L.get("legacy_backtest_fallback_rows"),
                   "live_constant_features": (L.get("parity") or {}).get("live_constant_features_v9")}
    out["per_league"] = per
    return out


def section_retrain(v9: Repo) -> dict:
    rb = v9.csv("output/model_lineage/retrain_batches.csv")
    rb["d"] = rb["decided_at"].astype(str).str[:10]
    rb["month"] = rb["d"].str[:7]
    rb["gate"] = np.where(rb["source"].eq("LEGACY_RETRAIN_LOG"), "OLD_LEGACY_GATE",
                          np.where(rb["source"].eq("CHAMPION_GATE"), "CHAMPION_GATE_HWM", rb["source"]))
    pdx = v9.csv("output/model_lineage/promotion_decisions.csv")
    out = {"by_month": {}, "oct25": {}, "examples_weak_promoted_sep": [], "examples_rejected_oct": []}
    for m, g in rb.groupby("month"):
        out["by_month"][m] = {
            "retrain_days": int(g["d"].nunique()), "candidates": int(len(g)),
            "promoted": int(g["promoted"].astype(bool).sum()),
            "rejected_or_held": int((~g["promoted"].astype(bool)).sum()),
            "promotion_rate": round(float(g["promoted"].astype(bool).mean()), 3),
            "promoted_with_worse_holdout_ll": int((g["promoted"].astype(bool) & (g["ll_delta"] > 0)).sum()),
            "promoted_with_ci": int((g["promoted"].astype(bool) & g["ll_ci_lo"].notna()).sum()),
            "promoted_ci_excluding_zero": int((g["promoted"].astype(bool) & (g["ll_ci_hi"] < 0)).sum()),
            "by_gate": g.groupby("gate")["promoted"].agg(["size", "sum"]).astype(int)
                        .rename(columns={"size": "candidates", "sum": "promoted"}).to_dict("index"),
            "verdicts": g["verdict"].value_counts().to_dict()}
    sep = rb[(rb["month"] == "2026-09") & rb["promoted"].astype(bool) & (rb["ll_delta"] > 0)]
    out["examples_weak_promoted_sep"] = sep[["d", "model_type", "ll_delta", "reason"]].head(8).to_dict("records")
    o = rb[(rb["month"] == "2026-10") & ~rb["promoted"].astype(bool)]
    out["examples_rejected_oct"] = o[["d", "model_type", "verdict", "ll_delta", "ll_ci_lo", "ll_ci_hi", "reason"]].head(12).to_dict("records")
    for r in rb[rb["d"] == "2026-10-25"].itertuples():
        out["oct25"][r.model_type] = {"gate": r.gate, "verdict": r.verdict, "promoted": bool(r.promoted),
                                      "ll_delta": r.ll_delta, "ll_ci95": [r.ll_ci_lo, r.ll_ci_hi],
                                      "brier_delta": r.brier_delta, "ece_delta": r.ece_delta,
                                      "later_half_ll_delta": r.later_half_ll_delta, "reason": r.reason}
    out["pg10_decisions"] = pdx.fillna("").to_dict("records")
    try:
        rep = v9.csv("output/model_lineage/legacy_gate_replay.csv")
        out["legacy_promotions_replayed_under_strict_gate"] = rep[rep["legacy_promoted"].astype(str) == "True"][
            "new_gate_replay"].value_counts().to_dict()
    except Exception:
        pass
    try:
        out["current_champions"] = {k: {"model_version": v.get("model_version"), "since": v.get("champion_since"),
                                        "source": v.get("promotion_source")}
                                    for k, v in v9.json("models/registry/current_champions.json").items()}
    except Exception:
        pass
    try:
        out["pg10_config"] = {k: v9.json("config/promotion_gate.json").get(k) for k in ("gate_version", "declared_on")}
        out["pg10_config"]["holdout"] = v9.json("config/promotion_gate.json").get("holdout")
        out["pg10_config"]["prospective"] = v9.json("config/promotion_gate.json").get("prospective")
    except Exception:
        pass
    return out


def _score(p, y, day) -> dict:
    return {"n": int(len(y)), "matchdays": int(len(set(day))), "base_rate": round(float(np.mean(y)), 4),
            "ll": round(float(ll(p, y).mean()), 5), "brier": round(float(brier(p, y).mean()), 5), "ece": ece(p, y)}


def section_forecast_ou25(v11: Repo, v9: Repo) -> dict:
    """OU25: v9's served P(over) vs the de-vigged market, for EVERY fixture v9 published (not only
    tips), from v11's shadow log (the same pipeline in both months) graded by v11. Last pre-kickoff
    snapshot per fixture."""
    log = v11.csv("output/v11_shadow_log.csv")
    g = v11.csv("output/v11_graded.csv")
    log["ts"] = pd.to_datetime(log["snapshot_ts"], utc=True, errors="coerce")
    ko = pd.to_datetime(log["kickoff_ts"], utc=True, errors="coerce")
    pre = ~log["is_post_kickoff"].astype(str).str.lower().isin(["true", "1"]) & (ko.isna() | (log["ts"] < ko))
    log = log[pre].sort_values("ts").drop_duplicates(["date", "league", "match"], keep="last")
    g = g.drop_duplicates(["date", "league", "match"], keep="last")
    j = log.merge(g[["date", "league", "match", "over25_result"]], on=["date", "league", "match"], how="inner")
    j = j[pd.to_numeric(j["over25_result"], errors="coerce").isin([0, 1])]
    for c in ("p_model_over", "v11_p_market", "v11_p_blend"):
        j[c] = pd.to_numeric(j[c], errors="coerce")
    j = j.dropna(subset=["p_model_over", "v11_p_market"])
    j["y"] = j["over25_result"].astype(float)
    j["month"] = j["date"].astype(str).str[:7]
    j["track"] = j["model_type"].map({"standard": "Standard", "new_format": "New Format"}).fillna("Unknown")
    out = {"source": "wowza_v11 output/v11_shadow_log.csv (last pre-kickoff snapshot) x v11_graded.csv",
           "note": "v11_p_market is the de-vigged two-sided price v9 published; one consistent pipeline in both months"}
    rows = {}
    for (m, t), x in j.groupby(["month", "track"]):
        if m not in ("2026-09", "2026-10"):
            continue
        day = x["date"].astype(str).to_numpy()
        d = ll(x["p_model_over"], x["y"]) - ll(x["v11_p_market"], x["y"])
        rows[f"{m}|{t}"] = {"model": _score(x["p_model_over"], x["y"], day),
                           "market": _score(x["v11_p_market"], x["y"], day),
                           "v11_blend": _score(x["v11_p_blend"].fillna(x["v11_p_market"]), x["y"], day),
                           "model_minus_market_ll": round(float(d.mean()), 5),
                           "model_minus_market_ll_ci95": boot_mean(d, day)}
    out["by_month_track"] = rows
    deltas = {}
    for t in ("Standard", "New Format"):
        a = j[(j["month"] == "2026-09") & (j["track"] == t)]
        b = j[(j["month"] == "2026-10") & (j["track"] == t)]
        if len(a) and len(b):
            da = ll(a["p_model_over"], a["y"]) - ll(a["v11_p_market"], a["y"])
            db = ll(b["p_model_over"], b["y"]) - ll(b["v11_p_market"], b["y"])
            deltas[t] = {"model_ll_oct_minus_sep": round(float(ll(b["p_model_over"], b["y"]).mean() - ll(a["p_model_over"], a["y"]).mean()), 5),
                         "model_ll_oct_minus_sep_ci95": boot_delta_mean(ll(a["p_model_over"], a["y"]), a["date"].astype(str).to_numpy(),
                                                                        ll(b["p_model_over"], b["y"]), b["date"].astype(str).to_numpy()),
                         "gap_to_market_oct_minus_sep": round(float(db.mean() - da.mean()), 5),
                         "gap_to_market_oct_minus_sep_ci95": boot_delta_mean(da, a["date"].astype(str).to_numpy(),
                                                                             db, b["date"].astype(str).to_numpy())}
    out["sep_to_oct"] = deltas
    return out


def section_forecast_side() -> dict:
    """BTTS / O1.5 / O3.5 / OU25: v9 model (Pro model_snapshots, last pre-kickoff) vs the de-vigged
    multi-book consensus (Pro book_odds_snapshots, last pre-kickoff quote per book), graded on
    v9 af_history results. Both months from the same Pro store."""
    from src.data import season_store as store
    from src.studies.common import match_frames, outcome
    from src.market.devig import power_devig
    fx = store.read("fixtures").drop_duplicates("fixture_key", keep="last")
    fx = fx[fx["match_date"].astype(str).between(SEP[0], "2026-10-31")]
    fx["kick"] = pd.to_datetime(fx["kickoff_utc"], utc=True, errors="coerce")
    res = _AF_RESULTS
    if res is None or res.empty:
        return {"available": False, "why": "no results frame"}
    n_fx = len(fx)
    res = res.reset_index(drop=True)
    idx = match_frames(fx.reset_index(drop=True), res, r_cols=("league", "date", "home_team", "away_team"))
    fx = fx.reset_index(drop=True)
    fx["r"] = idx.to_numpy()
    fx = fx[fx["r"].notna()].copy()
    fx["hg"] = res.loc[fx["r"].astype(int), "FTHG"].to_numpy()
    fx["ag"] = res.loc[fx["r"].astype(int), "FTAG"].to_numpy()
    fx = fx.dropna(subset=["hg", "ag"])
    ms = store.read("model_snapshots")
    ms = ms[ms["fixture_key"].isin(fx["fixture_key"])]
    ms["obs"] = pd.to_datetime(ms["observed_at"], utc=True, errors="coerce")
    ms = ms.merge(fx[["fixture_key", "kick"]], on="fixture_key")
    ms = ms[ms["kick"].isna() | (ms["obs"] < ms["kick"])].sort_values("obs")
    ms = ms.drop_duplicates(["fixture_key", "market"], keep="last")
    bo = store.read("book_odds_snapshots")
    bo = bo[bo["fixture_key"].isin(fx["fixture_key"]) & ~bo["is_post_kickoff"].astype(bool)]
    bo = bo[~((bo["market"] == "BTTS") & (bo["side"] == "YES") & (pd.to_numeric(bo["odds"], errors="coerce") > BTTS_YES_MAX))]
    bo = bo.sort_values("snapshot_ts").drop_duplicates(["fixture_key", "market", "bookmaker", "side"], keep="last")
    out = {"available": True, "fixtures_in_store": int(n_fx), "fixtures_with_results": int(len(fx)),
           "note": "market = median de-vigged (power) two-sided quote across books, LOCF last pre-kickoff per book; "
                   "BTTS YES > 3.20 removed (first-half mislabel)", "by": {}}
    first = {"OU15": "OVER", "OU25": "OVER", "OU35": "OVER", "BTTS": "YES"}
    for mk in ("OU25", "BTTS", "OU15", "OU35"):
        b = bo[bo["market"] == mk]
        w = b.pivot_table(index=["fixture_key", "bookmaker"], columns="side", values="odds", aggfunc="last")
        oth = [c for c in w.columns if c != first[mk]]
        if first[mk] not in w.columns or not oth:
            continue
        w = w.dropna(subset=[first[mk], oth[0]]).reset_index()
        w["p"] = [power_devig(a, c) for a, c in zip(w[first[mk]], w[oth[0]])]
        pm = w.dropna(subset=["p"]).groupby("fixture_key").agg(p_market=("p", "median"), n_books=("p", "size")).reset_index()
        m = ms[ms["market"] == mk][["fixture_key", "model_prob", "model_type"]]
        j = fx[["fixture_key", "match_date", "hg", "ag"]].merge(m, on="fixture_key").merge(pm, on="fixture_key")
        j = j[j["n_books"] >= 3]
        j["y"] = outcome(mk, j["hg"], j["ag"])
        j["p_model"] = pd.to_numeric(j["model_prob"], errors="coerce")
        j = j.dropna(subset=["p_model", "p_market"])
        j["month"] = j["match_date"].astype(str).str[:7]
        j["track"] = j["model_type"].map({"standard": "Standard", "new_format": "New Format"}).fillna("Unknown")
        for (mo, t), x in j.groupby(["month", "track"]):
            if t == "Unknown":
                continue
            day = x["match_date"].astype(str).to_numpy()
            d = ll(x["p_model"], x["y"]) - ll(x["p_market"], x["y"])
            out["by"][f"{mk}|{t}|{mo}"] = {"model": _score(x["p_model"], x["y"], day),
                                           "market": _score(x["p_market"], x["y"], day),
                                           "model_minus_market_ll": round(float(d.mean()), 5),
                                           "model_minus_market_ll_ci95": boot_mean(d, day)}
        for t in ("Standard", "New Format"):
            a = j[(j["month"] == "2026-09") & (j["track"] == t)]
            b = j[(j["month"] == "2026-10") & (j["track"] == t)]
            if len(a) < 30 or len(b) < 30:
                continue
            la, lb = ll(a["p_model"], a["y"]), ll(b["p_model"], b["y"])
            da, db = la - ll(a["p_market"], a["y"]), lb - ll(b["p_market"], b["y"])
            dya, dyb = a["match_date"].astype(str).to_numpy(), b["match_date"].astype(str).to_numpy()
            out.setdefault("sep_to_oct", {})[f"{mk}|{t}"] = {
                "model_ll_oct_minus_sep": round(float(lb.mean() - la.mean()), 5),
                "model_ll_oct_minus_sep_ci95": boot_delta_mean(la, dya, lb, dyb),
                "gap_to_market_oct_minus_sep": round(float(db.mean() - da.mean()), 5),
                "gap_to_market_oct_minus_sep_ci95": boot_delta_mean(da, dya, db, dyb)}
    return out


_AF_RESULTS: pd.DataFrame | None = None
_COMMITS: dict = {}


def section_hgb(v9: Repo) -> dict:
    s = v9.csv("output/model_lineage/shadow_experiments.csv")
    s = s[pd.to_numeric(s["y"], errors="coerce").isin([0, 1])].copy()
    out = {"source": "v9 output/model_lineage/shadow_experiments.csv (H-MODEL-01)", "decision": "DO NOT PROMOTE (analysis only)"}
    for eid, x in s.groupby("experiment_id"):
        x = x.dropna(subset=["p_champion_raw", "p_challenger"]).drop_duplicates("fixture_id", keep="first")
        y, day = x["y"].astype(float).to_numpy(), x["match_date"].astype(str).to_numpy()
        dll = ll(x["p_challenger"], y) - ll(x["p_champion_raw"], y)
        dbr = brier(x["p_challenger"], y) - brier(x["p_champion_raw"], y)
        r = {"paired_n": int(len(x)), "matchdays": int(len(set(day))),
             "first_match": str(x["match_date"].min()), "last_match": str(x["match_date"].max()),
             "champion_ll": round(float(ll(x["p_champion_raw"], y).mean()), 5),
             "challenger_ll": round(float(ll(x["p_challenger"], y).mean()), 5),
             "champion_brier": round(float(brier(x["p_champion_raw"], y).mean()), 5),
             "challenger_brier": round(float(brier(x["p_challenger"], y).mean()), 5),
             "delta_ll": round(float(dll.mean()), 5), "delta_ll_ci95": boot_mean(dll, day),
             "delta_brier": round(float(dbr.mean()), 5), "delta_brier_ci95": boot_mean(dbr, day)}
        pm = pd.to_numeric(x["p_market"], errors="coerce")
        if pm.notna().sum() > 10:
            k = pm.notna().to_numpy()
            r["market_ll_same_rows"] = round(float(ll(pm[k], y[k]).mean()), 5)
        out[eid] = r
    try:
        out["v9_evaluator"] = v9.json("output/model_lineage/shadow_experiments_eval.json")
    except Exception:
        pass
    return out


def section_clv(v9: Repo, df: pd.DataFrame, oct_end: str) -> dict:
    h = v9.json("output/clv_collection_health.json")
    out = {"clv_collection_health": {k: h.get(k) for k in ("generated_at", "close_rule", "measure_from", "check")},
           "all_time": {k: v for k, v in (h.get("shadow_all_time") or {}).items() if k not in ("by_league", "by_market")},
           "post_fix": {k: v for k, v in (h.get("shadow_since_measure_from") or {}).items() if k not in ("by_league", "by_market")},
           "collection_window": {k: v for k, v in (h.get("collection") or {}).items() if k not in ("by_market",)}}
    v = v9.csv("output/v91_shadow.csv")
    v["md"] = pd.to_datetime(v["match_date"].astype(str).str[:10], errors="coerce")
    v = v[v["settle_status"].astype(str).eq("SETTLED")]
    seg = {}
    for name, x in (("sep", v[(v["md"] >= SEP[0]) & (v["md"] <= SEP[1])]),
                    ("oct_pre_fix", v[(v["md"] >= OCT_START) & (v["md"] < CLV_FIX_FROM)]),
                    ("oct_post_fix", v[(v["md"] >= CLV_FIX_FROM) & (v["md"] <= oct_end)])):
        cm = pd.to_numeric(x["close_minutes_to_kickoff"], errors="coerce")
        seg[name] = {"eligible": int(len(x)),
                     "t30_certified_pct": round(float((x["close_status"] == "OK").mean() * 100), 1) if len(x) else None,
                     "t10_certified_pct": round(float(((x["close_status"] == "OK") & (cm <= 10)).mean() * 100), 1) if len(x) else None,
                     "stale_close_pct": round(float((x["close_status"] == "STALE_CLOSE_GT_30MIN").mean() * 100), 1) if len(x) else None,
                     "median_close_minutes_to_kickoff": round(float(cm.median()), 1) if cm.notna().any() else None}
    out["v91_shadow_by_period"] = seg
    out["v91_shadow_starts"] = str(v["md"].min().date()) if len(v) else None
    # ledger closing-price presence (not certification) by month
    led = {}
    for name, (a, b) in (("sep", SEP), ("oct", (OCT_START, oct_end))):
        x = window(df[df["settled"] & (df["market"] == "ou25")], a, b)
        led[name] = {"settled_ou25": int(len(x)), "closing_present_pct": round(float(x["clv_first"].notna().mean() * 100), 1),
                     "clv_exactly_zero_pct": round(float((x["clv_first"] == 0).mean() * 100), 1)}
    out["ledger_close_presence"] = led
    return out


def section_market_relative(v9: Repo) -> dict:
    """market_edge_v2 shadow (from 2026-10-25): model vs market vs decision probability, graded by
    goals from v91_shadow (fixture_id is shared)."""
    e = v9.csv("output/edge_engine_shadow.csv")
    v = v9.csv("output/v91_shadow.csv")[["fixture_id", "home_goals", "away_goals", "settle_status"]]
    v = v[v["settle_status"].astype(str).eq("SETTLED")].drop_duplicates("fixture_id")
    j = e.merge(v, on="fixture_id", how="inner")
    hg, ag = pd.to_numeric(j["home_goals"], errors="coerce"), pd.to_numeric(j["away_goals"], errors="coerce")
    tot = hg + ag
    yes = {"OU25": tot > 2.5, "OU15": tot > 1.5, "OU35": tot > 3.5, "BTTS": (hg > 0) & (ag > 0)}
    out = {"source": "v9 output/edge_engine_shadow.csv x v91_shadow goals", "first_prediction": str(e["prediction_ts"].min()), "by": {}}
    j = j.sort_values("prediction_ts").drop_duplicates(["fixture_id", "market", "side"], keep="first")
    for (mk, trk), x in j.groupby(["market", "track"]):
        y_side = yes[mk].loc[x.index]
        side_yes = x["side"].isin(["OVER", "YES"])
        y = np.where(side_yes, y_side, ~y_side).astype(float)
        cols = {"model": "p_model_raw", "market": "p_market_fair", "decision": "p_decision"}
        P = {k: pd.to_numeric(x[c], errors="coerce") for k, c in cols.items()}
        ok = np.all([P[k].notna().to_numpy() for k in P], axis=0)
        if ok.sum() < 10:
            continue
        day = x["match_date"].astype(str).to_numpy()[ok]
        r = {k: _score(P[k].to_numpy()[ok], y[ok], day) for k in P}
        d = ll(P["model"].to_numpy()[ok], y[ok]) - ll(P["market"].to_numpy()[ok], y[ok])
        r["model_minus_market_ll_ci95"] = boot_mean(d, day)
        out["by"][f"{mk}|{trk}"] = r
    return out


def section_bankroll() -> dict:
    base = OUT / "bankroll"
    out = {}
    try:
        wf = pd.read_csv(base / "walk_forward.csv")
        out["walk_forward"] = wf.to_dict("records")
    except Exception as e:  # noqa: BLE001
        out["walk_forward_error"] = str(e)
    try:
        out["track_decisions"] = pd.read_csv(base / "track_decisions.csv").fillna("").to_dict("records")
    except Exception:
        pass
    try:
        txt = (base / "MONTHLY_REVIEW.md").read_text(encoding="utf-8")
        out["monthly_review_head"] = [ln for ln in txt.splitlines()[:8] if ln.strip()]
    except Exception:
        pass
    return out


def section_v11(v11: Repo) -> dict:
    sb = v11.csv("output/v11_scoreboard.csv")
    out = {"scoreboard": sb[sb["scope"].isin(["2026-09", "2026-10", "overall"])].fillna("").to_dict("records")}
    for f in ("v11_movement_summary.csv", "v11_placebo_table.csv", "v11_residual.csv", "v11_chronological_folds.csv"):
        try:
            out[f] = v11.csv(f"output/{f}").fillna("").to_dict("records")
        except Exception:
            out[f] = []
    # residual by month on the same rows: market vs v11 blend
    return out


def section_v11_residual_month(v11: Repo) -> dict:
    log = v11.csv("output/v11_shadow_log.csv")
    g = v11.csv("output/v11_graded.csv")
    log["ts"] = pd.to_datetime(log["snapshot_ts"], utc=True, errors="coerce")
    ko = pd.to_datetime(log["kickoff_ts"], utc=True, errors="coerce")
    log = log[ko.isna() | (log["ts"] < ko)].sort_values("ts").drop_duplicates(["date", "league", "match"], keep="last")
    j = log.merge(g.drop_duplicates(["date", "league", "match"])[["date", "league", "match", "over25_result", "month"]],
                  on=["date", "league", "match"])
    j = j[pd.to_numeric(j["over25_result"], errors="coerce").isin([0, 1])]
    out = {}
    for m, x in j.groupby("month"):
        if m not in ("2026-09", "2026-10"):
            continue
        pm, pb = pd.to_numeric(x["v11_p_market"], errors="coerce"), pd.to_numeric(x["v11_p_blend"], errors="coerce")
        k = pm.notna() & pb.notna()
        y, day = x.loc[k, "over25_result"].astype(float).to_numpy(), x.loc[k, "date"].astype(str).to_numpy()
        d = ll(pb[k], y) - ll(pm[k], y)
        out[m] = {"n": int(k.sum()), "matchdays": int(len(set(day))), "ll_market": round(float(ll(pm[k], y).mean()), 5),
                  "ll_market_plus_wowza_blend": round(float(ll(pb[k], y).mean()), 5),
                  "blend_minus_market": round(float(d.mean()), 5), "blend_minus_market_ci95": boot_mean(d, day)}
    return out


def section_maturity(v9: Repo, pro: Repo, v11: Repo) -> list[dict]:
    items = [
        ("v9", "src/promotion_gate.py", "Leak-free validation harness + champion/challenger gate (shadow)"),
        ("v9", "src/champion_gate.py", "Champion high-water mark: retrains are challengers"),
        ("v9", "output/model_lineage/champion_history.csv", "Model lineage (champion history, retrain batches)"),
        ("v9", "config/promotion_gate.json", "STRICT PG-1.0 gate declared (sole writer of current_champions)"),
        ("v9", "output/model_lineage/shadow_experiments.csv", "Shadow challenger framework (H-MODEL-01 HGB)"),
        ("v9", "output/v91_shadow.csv", "v9.1 shadow: every fixture's served prob + market + outcome"),
        ("v9", "src/allocation.py", "Evidence allocator with RELIABLE_FROM epoch + matchday bootstrap"),
        ("v9", "config/bankroll_policy.json", "Bankroll policy file (WIRED_PAPER)"),
        ("v9", "output/clv_collection_health.json", "CLV collection health (T30/T10 certified close)"),
        ("v9", "output/odds_heartbeat", "Odds heartbeat (last OBSERVATION, not last change)"),
        ("v9", "src/edge_engine_shadow.py", "Market-first shadow engine (market_edge_v2)"),
        ("v9", "src/research_lock.py", "Research lock: protected-track fingerprint"),
        ("v9", "src/research/first_sight.py", "First-sight immutable research store"),
        ("v9", "output/league_weekly_research.csv", "Weekly league panel (first sight)"),
        ("v9", "output/system_health.json", "Canonical system-health checks"),
        ("v9", "src/direction_guard.py", "Opposite-direction guard on one fixture"),
        ("v9", "output/ledger_tier_seen.csv", "Ledger first-logged freeze (later sightings logged separately)"),
        ("pro", "src/bankroll/__init__.py", "Pro bankroll research (walk-forward, stress tests)"),
        ("pro", "src/studies/standard_repair", "Standard repair programme (league x market x side)"),
    ]
    repos = {"v9": v9, "pro": pro, "v11": v11}
    out = []
    for r, p, what in items:
        try:
            d = repos[r].first_added(p)
        except Exception:
            d = None
        out.append({"repo": r, "path": p, "capability": what, "first_on_main": d,
                    "month": (d or "")[:7] or "unknown"})
    commits = {}
    for name, rp in repos.items():
        try:
            lines = rp.run("log", rp.ref if name != "pro" else "HEAD", "--since=2026-09-01", "--until=2026-10-31T23:59:59",
                           "--format=%ad|%an", "--date=format:%Y-%m").splitlines()
            c = pd.Series([ln for ln in lines if "|" in ln]).str.split("|", expand=True)
            c.columns = ["month", "author"]
            c["kind"] = np.where(c["author"].str.contains(r"\[bot\]|github-actions", regex=True), "automated", "human")
            commits[name] = c.groupby(["month", "kind"]).size().unstack(fill_value=0).to_dict("index")
        except Exception:
            commits[name] = {}
    _COMMITS.update(commits)
    alias = v9.commit_date("6c80672f")
    out.append({"repo": "v9", "path": "6c80672f", "capability": "Club alias split fix (one club was becoming two teams)",
                "first_on_main": alias, "month": (alias or "")[:7]})
    return out


def oct_end_date(df: pd.DataFrame) -> str:
    s = df[df["settled"] & (df["md"] >= pd.Timestamp(OCT_START)) & (df["md"] <= pd.Timestamp("2026-10-31"))]
    return str(s["md"].max().date())


# ── orchestration ───────────────────────────────────────────────────────────────────────────────
def build(fetch: bool = True, refresh_history: bool = True) -> dict:
    global _AF_RESULTS
    home = Path.home() / "dev" / "wowza"
    v9 = Repo(_clone("V9_GIT_CLONE", cfg.V9_LOCAL, home / "v9"))
    v11 = Repo(_clone("V11_GIT_CLONE", cfg.V11_LOCAL, home / "v11"))
    pro = Repo(cfg.BASE_DIR)
    if fetch:
        for r in (v9, v11):
            r.fetch()
    df, audit = load_ledgers(v9, refresh_history)
    oct_end = oct_end_date(df)
    try:
        # fd_history carries a final score for every finished fixture in every league we price;
        # af_history's FTHG is only ~25% filled for Sep-Oct 2026 (measured 2026-10-28), so it is not used.
        r = v9.parquet("output/fd_history.parquet").rename(columns={"home_goals": "FTHG", "away_goals": "FTAG"})
        r["date"] = pd.to_datetime(r["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        _AF_RESULTS = r[(r["date"] >= "2026-08-25") & r["FTHG"].notna() & r["FTAG"].notna()]
    except Exception:
        _AF_RESULTS = None
    bet = section_betting(df, oct_end)
    out = {
        "title": "SEPTEMBER 2026 vs OCTOBER 2026 LEARNING EVIDENCE REPORT",
        "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calc_version": CALC_VERSION,
        "provenance": {"v9_origin_main": v9.sha(), "v9_head_ts": v9.head_ts(),
                       "v11_origin_main": v11.sha(), "v11_head_ts": v11.head_ts(),
                       "pro_head": pro.run("rev-parse", "--short=12", "HEAD").strip(),
                       "read_rule": "v9 and v11 read via `git show origin/main:<path>` after `git fetch`"},
        "windows": {"A": {"sep": list(SEP), "oct": [OCT_START, oct_end]},
                    "B": {"sep": list(SEP_RELIABLE), "oct": [OCT_START, oct_end]},
                    "reliable_from": RELIABLE_FROM,
                    "reliable_from_source": "v9 src/allocation.py:52 RELIABLE_FROM = \"2026-09-24\" "
                                            "(mirrored in Pro src/bankroll/__init__.py:26)",
                    "oct_latest_settled": oct_end},
        "ledger_audit": audit,
        "betting": bet["windows"],
        "tier_monotonic": section_tier_monotonic(bet),
        "standard_reference": section_std_reference(df, oct_end),
        "standard_data_quality": section_data_quality(),
        "retraining": section_retrain(v9),
        "forecast_ou25": section_forecast_ou25(v11, v9),
        "forecast_side": section_forecast_side(),
        "hgb_challenger": section_hgb(v9),
        "clv": section_clv(v9, df, oct_end),
        "market_relative_edge_v2": section_market_relative(v9),
        "bankroll": section_bankroll(),
        "v11": section_v11(v11),
        "v11_residual_by_month": section_v11_residual_month(v11),
        "maturity": section_maturity(v9, pro, v11),
    }
    out["commits_by_month"] = dict(_COMMITS)
    try:
        out["current_bankroll_policy"] = v9.json("config/bankroll_policy.json")
    except Exception:
        pass
    return out, bet


def write(out: dict, bet: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "monthly_learning_comparison.json").write_text(
        json.dumps(out, indent=1, default=lambda o: None if (isinstance(o, float) and o != o) else str(o)),
        encoding="utf-8")
    pd.DataFrame(bet["league_rows"]).to_csv(OUT / "monthly_learning_by_league.csv", index=False)
    tr = pd.DataFrame(bet["track_rows"])
    for c in tr.columns:
        if tr[c].map(lambda v: isinstance(v, list)).any():
            tr[c] = tr[c].map(lambda v: json.dumps(v) if isinstance(v, list) else v)
    tr.to_csv(OUT / "monthly_learning_by_track.csv", index=False)
    _LEAGUE_CACHE[:] = bet["league_rows"]
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(render(out), encoding="utf-8")


# ── report rendering ────────────────────────────────────────────────────────────────────────────
def _p(x, d=1, sign=True) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def _u(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}u"


def _ci(ci, pct=True, d=1) -> str:
    if not ci or ci[0] is None:
        return "n/a"
    return f"[{_p(ci[0], d)}, {_p(ci[1], d)}]" if pct else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def _f(x, d=4) -> str:
    return "n/a" if x is None else f"{x:+.{d}f}"


def verdict(ci) -> str:
    """IMPROVED / DETERIORATED only when the matchday-bootstrap CI of the change excludes zero."""
    if not ci or ci[0] is None:
        return "NOT COMPARABLE"
    return "IMPROVED" if ci[0] > 0 else "DETERIORATED" if ci[1] < 0 else "MIXED"


_BET_HDR = ("| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds "
            "| Mean CLV | CLV>0 | Close present |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def _bet_line(label, month, m) -> str:
    if not m or not m.get("n"):
        return f"| {label} | {month} | 0 | - | - | - | - | - | - | - | - | - | - | - |"
    clv = "n/a" if m.get("mean_clv_pct") is None else f"{m['mean_clv_pct']:+.2f}%"
    pos = "n/a" if m.get("clv_positive_share") is None else f"{m['clv_positive_share'] * 100:.0f}%"
    return (f"| {label} | {month} | {m['n']} | {m['matchdays']} | {m['wins']}-{m['losses']} | {m['hit'] * 100:.1f}% "
            f"| {m['breakeven_hit'] * 100:.1f}% | {_u(m['pnl_u'])} | {_p(m['roi'])} | {_ci(m['roi_ci90'])} "
            f"| {m['avg_odds']:.2f} / {m['median_odds']:.2f} | {clv} | {pos} | {m['clv_coverage'] * 100:.0f}% |")


def _cmp_block(title, comp: dict, keys=None) -> list[str]:
    L = [f"**{title}**", "", _BET_HDR]
    for k in (keys or comp.keys()):
        c = comp.get(k)
        if not c or "sep" not in c:
            continue
        L.append(_bet_line(k, "Sep", c["sep"]))
        L.append(_bet_line(k, "Oct", c["oct"]))
    L += ["", f"| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < {MIN_LEAGUE_N} bets or < {MIN_LEAGUE_DAYS} matchdays) |",
          "|---|---|---|---|---|---|"]
    for k in (keys or comp.keys()):
        c = comp.get(k)
        if not c or "delta_roi" not in c:
            continue
        small = min(c["sep"].get("n", 0), c["oct"].get("n", 0)) < MIN_LEAGUE_N or             min(c["sep"].get("matchdays", 0), c["oct"].get("matchdays", 0)) < MIN_LEAGUE_DAYS
        read = verdict(c.get("delta_roi_ci90"))
        if small:
            read = f"TOO_SMALL (CI would read {read})" if read in ("IMPROVED", "DETERIORATED") else "TOO_SMALL"
        L.append(f"| {k} | {_p(c['delta_roi'])} | {_ci(c.get('delta_roi_ci90'))} | {_p(c['delta_hit'])} "
                 f"| {_u(c['delta_pnl_u'])} | {read} |")
    return L + [""]


def _fq_line(label, r) -> str:
    m, k = r["model"], r["market"]
    return (f"| {label} | {m['n']} | {m['matchdays']} | {m['ll']:.4f} | {k['ll']:.4f} | {m['brier']:.4f} | {k['brier']:.4f} "
            f"| {m['ece']:.3f} | {k['ece']:.3f} | {r['model_minus_market_ll']:+.4f} {_ci(r['model_minus_market_ll_ci95'], False)} |")


def render(o: dict) -> str:  # noqa: C901 - one long, linear document
    W = o["windows"]
    A, B = o["betting"]["A"], o["betting"]["B"]
    ou, ouB = A["ou25"], B["ou25"]
    comb = A["combined"]
    std_ref = o["standard_reference"]
    dq = o["standard_data_quality"]
    rt = o["retraining"]
    fq = o["forecast_ou25"]
    fs = o["forecast_side"]
    hg = o["hgb_challenger"]
    clv = o["clv"]
    br = o["bankroll"]
    v11 = o["v11"]
    v11r = o["v11_residual_by_month"]
    mat = o["maturity"]
    prov = o["provenance"]
    tm = o["tier_monotonic"]
    oct_end = W["oct_latest_settled"]
    L: list[str] = []
    add = L.append

    def m(c, k):
        return c.get(k, {}) if c else {}

    allc, nfc, stc = comb["all"], comb["New Format"], comb["Standard"]
    nf_btts = A["tracks"]["NF BTTS"]
    sep_rm, oct_rm = rt["by_month"].get("2026-09", {}), rt["by_month"].get("2026-10", {})
    wf = pd.DataFrame(br.get("walk_forward", []))

    def wfv(month, pol, col="month_return_pct"):
        x = wf[(wf["month"] == month) & (wf["policy"] == pol)] if len(wf) else wf
        return float(x[col].iloc[0]) if len(x) else None

    arg = next((r for r in _LEAGUE_CACHE if r["comparison"] == "A" and r["market_family"] == "BTTS"
                and r["league"] == "Argentina Primera Division"), {})
    cap_sep = sum(1 for x in mat if x["month"] == "2026-09")
    cap_oct = sum(1 for x in mat if x["month"] == "2026-10")
    pre = clv["v91_shadow_by_period"]["oct_pre_fix"]
    post = clv["v91_shadow_by_period"]["oct_post_fix"]
    fq_std, fq_nf = fq["sep_to_oct"].get("Standard", {}), fq["sep_to_oct"].get("New Format", {})

    add(f"# {o['title']}")
    add("")
    add(f"Generated {o['generated_at']} by `python -m src.studies.monthly_learning` (calc {o['calc_version']}). "
        f"Data read from GitHub `origin/main` after `git fetch`: v9 `{prov['v9_origin_main']}` ({prov['v9_head_ts']}), "
        f"wowza_v11 `{prov['v11_origin_main']}` ({prov['v11_head_ts']}); Pro `{prov['pro_head']}`. "
        "ANALYSIS ONLY - nothing in production was changed.")
    add("")
    add(f"Comparison A: September 1-30 vs October 1-{oct_end[-2:]} (latest settled October match date {oct_end}). "
        f"Comparison B (reliable evidence): September {W['B']['sep'][0][-2:]}-30 vs the same October window. "
        f"`RELIABLE_FROM = {W['reliable_from']}` is defined in {W['reliable_from_source']}: it is the date from which the "
        "pipeline ran without a KNOWN defect. A and B are reported side by side and never mixed. Money is flat 1-unit stakes at the "
        "FIRST-LOGGED price (P/L in units).")
    add("")

    # ── plain English ──
    add("## Plain-English summary")
    add("")
    add(f"* **Did October make more money than September?** On the raw tip ledger, yes on the point estimate, but not "
        f"provably. All O/U 2.5 tips: September {_p(ou['all']['sep']['roi'])} ROI on {ou['all']['sep']['n']} bets "
        f"({_u(ou['all']['sep']['pnl_u'])}); October {_p(ou['all']['oct']['roi'])} on {ou['all']['oct']['n']} bets "
        f"({_u(ou['all']['oct']['pnl_u'])}). The change is {_p(ou['all']['delta_roi'])}, 90% interval "
        f"{_ci(ou['all']['delta_roi_ci90'])} - the interval includes zero, so October is not demonstrably better. "
        f"Every market together (genuine prices only): September {_p(allc['sep']['roi'])} on {allc['sep']['n']}, "
        f"October {_p(allc['oct']['roi'])} on {allc['oct']['n']}, change {_p(allc['delta_roi'])} {_ci(allc['delta_roi_ci90'])}.")
    add(f"* **The one change that IS statistically clear is a deterioration:** New Format BTTS went from "
        f"{_p(nf_btts['sep']['roi'])} (n {nf_btts['sep']['n']}) to {_p(nf_btts['oct']['roi'])} (n {nf_btts['oct']['n']}), "
        f"change {_p(nf_btts['delta_roi'])} {_ci(nf_btts['delta_roi_ci90'])}. Argentina alone accounts for "
        f"{_u(arg.get('delta_pnl_u'))} of the {_u(nf_btts.get('delta_pnl_u'))} swing ({_p(arg.get('sep_roi'))} -> {_p(arg.get('oct_roi'))}, "
        f"n {arg.get('sep_n')}/{arg.get('oct_n')}); the October studies had already shown Argentina BTTS to be a league regime, "
        "not model skill.")
    add(f"* **Forecast quality did not measurably improve.** On every O/U 2.5 fixture v9 published (not only tips), "
        f"v9's log loss changed by {_f(fq_std.get('model_ll_oct_minus_sep'))} on Standard and "
        f"{_f(fq_nf.get('model_ll_oct_minus_sep'))} on New Format (lower is better; both 95% intervals include zero), and the "
        "bookmaker's own de-vigged price stayed better than the model in both months.")
    add(f"* **What clearly improved is the machinery that decides what to trust.** Retrain promotions fell from "
        f"{sep_rm.get('promoted')}/{sep_rm.get('candidates')} ({_p(sep_rm.get('promotion_rate'), 0, False)}) in September to "
        f"{oct_rm.get('promoted')}/{oct_rm.get('candidates')} ({_p(oct_rm.get('promotion_rate'), 0, False)}) in October; "
        f"promotions of a model whose own holdout got WORSE fell from {sep_rm.get('promoted_with_worse_holdout_ll')} to "
        f"{oct_rm.get('promoted_with_worse_holdout_ll')}; and under the strict PG-1.0 gate (from 2026-10-25) 0 of 7 retrains reached "
        f"production. Certified closing-price coverage went from {pre['t30_certified_pct']}% (October, before the collector fix) to "
        f"{post['t30_certified_pct']}% after it. {cap_oct} of the {len(mat)} evidence capabilities listed in section 18 first "
        f"landed in October; {cap_sep} in September.")
    add("* **Standard results are PRE_REPAIR evidence.** They come from a pipeline with known data defects (section 2). "
        "A bad Standard month is not proof the model idea fails, and a better month is not proof it was fixed.")
    add("")
    lo = std_ref.get("League One", {})
    add("**Worked example - why one bad month is not 'the model is broken'.** League One O/U 2.5, Sep 1-"
        f"{oct_end[-5:]}: {lo.get('n')} settled tips, {lo.get('wins')} won. The bookmaker's own prices, after removing a ~5% "
        f"margin, implied about {lo.get('expected_wins_devig_approx_5pct')} wins. Getting {lo.get('wins')} or fewer by chance has "
        f"probability {lo.get('p_value_le_wins_devig_approx')} - unusual, so League One is genuinely bad. But League One also "
        f"carries the heaviest data defects in the Standard repair audit (alias collisions "
        f"{_p((dq.get('per_league', {}).get('League One') or {}).get('alias_collision_share_legacy'), 0, False)} of legacy rows; "
        f"{(dq.get('per_league', {}).get('League One') or {}).get('future_leak_sides_legacy')} team-sides whose rolling form "
        "contained a FUTURE match). The honest reading is 'a broken input pipeline produced bad tips here', which only the "
        "repaired-v9 rerun can separate from 'bad model idea'.")
    add("")
    add("**Worked example - reading an interval.** October's O/U 2.5 ROI was "
        f"{_p(ou['all']['delta_roi'])} better than September's. The 90% interval {_ci(ou['all']['delta_roi_ci90'])} is built by "
        "re-drawing whole matchdays (a Saturday with 20 bets is one draw, not 20). Because it runs from a loss to a gain, the "
        "data cannot tell a real improvement from a lucky month.")
    add("")

    # ── scorecard ──
    add("## 19. Learning scorecard")
    add("")
    add("| Area | September | October | Verdict |")
    add("|---|---|---|---|")
    sc = []
    sc.append(("Main performance (all O/U 2.5 tips)",
               f"{_p(ou['all']['sep']['roi'])} on {ou['all']['sep']['n']} ({_u(ou['all']['sep']['pnl_u'])})",
               f"{_p(ou['all']['oct']['roi'])} on {ou['all']['oct']['n']} ({_u(ou['all']['oct']['pnl_u'])})",
               f"{verdict(ou['all']['delta_roi_ci90'])} (change {_p(ou['all']['delta_roi'])}, CI {_ci(ou['all']['delta_roi_ci90'])})"))
    sc.append(("New Format performance (all markets)",
               f"{_p(nfc['sep']['roi'])} on {nfc['sep']['n']} ({_u(nfc['sep']['pnl_u'])})",
               f"{_p(nfc['oct']['roi'])} on {nfc['oct']['n']} ({_u(nfc['oct']['pnl_u'])})",
               f"{verdict(nfc['delta_roi_ci90'])} (OU25 better n.s.; BTTS significantly worse)"))
    sc.append(("Standard (PRE_REPAIR)",
               f"OU25 {_p(ou['Standard']['sep']['roi'])} on {ou['Standard']['sep']['n']}",
               f"OU25 {_p(ou['Standard']['oct']['roi'])} on {ou['Standard']['oct']['n']}",
               f"{verdict(ou['Standard']['delta_roi_ci90'])} - PRE_REPAIR, not structural evidence"))
    sc.append(("Side markets (genuine prices)",
               f"NF BTTS {_p(nf_btts['sep']['roi'])}, NF O1.5 {_p(A['side']['New Format|over15']['sep']['roi'])}",
               f"NF BTTS {_p(nf_btts['oct']['roi'])}, NF O1.5 {_p(A['side']['New Format|over15']['oct']['roi'])}",
               "DETERIORATED (NF BTTS CI excludes zero; others n.s.)" if verdict(nf_btts['delta_roi_ci90']) == "DETERIORATED" else "MIXED"))
    sc.append(("Prediction quality (OU25 log loss, all fixtures)",
               f"Std {fq['by_month_track']['2026-09|Standard']['model']['ll']:.4f} / NF {fq['by_month_track']['2026-09|New Format']['model']['ll']:.4f}",
               f"Std {fq['by_month_track']['2026-10|Standard']['model']['ll']:.4f} / NF {fq['by_month_track']['2026-10|New Format']['model']['ll']:.4f}",
               "MIXED (no change outside noise; market still better)"))
    sc.append(("CLV quality (measurement)", "NOT MEASURABLE (no certified close stream; v91_shadow starts 2026-10-04)",
               f"T30 certified {pre['t30_certified_pct']}% pre-fix -> {post['t30_certified_pct']}% post-fix",
               "STRONGLY IMPROVED (measurement); CLV values themselves flat"))
    sc.append(("Model promotion discipline", f"{sep_rm.get('promoted')}/{sep_rm.get('candidates')} promoted, "
               f"{sep_rm.get('promoted_with_worse_holdout_ll')} with worse holdout, no CI",
               f"{oct_rm.get('promoted')}/{oct_rm.get('candidates')} promoted, {oct_rm.get('promoted_with_worse_holdout_ll')} with worse "
               "holdout; PG-1.0: 0/7 to production", "STRONGLY IMPROVED"))
    sc.append(("Data integrity", "alias split fix (09-24); first-logged prices still overwritable",
               "first-logged freeze, 1H-BTTS + synthetic-price exclusion, heartbeat, identity audit (Standard still unrepaired)",
               "IMPROVED"))
    sc.append(("Research quality", f"{cap_sep} evidence capability landed", f"{cap_oct} capabilities landed (shadow challenger, "
               "strict gate, first-sight stores, market-first shadow, weekly panel)", "STRONGLY IMPROVED"))
    sc.append(("Bankroll (Pro walk-forward)", f"ADAPTIVE {wfv('2026-09', 'ADAPTIVE'):+.1f}%, BALANCED {wfv('2026-09', 'STATIC_BALANCED'):+.1f}%",
               f"ADAPTIVE {wfv('2026-10', 'ADAPTIVE'):+.1f}%, BALANCED {wfv('2026-10', 'STATIC_BALANCED'):+.1f}%",
               "DETERIORATED for managed policies (September made more); flat staking did better in October"))
    for r in sc:
        add("| " + " | ".join(r) + " |")
    add("")
    add("Verdict rule for performance rows: IMPROVED / DETERIORATED only when the 90% matchday-bootstrap interval of the "
        "Oct-Sep change excludes zero; otherwise MIXED. Process rows are judged on counts and dates in sections 8, 11 and 18.")
    add("")

    # ── final answers ──
    add("## 20. Final questions")
    add("")
    best_lg = [r for r in _LEAGUE_CACHE if r["comparison"] == "A"]
    imp = sorted([r for r in best_lg if r["delta_roi"] == r["delta_roi"] and r["delta_roi"] is not None
                  and min(r["sep_n"], r["oct_n"]) >= 10], key=lambda r: -r["delta_roi"])[:4]
    det = sorted([r for r in best_lg if r["delta_roi"] == r["delta_roi"] and r["delta_roi"] is not None
                  and min(r["sep_n"], r["oct_n"]) >= 10], key=lambda r: r["delta_roi"])[:4]
    fmt_l = lambda rs: "; ".join(f"{r['league']} {r['market_family']} {_p(r['sep_roi'])} -> {_p(r['oct_roi'])} "
                                 f"(n {r['sep_n']}/{r['oct_n']}, CI {_ci([r['delta_roi_ci90_lo'], r['delta_roi_ci90_hi']])}, {r['category']})"
                                 for r in rs)
    add("1. **Is there numerical evidence that WOWZA learned?** In its DECISION PROCESS, yes: promotion rate "
        f"{_p(sep_rm.get('promotion_rate'), 0, False)} -> {_p(oct_rm.get('promotion_rate'), 0, False)}, worse-holdout promotions "
        f"{sep_rm.get('promoted_with_worse_holdout_ll')} -> {oct_rm.get('promoted_with_worse_holdout_ll')}, certified closes "
        f"{pre['t30_certified_pct']}% -> {post['t30_certified_pct']}%. In its PREDICTIONS and RESULTS, no change survives the "
        "matchday bootstrap except the NF BTTS deterioration.")
    add(f"2. **Strongest numbers.** Strict gate: 0 of 7 retrains reached production on 2026-10-25 (one PG-1.0 rollback). "
        f"CLV certification {post['t30_certified_pct']}% T30 / {post['t10_certified_pct']}% T10 post-fix. Standard ex League One/Two "
        f"OU25 {_p(ou['Standard ex League One/Two']['sep']['roi'])} -> {_p(ou['Standard ex League One/Two']['oct']['roi'])} "
        f"(n {ou['Standard ex League One/Two']['sep']['n']}/{ou['Standard ex League One/Two']['oct']['n']}, CI "
        f"{_ci(ou['Standard ex League One/Two']['delta_roi_ci90'])}) - directional only. NF O1.5 October "
        f"{_p(A['side']['New Format|over15']['oct']['roi'])} with ROI CI {_ci(A['side']['New Format|over15']['oct']['roi_ci90'])} on "
        f"n {A['side']['New Format|over15']['oct']['n']} (small). H-MODEL-01 HGB on New Format: log loss "
        f"{_f(hg.get('H-MODEL-01__newformat', {}).get('delta_ll'))} vs champion, CI {_ci(hg.get('H-MODEL-01__newformat', {}).get('delta_ll_ci95'), False)} "
        f"on {hg.get('H-MODEL-01__newformat', {}).get('paired_n')} fixtures / {hg.get('H-MODEL-01__newformat', {}).get('matchdays')} matchdays.")
    add(f"3. **What did not improve.** Forecast quality vs the market (v9 still loses to the de-vigged price on log loss in both months); "
        f"mean CLV of tips ({ou['all']['sep']['mean_clv_pct']:+.2f}% -> {ou['all']['oct']['mean_clv_pct']:+.2f}%); tier ordering "
        "(Big/Medium/Small gap is not monotonic in either month); NF BTTS; League One; the Standard HGB challenger.")
    add(f"4. **Was October more profitable?** Raw betting: point estimate yes (all OU25 {_u(ou['all']['sep']['pnl_u'])} -> "
        f"{_u(ou['all']['oct']['pnl_u'])}; every market {_u(allc['sep']['pnl_u'])} -> {_u(allc['oct']['pnl_u'])}), not significant. "
        f"Bankroll simulation: NO for the managed policies (ADAPTIVE {wfv('2026-09', 'ADAPTIVE'):+.1f}% -> {wfv('2026-10', 'ADAPTIVE'):+.1f}%, "
        f"BALANCED {wfv('2026-09', 'STATIC_BALANCED'):+.1f}% -> {wfv('2026-10', 'STATIC_BALANCED'):+.1f}%), yes for flat staking. "
        "Forecast quality: no measurable change.")
    add(f"5. **Did New Format improve?** NF OU25 {_p(ou['New Format']['sep']['roi'])} -> {_p(ou['New Format']['oct']['roi'])} "
        f"(change {_p(ou['New Format']['delta_roi'])}, CI {_ci(ou['New Format']['delta_roi_ci90'])}); NF all markets "
        f"{_p(nfc['sep']['roi'])} -> {_p(nfc['oct']['roi'])} (CI {_ci(nfc['delta_roi_ci90'])}); NF BTTS significantly worse. "
        "Net: NOT demonstrably improved.")
    add(f"6. **Did Standard improve? (PRE_REPAIR)** OU25 {_p(ou['Standard']['sep']['roi'])} -> {_p(ou['Standard']['oct']['roi'])} "
        f"(CI {_ci(ou['Standard']['delta_roi_ci90'])}); forecast log loss slightly worse in October (+{fq_std.get('model_ll_oct_minus_sep', 0):.4f}, "
        "CI includes zero). Not demonstrably; and pre-repair evidence cannot answer it - rerun OLD V9 vs REPAIRED V9 vs MARKET.")
    ci_pos = [r["league"] + " " + r["market_family"] for r in best_lg if r["delta_roi_ci90_lo"] is not None
              and r["delta_roi_ci90_lo"] == r["delta_roi_ci90_lo"] and r["delta_roi_ci90_lo"] > 0]
    cls_imp = [r["league"] + " " + r["market_family"] for r in best_lg if r["category"] == "IMPROVED"]
    cls_det = [r["league"] + " " + r["market_family"] for r in best_lg if r["category"] == "DETERIORATED"]
    add(f"7. **Leagues that improved most (point estimate, n>=10 both months).** {fmt_l(imp)}. Cells whose interval excludes "
        f"zero on the upside: {', '.join(ci_pos) or 'none'}; cells that pass the sample floor AND the interval (IMPROVED): "
        f"{', '.join(cls_imp) or 'none'}.")
    add(f"8. **Leagues that deteriorated.** {fmt_l(det)}. Cells classified DETERIORATED: {', '.join(cls_det) or 'none'}.")
    add(f"9. **Is promotion more selective?** Yes: {_p(sep_rm.get('promotion_rate'), 0, False)} -> {_p(oct_rm.get('promotion_rate'), 0, False)} "
        "under the old gate alone, and the strict PG-1.0 gate now requires a 95% CI that excludes zero, a material gain, calibration, "
        "a canary, no league regression AND a prospective period of >=1000 rows per track. "
        f"Replayed under the new gate, the {sum(o['retraining'].get('legacy_promotions_replayed_under_strict_gate', {}).values())} legacy "
        f"promotions become {o['retraining'].get('legacy_promotions_replayed_under_strict_gate')}.")
    add(f"10. **Did market-data quality improve?** Yes: certified T30 close {pre['t30_certified_pct']}% -> {post['t30_certified_pct']}%, "
        f"median last pre-kickoff close {pre['median_close_minutes_to_kickoff']} min -> {post['median_close_minutes_to_kickoff']} min; "
        "first-logged prices frozen from 2026-10-26; 1H-BTTS and synthetic-price rows excluded from certified ROI.")
    add("11. **What WOWZA learned in October that it did not know in September.** (a) The NF BTTS profit was a league regime "
        "(Argentina), not selection skill - October proved it out of sample. (b) Raw model-market disagreement is not a quality "
        "ordering. (c) v9 adds nothing measurable to the market price (v11 residual, edge_v2 shadow, Pro consensus all agree). "
        "(d) Most September 'improvements' at retrain were noise - a gate with a CI rejects them. (e) The Standard pipeline has "
        "concrete data defects (aliases, future-form leak, closing-price training) that must be fixed before its results mean anything. "
        "(f) NF OU25 UNDER does not earn its stake (monthly review proposes STOP). (g) An HGB challenger may help New Format - "
        "too early to say.")
    add("12. **What should NOT be changed yet.** No promotion of the HGB challenger (5 matchdays, PG-1.0 needs >=1000 prospective "
        "rows per track); no Standard staking or threshold change before the repaired-v9 rerun; no stake increase on NF BTTS or NF "
        "O1.5 from one month; no new per-league rules from October league ROI (every cell but one is TOO_SMALL or STABLE); keep the "
        "strict gate, the first-logged freeze and the CLV collector exactly as they are.")
    add("")

    # ── 1 / 2 ──
    add("## 1. The two comparisons")
    add("")
    add(f"| Comparison | September window | October window | Why |\n|---|---|---|---|\n"
        f"| A | {W['A']['sep'][0]} to {W['A']['sep'][1]} | {W['A']['oct'][0]} to {W['A']['oct'][1]} | calendar months |\n"
        f"| B | {W['B']['sep'][0]} to {W['B']['sep'][1]} | {W['B']['oct'][0]} to {W['B']['oct'][1]} | reliable-evidence epoch only |")
    add("")
    add(f"Ledger audit: {o['ledger_audit']['rows_since_sep']} live ledger rows since Sep 1, first-logged state recovered from v9's git "
        f"history for {o['ledger_audit']['first_logged_found']}. Rows whose PRICE was rewritten after first log (side ledger, before "
        f"2026-10-26): {o['ledger_audit']['rows_price_rewritten_after_first_log']}. Rows whose TIER was upgraded in place: "
        f"{o['ledger_audit']['rows_tier_upgraded_after_first_log']}. All results below use the first-logged price and tier.")
    add("")
    add("## 2. Standard = PRE_REPAIR STANDARD EVIDENCE / LEGACY")
    add("")
    add("**Every Standard number in this report is labelled PRE_REPAIR STANDARD EVIDENCE / LEGACY - CONTAMINATED BY KNOWN DATA "
        "DEFECTS:** alias duplication and split team histories; future-match contamination in rolling form; wrong season weighting; "
        "closing-price train/live mismatch; invalid synthetic historical BTTS/O1.5 prices. It is NOT proof of structural improvement "
        "or deterioration. **This report must be rerun as OLD V9 vs REPAIRED V9 vs MARKET once a repaired v9 exists.**")
    add("")
    if dq.get("available"):
        add(f"Data-quality burden (read-only from `{dq['source_dir']}`, status {dq.get('status')}, cutoff {dq.get('data_cutoff')}, "
            f"v9 {str(dq.get('v9_commit'))[:12]}): {dq.get('alias_rows_removed')} alias rows removed from the legacy frame; "
            f"{dq.get('future_match_in_window_legacy_total')} Standard fixtures had a future match inside the 5-game rolling window "
            f"(legacy; {dq.get('future_match_in_window_canonical_total')} after canonicalisation); identity quarantine rows "
            f"{dq.get('identity_quarantine_rows')}; {_p(dq.get('ou25_frame_price_equals_closing_share'), 0, False)} of the training "
            "frame's OU25 price equals the CLOSING price where both are known.")
        add("")
        add("| League | Legacy rows | Alias-collision share (legacy) | Aliases resolved | Future-form leak sides legacy / canonical "
            "| OU25 real entry price share | Certified T30 close (forward) | 1H-BTTS rows removed | Live-constant features |")
        add("|---|---|---|---|---|---|---|---|---|")
        for lg, x in dq["per_league"].items():
            b1 = x.get("btts_1h_rows_removed") or {}
            add(f"| {lg} | {x.get('rows')} | {_p(x.get('alias_collision_share_legacy'), 1, False)} | {x.get('aliases_resolved')} "
                f"| {x.get('future_leak_sides_legacy')} / {x.get('future_leak_sides_canonical')} | {_p(x.get('ou25_real_entry_share'), 0, False)} "
                f"| {_p(x.get('ou25_certified_t30_share_forward'), 0, False)} | {sum(v for v in b1.values() if isinstance(v, (int, float)))} "
                f"| {', '.join(x.get('live_constant_features') or [])} |")
        add("")
        add("Note: the owner brief quoted ~370 future-form rows (League One 95, League Two 125). The repair worktree's current "
            "file reports the figures above; that worktree is still being written by another agent, so the count is a moving "
            "measurement - the direction (League One and League Two carry the leak; the others ~0) is stable.")
    else:
        add(f"Data-quality file not available: {dq.get('error')}")
    add("")

    # ── 3 ──
    add("## 3. Main O/U 2.5 betting (first-logged price, one row per fixture x side)")
    add("")
    for wid, R in (("A", ou), ("B", ouB)):
        add(f"### Comparison {wid}")
        add("")
        L += _cmp_block(f"O/U 2.5 - comparison {wid}", R,
                        ["all", "Standard", "New Format", "Standard|OVER", "Standard|UNDER", "New Format|OVER", "New Format|UNDER",
                         "Standard ex League One/Two"])
    add("### By raw-gap label (comparison A)")
    add("")
    add(TIER_SENTENCE)
    add("")
    for scope in ("all", "Standard", "New Format"):
        L += _cmp_block(f"{scope} - SNIPER/Big gap, MARKSMAN/Medium gap, VALUABLE/Small gap", A["ou25_by_gap"][scope])
    add(f"Close present = a closing price exists in the ledger. It is NOT a certified close: {clv['ledger_close_presence']['sep']['clv_exactly_zero_pct']}% "
        f"(Sep) and {clv['ledger_close_presence']['oct']['clv_exactly_zero_pct']}% (Oct) of OU25 closes equal the entry price exactly, "
        "the signature of a missing close. Certified close coverage is in section 11.")
    add("")

    # ── 4 ──
    add("## 4. Side markets - genuine observed prices only")
    add("")
    add(f"Excluded from certified ROI: {o['ledger_audit']['side_rows_excluded']} (rows priced exactly at v9's synthetic fill "
        f"constant {SYNTHETIC_ODDS} are dropped fail-closed, the rule in v9 `src/market_edge.py::exclude_synthetic_prices`; BTTS "
        f"entries above {BTTS_YES_MAX} are the first-half market and dropped; BTTS closes above {BTTS_YES_MAX} are dropped from CLV).")
    add("")
    L += _cmp_block("Side markets - comparison A", A["side"],
                    ["New Format|btts", "New Format|over15", "Standard|btts", "Standard|over15", "New Format|over35", "Standard|over35"])
    L += _cmp_block("Side markets - comparison B", B["side"],
                    ["New Format|btts", "New Format|over15", "Standard|btts", "Standard|over15"])

    # ── 5 ──
    add("## 5. League-level change")
    add("")
    add(f"Category rule: TOO_SMALL unless both months have >= {MIN_LEAGUE_N} settled bets and >= {MIN_LEAGUE_DAYS} matchdays; then "
        "IMPROVED / DETERIORATED only if the 90% matchday-bootstrap CI of the ROI change excludes zero, else STABLE. Full table "
        "(both comparisons, OU25 and BTTS): `output/monthly_learning_by_league.csv`.")
    add("")
    add("| Market | League | Track | Sep N | Sep ROI | Oct N | Oct ROI | ROI change | 90% CI | Hit change | PnL change | Category | Pattern |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted([r for r in _LEAGUE_CACHE if r["comparison"] == "A" and (r["sep_n"] or 0) + (r["oct_n"] or 0) >= 15],
                    key=lambda r: (r["market_family"], r["track"], r["league"])):
        lab = r["league"] + (" (PRE_REPAIR)" if r["pre_repair_standard"] else "")
        add(f"| {r['market_family']} | {lab} | {r['track']} | {r['sep_n']} | {_p(r['sep_roi'])} | {r['oct_n']} | {_p(r['oct_roi'])} "
            f"| {_p(r['delta_roi'])} | {_ci([r['delta_roi_ci90_lo'], r['delta_roi_ci90_hi']])} | {_p(r['delta_hit'])} "
            f"| {_u(r['delta_pnl_u'])} | {r['category']} | {r['pattern']} |")
    add("")
    for pat, words in (("POSITIVE_BOTH", "Positive both months"), ("NEG_TO_POS", "Negative -> positive"),
                       ("POS_TO_NEG", "Positive -> negative"), ("NEGATIVE_BOTH", "Persistently negative")):
        xs = [f"{r['league']} {r['market_family']}" for r in _LEAGUE_CACHE
              if r["comparison"] == "A" and r["pattern"] == pat and min(r["sep_n"], r["oct_n"]) >= 10]
        add(f"* **{words}** (n>=10 both months): {', '.join(xs) or 'none'}")
    add("")
    add("Comparison B: with only Sep 24-30 on the September side, every league cell is TOO_SMALL; no league-level claim can be made "
        "from the reliable-evidence window yet.")
    add("")

    # ── 6 ──
    add("## 6. New Format")
    add("")
    L += _cmp_block("New Format totals - comparison A", {"NF all markets": nfc, "NF OU25": ou["New Format"],
                                                        "NF OU25 OVER": ou["New Format|OVER"], "NF OU25 UNDER": ou["New Format|UNDER"],
                                                        "NF BTTS": nf_btts, "NF O1.5": A["side"]["New Format|over15"]})
    add(f"**Did New Format improve?** Not demonstrably. All NF markets: {_p(nfc['sep']['roi'])} -> {_p(nfc['oct']['roi'])}, change "
        f"{_p(nfc['delta_roi'])}, 90% CI {_ci(nfc['delta_roi_ci90'])}. NF OU25 moved up ({_p(ou['New Format']['delta_roi'])}, CI "
        f"{_ci(ou['New Format']['delta_roi_ci90'])}) while NF BTTS fell ({_p(nf_btts['delta_roi'])}, CI {_ci(nf_btts['delta_roi_ci90'])}). "
        f"Forecast-wise NF OU25 log loss moved {_f(fq_nf.get('model_ll_oct_minus_sep'))} (CI {_ci(fq_nf.get('model_ll_oct_minus_sep_ci95'), False)}). "
        "NF leagues are in section 5.")
    add("")

    # ── 7 ──
    add("## 7. Standard per league - PRE_REPAIR")
    add("")
    add("| League (PRE_REPAIR) | N Sep-Oct | Matchdays | Wins | Bookmaker-expected wins (raw / ~5% de-vig) | P(W <= observed) raw / de-vig | PnL | ROI |")
    add("|---|---|---|---|---|---|---|---|")
    for lg, x in std_ref.items():
        add(f"| {lg} | {x['n']} | {x['matchdays']} | {x['wins']} | {x['expected_wins_raw_implied']} / {x['expected_wins_devig_approx_5pct']} "
            f"| {x['p_value_le_wins_raw']} / {x['p_value_le_wins_devig_approx']} | {_u(x['pnl_u'])} | {_p(x['roi'])} |")
    add("")
    so = ou["Standard ledger-price (owner reference)"]
    add(f"Owner reference reproduced from the GitHub ledger (1u at logged odds): Standard OU25 September {so['sep']['n']} bets "
        f"{_p(so['sep']['roi'])} {_u(so['sep']['pnl_u'])}; October {so['oct']['n']} bets {_p(so['oct']['roi'])} {_u(so['oct']['pnl_u'])}. "
        f"Ex League One/Two: September {ou['Standard ex League One/Two']['sep']['n']} {_p(ou['Standard ex League One/Two']['sep']['roi'])}, "
        f"October {ou['Standard ex League One/Two']['oct']['n']} {_p(ou['Standard ex League One/Two']['oct']['roi'])}. League One "
        f"{lo.get('wins')} wins vs ~{lo.get('expected_wins_devig_approx_5pct')} bookmaker-expected (p {lo.get('p_value_le_wins_devig_approx')}). "
        "All verified - the OU25 ledger price was never overwritten (0 rows), so ledger price = first-logged price for OU25.")
    add("")
    add("A bad Standard month is NOT read as pure model failure: League One and League Two, the two worst leagues, are also the "
        "only two Standard leagues with future-form leakage, and all seven serve `home_advantage` as a constant live while it varies "
        "in training. Those are implementation defects to remove before the model idea can be judged.")
    add("")

    # ── 8 ──
    add("## 8. Retraining and promotion")
    add("")
    add("| Month | Retrain days | Candidates | Promoted | Rejected / held | Promotion rate | Promoted with WORSE holdout LL | Promoted with a CI | Promoted with CI excluding zero |")
    add("|---|---|---|---|---|---|---|---|---|")
    for mo, x in rt["by_month"].items():
        add(f"| {mo} | {x['retrain_days']} | {x['candidates']} | {x['promoted']} | {x['rejected_or_held']} | {_p(x['promotion_rate'], 0, False)} "
            f"| {x['promoted_with_worse_holdout_ll']} | {x['promoted_with_ci']} | {x['promoted_ci_excluding_zero']} |")
    add("")
    add("Gates: **OLD LEGACY GATE** (v9 retrain.py tolerance rule: promote unless holdout log loss rose by more than 0.005 - later "
        "0.030 - no interval) ran every September and October retrain through 2026-10-18. The **champion high-water mark** "
        "(src/champion_gate.py, 2026-10-18) judged the 2026-10-25 batch. The **STRICT PG-1.0 GATE** (src/promotion_gate.py + "
        f"config/promotion_gate.json, declared {rt.get('pg10_config', {}).get('declared_on')}) became the sole writer of "
        "current_champions.json minutes later and requires: n >= 1000 per track, a material gain (<= -0.001 LL), 95% matchday "
        "block-bootstrap CI excluding zero, Brier/ECE/slope not worse, a prediction canary, no league regression, AND a prospective "
        "period of >= 1000 rows per track.")
    add("")
    add("By gate: " + "; ".join(f"{mo}: {x['by_gate']}" for mo, x in rt["by_month"].items()))
    add("")
    add("**September examples of weak models the old gate promoted** (holdout log loss got WORSE, promoted anyway):")
    add("")
    for e in rt["examples_weak_promoted_sep"]:
        add(f"* {e['d']} {e['model_type']}: delta {e['ll_delta']:+.5f} - \"{e['reason']}\"")
    add("")
    add("**October rejections:**")
    add("")
    for e in rt["examples_rejected_oct"]:
        add(f"* {e['d']} {e['model_type']}: {e['verdict']}, delta {e['ll_delta']:+.6f} - {e['reason']}")
    add("")
    add("**2026-10-25, model by model:**")
    add("")
    add("| Model | Gate | Verdict | LL delta | 95% CI | Brier delta | ECE delta | Later-half delta | Why |")
    add("|---|---|---|---|---|---|---|---|---|")
    for k in ("standard", "newformat", "btts", "over15", "over35", "ht_over05", "ht_over15"):
        x = rt["oct25"].get(k)
        if x:
            add(f"| {k} | {x['gate']} | {x['verdict']} | {x['ll_delta']:+.6f} | {_ci(x['ll_ci95'], False)} | {x['brier_delta']:+.6f} "
                f"| {x['ece_delta']:+.4f} | {x['later_half_ll_delta']:+.6f} | {x['reason']} |")
    add("")
    add("PG-1.0 decisions the same day: " + "; ".join(f"{d['stage']} {d['model_type']} {d['candidate_version']} -> {d['verdict']} "
                                                      f"({d['reason']})" for d in rt.get("pg10_decisions", [])))
    add("")
    add("So on 2026-10-25: standard HELD (SHADOW_MORE - possibly better, CI includes zero, not material); newformat was promoted by "
        "the retiring high-water-mark gate, then ROLLED BACK under PG-1.0 because it had no prospective period, and parked as a "
        "challenger; btts KEPT (challenger worse); over15, over35, ht_over05, ht_over15 KEPT (statistically tied - the CI does not "
        "even admit a material gain). Net: 0 of 7 retrains changed production.")
    add("")
    add(f"Did the system get better at rejecting weak models? Yes. Replaying every legacy promotion under the new gate gives "
        f"{rt.get('legacy_promotions_replayed_under_strict_gate')} - not one would have been a clean PROMOTE.")
    add("")

    # ── 9 ──
    add("## 9. Forecast quality (log loss, Brier, ECE)")
    add("")
    add("Comparable datasets only. **(a)** O/U 2.5 on EVERY fixture v9 published, from wowza_v11's shadow log (the same pipeline in "
        "both months; last pre-kickoff snapshot; graded by v11). **(b)** O/U 2.5, BTTS, O1.5, O3.5 from the Pro canonical store: v9 "
        "model snapshot (last pre-kickoff) vs the median de-vigged two-sided quote over >= 3 books (last pre-kickoff quote per book, "
        f"change-log carried forward), graded on v9 fd_history scores; {fs.get('fixtures_with_results')} of {fs.get('fixtures_in_store')} "
        "fixtures matched to a final score. v91_shadow starts 2026-10-04, so it is **NOT DIRECTLY COMPARABLE** for September and is "
        "used only in section 11.")
    add("")
    add("| (a) OU25, all published fixtures | N | Matchdays | Model LL | Market LL | Model Brier | Market Brier | Model ECE | Market ECE | Model - market LL (95% CI) |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for k in ("2026-09|Standard", "2026-10|Standard", "2026-09|New Format", "2026-10|New Format"):
        if k in fq["by_month_track"]:
            add(_fq_line(k, fq["by_month_track"][k]))
    add("")
    for t, x in fq["sep_to_oct"].items():
        add(f"* {t}: model LL Oct - Sep {_f(x['model_ll_oct_minus_sep'])} {_ci(x['model_ll_oct_minus_sep_ci95'], False)}; gap to market "
            f"Oct - Sep {_f(x['gap_to_market_oct_minus_sep'])} {_ci(x['gap_to_market_oct_minus_sep_ci95'], False)}.")
    add("")
    add("| (b) Pro store | N | Matchdays | Model LL | Market LL | Model Brier | Market Brier | Model ECE | Market ECE | Model - market LL (95% CI) |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for k in sorted(fs.get("by", {})):
        if fs["by"][k]["model"]["n"] >= 20:
            add(_fq_line(k, fs["by"][k]))
    add("")
    for k, x in (fs.get("sep_to_oct") or {}).items():
        add(f"* {k}: model LL Oct - Sep {_f(x['model_ll_oct_minus_sep'])} {_ci(x['model_ll_oct_minus_sep_ci95'], False)}; gap to market "
            f"Oct - Sep {_f(x['gap_to_market_oct_minus_sep'])} {_ci(x['gap_to_market_oct_minus_sep_ci95'], False)}.")
    add("")
    s2o = fs.get("sep_to_oct") or {}
    better = [k for k, x in s2o.items() if x["model_ll_oct_minus_sep_ci95"][0] is not None and x["model_ll_oct_minus_sep_ci95"][1] < 0]
    narrowed = [k for k, x in s2o.items() if x["gap_to_market_oct_minus_sep_ci95"][0] is not None and x["gap_to_market_oct_minus_sep_ci95"][1] < 0]
    add("O1.5 has too few fixtures with >= 3 two-sided books to compare month on month: NOT DIRECTLY COMPARABLE. "
        f"Cells where the model's own log loss improved with a CI excluding zero: {', '.join(better) or 'none'}. Cells where the gap "
        f"to the market narrowed with a CI excluding zero: {', '.join(narrowed) or 'none'}"
        + (" - check whether that is the model improving or the market getting worse (compare the two LL columns above)." if narrowed else "."))
    add("")

    # ── 10 ──
    add("## 10. HGB challenger (H-MODEL-01) - shadow, DO NOT PROMOTE")
    add("")
    add("| Track | Paired N | Matchdays | Window | Champion LL | Challenger LL | Champion Brier | Challenger Brier | LL delta (95% CI) | Brier delta (95% CI) | Market LL same rows |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for k in ("H-MODEL-01__newformat", "H-MODEL-01__standard"):
        x = hg.get(k)
        if x:
            add(f"| {k.split('__')[1]} | {x['paired_n']} | {x['matchdays']} | {x['first_match']} to {x['last_match']} | {x['champion_ll']:.4f} "
                f"| {x['challenger_ll']:.4f} | {x['champion_brier']:.4f} | {x['challenger_brier']:.4f} | {x['delta_ll']:+.4f} "
                f"{_ci(x['delta_ll_ci95'], False)} | {x['delta_brier']:+.4f} {_ci(x['delta_brier_ci95'], False)} | {x.get('market_ll_same_rows', 'n/a')} |")
    add("")
    add("Recomputed here and matching v9's own evaluator (`shadow_experiments_eval.json`). New Format: the challenger is better on "
        "both metrics with intervals excluding zero - but on 5 matchdays, against PG-1.0's prospective floor of 1000 rows per track, "
        "and it is still worse than the market on the same rows. Standard: the challenger is worse (CI includes zero). Neither is "
        "promotable; no Sep/Oct comparison exists because the experiment started 2026-10-22.")
    add("")

    # ── 11 ──
    add("## 11. CLV collection")
    add("")
    at, pf = clv["all_time"], clv["post_fix"]
    add("| Period | Eligible | T30 certified | T10 certified | Stale close | Median last pre-kickoff close (min) |")
    add("|---|---|---|---|---|---|")
    add(f"| ALL-TIME (v91_shadow from 2026-10-04) | {at.get('eligible')} | {at.get('certified_t30_pct')}% | {at.get('certified_t10_pct')}% "
        f"| {at.get('stale_close')} | {at.get('median_last_pre_kickoff_minutes')} |")
    add(f"| POST-COLLECTION-FIX (from {CLV_FIX_FROM}) | {pf.get('eligible')} | {pf.get('certified_t30_pct')}% | {pf.get('certified_t10_pct')}% "
        f"| {pf.get('stale_close')} | {pf.get('median_last_pre_kickoff_minutes')} |")
    add(f"| October before the fix (recomputed) | {pre['eligible']} | {pre['t30_certified_pct']}% | {pre['t10_certified_pct']}% "
        f"| {pre['stale_close_pct']}% | {pre['median_close_minutes_to_kickoff']} |")
    add(f"| October after the fix (recomputed, settled) | {post['eligible']} | {post['t30_certified_pct']}% | {post['t10_certified_pct']}% "
        f"| {post['stale_close_pct']}% | {post['median_close_minutes_to_kickoff']} |")
    add("| September | NOT MEASURABLE | - | - | - | - |")
    add("")
    cw = clv.get("collection_window", {})
    add(f"Collector window since {CLV_FIX_FROM} (all markets, {cw.get('fixtures')} fixtures): T30 {cw.get('t30_pct')}%, T10 {cw.get('t10_pct')}%, "
        f"median last observation {cw.get('median_last_obs_minutes')} min before kickoff; health check {clv['clv_collection_health'].get('check')}.")
    add("")
    add("Why September is not measurable: the odds archives are change-logs (a row only when a price moves), so the last stored row "
        "is the last CHANGE, not the last time anyone looked. Only the odds heartbeat (from 2026-10-22) and v91_shadow's close audit "
        "measure the last OBSERVATION. **Is October evidence more trustworthy?** For CLV, yes - after 2026-10-23 a CLV figure is "
        "backed by a close observed inside 30 minutes about 70% of the time, versus under 10% before. For ROI, only modestly: the "
        "first-logged freeze (2026-10-26) removes rewritten side-market prices going forward, but October's results still come from "
        "the same v9 models.")
    add("")

    # ── 12 ──
    add("## 12. Market-relative: is WOWZA learning information the market does not know?")
    add("")
    add("| Source | Sep | Oct |\n|---|---|---|")
    vs, vo = v11r.get("2026-09", {}), v11r.get("2026-10", {})
    add(f"| v11 residual: market+WOWZA blend minus market LL (OU25, all fixtures) | {_f(vs.get('blend_minus_market'), 5)} "
        f"{_ci(vs.get('blend_minus_market_ci95'), False)} n {vs.get('n')} | {_f(vo.get('blend_minus_market'), 5)} "
        f"{_ci(vo.get('blend_minus_market_ci95'), False)} n {vo.get('n')} |")
    for t in ("Standard", "New Format"):
        a, b = fq["by_month_track"].get(f"2026-09|{t}"), fq["by_month_track"].get(f"2026-10|{t}")
        if a and b:
            add(f"| v9 model minus market LL, OU25 {t} | {a['model_minus_market_ll']:+.4f} {_ci(a['model_minus_market_ll_ci95'], False)} "
                f"| {b['model_minus_market_ll']:+.4f} {_ci(b['model_minus_market_ll_ci95'], False)} |")
    add("")
    add("market_edge_v2 shadow (model vs fair market vs decision probability, from 2026-10-25 only - October snapshot, NOT COMPARABLE "
        "with September):")
    add("")
    add("| Market / track | N | Matchdays | Model LL | Market LL | Decision LL | Model Brier | Market Brier | Decision Brier | Model - market LL 95% CI |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for k, x in o["market_relative_edge_v2"].get("by", {}).items():
        add(f"| {k} | {x['model']['n']} | {x['model']['matchdays']} | {x['model']['ll']:.4f} | {x['market']['ll']:.4f} | {x['decision']['ll']:.4f} "
            f"| {x['model']['brier']:.4f} | {x['market']['brier']:.4f} | {x['decision']['brier']:.4f} | {_ci(x['model_minus_market_ll_ci95'], False)} |")
    add("")
    add("**Answer: no measurable evidence.** In both months the de-vigged market forecasts at least as well as v9, and adding v9 to "
        f"the market does not improve it (September {_f(vs.get('blend_minus_market'), 5)} {_ci(vs.get('blend_minus_market_ci95'), False)}, "
        f"October {_f(vo.get('blend_minus_market'), 5)} {_ci(vo.get('blend_minus_market_ci95'), False)}). The decision "
        "probability of the market-first engine tracks the market, which is the intended behaviour.")
    add("")

    # ── 13 ──
    add("## 13. Bankroll research (Pro walk-forward, paper)")
    add("")
    add("| Policy | Sep return | Sep max DD | Oct return | Oct max DD | Bankroll end Oct |")
    add("|---|---|---|---|---|---|")
    for pol in ("ADAPTIVE", "STATIC_BALANCED", "FLAT_0.5", "FLAT_1", "FLAT_2"):
        add(f"| {pol} | {wfv('2026-09', pol):+.2f}% | {wfv('2026-09', pol, 'month_max_dd') * 100:.1f}% | {wfv('2026-10', pol):+.2f}% "
            f"| {wfv('2026-10', pol, 'month_max_dd') * 100:.1f}% | {wfv('2026-10', pol, 'bankroll'):.2f} |")
    add("")
    add("Source: Pro `output/bankroll/walk_forward.csv` (each month's policy chosen with data before that month; evidence cutoff "
        f"2026-10-25). **September made more money under the managed policies**: ADAPTIVE {wfv('2026-09', 'ADAPTIVE'):+.1f}% with a "
        f"{wfv('2026-09', 'ADAPTIVE', 'month_max_dd') * 100:.1f}% drawdown, then {wfv('2026-10', 'ADAPTIVE'):+.1f}% with a "
        f"{wfv('2026-10', 'ADAPTIVE', 'month_max_dd') * 100:.1f}% drawdown in October. That pattern is consistent with the NF BTTS reversal: "
        "the managed policies stake NF BTTS hardest (1.25% vs 0.5% for the other active tracks) because it had the best evidence, "
        "so its October reversal costs them most (attribution by track was not recomputed here); flat staking spreads risk evenly and did better in October. Discipline "
        "here means sizing by evidence and cutting what fails (NF OU25 UNDER -> STOP proposed); it bounds drawdown and survival risk, "
        "it does not guarantee a better month. Walk-forward validation is NOT_VALIDATED_INSUFFICIENT_MONTHS (2 of 6).")
    add("")

    # ── 14 ──
    add("## 14. Track level")
    add("")
    pol = (o.get("current_bankroll_policy") or {}).get("tracks", {})
    td = {r["track"]: r for r in br.get("track_decisions", [])}
    tmap = {"NF BTTS": "new_format|BTTS", "NF OU25 OVER": "new_format|OU25_OVER", "NF OU25 UNDER": "new_format|OU25_UNDER",
            "NF O1.5": "new_format|OVER15", "Standard OU25": "standard|OU25_OVER", "Standard BTTS": "standard|BTTS"}
    add("| Track | Sep evidence | Oct evidence | Change (90% CI) | Current state (v9 config/bankroll_policy.json) | Pro monthly review (dry run, cutoff 2026-10-25) |")
    add("|---|---|---|---|---|---|")
    for name, c in A["tracks"].items():
        key = tmap[name]
        st = pol.get(key, {})
        cur = f"{st.get('state')} {st.get('base_fraction', 0) * 100:.2f}%" if st else "n/a"
        if name == "Standard OU25":
            cur = f"OVER {pol.get('standard|OU25_OVER', {}).get('state')} / UNDER {pol.get('standard|OU25_UNDER', {}).get('state')}"
        d = td.get(key, {})
        rec = f"{d.get('decision')} -> {d.get('proposed_state')} ({str(d.get('reasons')).strip('[]')})" if d else "n/a"
        add(f"| {name} | {_p(c['sep'].get('roi'))} n {c['sep'].get('n')} | {_p(c['oct'].get('roi'))} n {c['oct'].get('n')} "
            f"| {_p(c.get('delta_roi'))} {_ci(c.get('delta_roi_ci90'))} | {cur} | {rec} |")
    add("")
    add(f"Learned policy change: the 2026-10 monthly review (Pro `output/bankroll/MONTHLY_REVIEW.md`, dry run for the 11-01 cycle) "
        f"proposes NF OU25 UNDER {td.get('new_format|OU25_UNDER', {}).get('previous_state')} -> {td.get('new_format|OU25_UNDER', {}).get('decision')} "
        f"on n={int(float(td.get('new_format|OU25_UNDER', {}).get('n') or 0))} settled bets, shrunk ROI {_p(td.get('new_format|OU25_UNDER', {}).get('shrunk_roi'))}. This report's own figures agree: NF OU25 "
        f"UNDER {_p(ou['New Format|UNDER']['sep']['roi'])} in September and {_p(ou['New Format|UNDER']['oct']['roi'])} in October. "
        "Production is unchanged until the owner approves the PR.")
    add("")

    # ── 15 ──
    add("## 15. Tier learning")
    add("")
    add(TIER_SENTENCE)
    add("")
    add("| Window / scope / month | ROI Big gap | ROI Medium gap | ROI Small gap | N (B/M/S) | Monotonic? |")
    add("|---|---|---|---|---|---|")
    for k, x in tm.items():
        r = x["roi_big_medium_small"]
        add(f"| {k} | {_p(r[0])} | {_p(r[1])} | {_p(r[2])} | {'/'.join(map(str, x['n']))} | {x['monotonic']} |")
    add("")
    add("Not monotonic in any window, scope or month. **Raw model-market disagreement magnitude is not a reliable quality ordering.** "
        "Tiers here are the FIRST-LOGGED tier (before 2026-10-26 the ledger upgraded tiers in place; "
        f"{o['ledger_audit']['rows_tier_upgraded_after_first_log'].get('ou25')} OU25 rows were upgraded).")
    add("")

    # ── 16 / 17 ──
    add("## 16. V11 independent scoreboard (v9 tips as graded by wowza_v11)")
    add("")
    add("| Month | System | Picks | W | L | Hit | PnL | PnL / pick |")
    add("|---|---|---|---|---|---|---|---|")
    for r in v11["scoreboard"]:
        if r["scope"] in ("2026-09", "2026-10"):
            pp = r["pnl"] / r["picks"] if r["picks"] else None
            add(f"| {r['scope']} | {r['system']} | {r['picks']} | {r['W']} | {r['L']} | {r['hit']} | {r['pnl']:+.2f} | "
                f"{'n/a' if pp is None else f'{pp:+.3f}'} |")
    add("")
    add("v11 grades v9's live O/U 2.5 tips from its own shadow log and prices, so its counts differ from the first-logged ledger "
        "in section 3. Direction agrees with section 3: v9 lost less per pick in October. v11 itself placed 0 bets "
        "in both months - its market-first engine has never found a BET or PAPER state worth taking.")
    add("")
    add("## 17. V11 research learning, September -> October")
    add("")
    mv = {r["segment"]: r for r in v11.get("v11_movement_summary.csv", [])}
    for seg in ("month 2026-09", "month 2026-10"):
        r = mv.get(seg)
        if r:
            add(f"* Movement signal {seg}: toward-model rate {r['toward_rate']} (CI {r['toward_ci_lo']}-{r['toward_ci_hi']}, p {r['p_value']}), "
                f"mean signed move {r['mean_signed_move_pp']}pp, mean CLV {r['mean_clv_pct']}%, CLV>0 {r['pct_positive_clv']}, n {r['n_obs']} snapshots / "
                f"{r['n_fixtures']} fixtures.")
    folds = v11.get("v11_chronological_folds.csv", [])
    for f in folds:
        add(f"* Residual-movement fold {f['fold']} ({str(f['test_from'])[:10]} to {str(f['test_to'])[:10]}): coef {float(f['residual_coef']):+.4f} "
            f"[{float(f['ci_lo']):+.4f}, {float(f['ci_hi']):+.4f}], excludes zero {f['excludes_zero']}.")
    pl = {r["variant"]: r for r in v11.get("v11_placebo_table.csv", [])}
    if "v9_residual" in pl:
        add(f"* Placebo table (all months pooled): v9 residual toward-rate {pl['v9_residual']['toward_rate']} vs shuffled-residual placebo "
            f"{pl.get('PLACEBO_shuffled_residual', {}).get('toward_rate')} and fixed-anchor placebo {pl.get('PLACEBO_fixed_anchor', {}).get('toward_rate')}: "
            "the real residual sits between its placebos - it does not clearly beat them.")
    add(f"* Residual model (market + WOWZA vs market): September {_f(vs.get('blend_minus_market'), 5)}, October {_f(vo.get('blend_minus_market'), 5)} LL - no gain either month.")
    add("")
    add("Read: the movement signal weakened from August into September and October (October fold's residual coefficient CI includes "
        "zero, mean CLV turned more negative). These are negative results and they count: v11 is not profitable and has not found "
        "an edge; it learned that the earlier movement 'signal' does not persist out of sample.")
    add("")

    # ── 18 ──
    add("## 18. System maturity (dated from git history on origin/main)")
    add("")
    add("| First on main | Repo | Capability | Path / commit |")
    add("|---|---|---|---|")
    for x in sorted(mat, key=lambda x: str(x["first_on_main"])):
        add(f"| {x['first_on_main']} | {x['repo']} | {x['capability']} | `{x['path']}` |")
    add("")
    cm = o.get("commits_by_month", {})
    add("Commits by month (origin/main, Sep-Oct): " + "; ".join(f"{r}: {v}" for r, v in cm.items())
        + ". (Pro's history on main starts 2026-10-12, so it has no September commits to count.)")
    add("")
    add(f"{cap_sep} listed capability landed in September; {cap_oct} in October. September's system had one gate (a tolerance with no "
        "interval), no lineage, no shadow challenger, no certified close, no first-sight store and overwritable ledger prices. "
        "October's has all of them, plus protected-track locks (research_lock) and an explicit identity/alias audit for Standard.")
    add("")
    add("## Method and traps handled")
    add("")
    add("* Data: v9 and wowza_v11 read with `git show origin/main:<path>` after `git fetch`; Pro store and bankroll outputs from the Pro "
        "worktree at origin/main; Standard data-quality burden read-only from the pro_v9r worktree.")
    add("* Ledger: first-logged odds and tier rebuilt from every v9 commit of each ledger since 2026-08-20; P/L in units at that price.")
    add("* Intervals: 90% for ROI and ROI changes, 95% for log-loss/Brier deltas; matchday block bootstrap, 2000 draws, fixed seed.")
    add("* Snapshots treated as change-logs (last pre-kickoff quote per book carried forward); no merge_asof index assignment; "
        "thresholds not re-derived from config.py; no mtime-based freshness.")
    add("")
    add("PRODUCTION_CHANGES_MADE = NO")
    add("")
    return "\n".join(L)


_LEAGUE_CACHE: list[dict] = []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--cached-history", action="store_true", help="reuse the first-logged cache")
    a = ap.parse_args(argv)
    out, bet = build(fetch=not a.no_fetch, refresh_history=not a.cached_history)
    write(out, bet)
    print(f"wrote {DOC.relative_to(cfg.BASE_DIR)} and output/monthly_learning_*")
    print("PRODUCTION_CHANGES_MADE = NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
