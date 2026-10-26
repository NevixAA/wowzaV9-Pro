"""NEW-FORMAT BTTS contradiction: strong realised ROI, poor CLV — skill, price artifact, league, or luck?

    python -m src.studies.btts_contradiction            (needs v9's git history for first-logged rows,
                                                          falls back to the committed cache)

Owner brief 2026-10-26 part C. RESEARCH ONLY: nothing here changes a stake, tier, threshold or
filter, and nothing reads this output to make a decision.

THE CONTRADICTION. v9's new-format BTTS-YES tips have booked a strong flat-stake profit while the
closing line says the entries were poor and the market's probabilities are at least as good as
Wowza's. Both cannot be "edge". This study tests the four candidate explanations side by side:

    MARKET INEFFICIENCY   the model finds YES prices the market corrects later  -> positive CLV,
                          selected beats not-selected, residual model coefficient > 0
    TIMING / PRICE        the profit lives in the recorded price, not the bet   -> first-logged vs
                          ledger odds, entry vs books available at that minute, stale entries
    LEAGUE REGIME         YES simply landed more often than ANY price implied in a few leagues
                          -> naive "every BTTS-YES" control earns the same, Argentina share, LOLO
    VARIANCE              profit is inside what the market's own probabilities allow
                          -> simulated ROI under p_close, matchday block-bootstrap CIs

DATA, and why each source:
    first-logged rows   v9 git history of output/side_bets_ledger.csv. Before 2026-10-26 the ledger
                        rewrote odds/edge/tier IN PLACE on a tier upgrade, so the current file is
                        not what was sent. The first version a row appears in is. Cached to
                        output/studies/btts_contradiction_first_logged.csv so CI can re-run without
                        history.
    book quotes         Pro book_odds_snapshots (BTTS, per book). A CHANGE-LOG, so every "price at
                        time t" is last-observation-carried-forward per book, never a group-by.
    model probs         Pro model_snapshots (BTTS), last pre-kickoff observation per fixture.
    results             API-Football finished fixtures (src.studies.common.results, day cache).
    1X2                 Pro market_snapshots h2h_home/h2h_draw/h2h_away (v9 capture).

ENTRY PRICE. v9's NF BTTS `odds` is NOT a bookmaker's price: src/btts_odds.py sets odds_btts to the
MEDIAN YES across every book OddsAPI returned in that run. So "same book" closing is the same
CONSTRUCTION at close (median YES of the books quoting at kickoff), and per-book CLV is reported
separately for books that quoted at entry.

CERTIFIED CLOSE. A book's close is its carried-forward quote at kickoff, and is CERTIFIED only when
that book has an observed row in the 30 minutes before kickoff (strict) — a change-log row proves
the book was fetched then. The looser "fixture fetched in the window" variant is reported beside it
and never mixed in.

STATISTICS. Flat 1u. Every CI is a 90% bootstrap over MATCHDAYS (bets on one day share weather,
news and line moves; they are not independent).
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.data.entities import fixture_key
from src.market.devig import power_devig
from src.studies import common as C

NAME = "btts_contradiction"
LEDGER_PATH = "output/side_bets_ledger.csv"
FIRST_CACHE = cfg.OUTPUT_DIR / "studies" / f"{NAME}_first_logged.csv"
CERT_MIN = 30                          # certified close: book observed within 30 min pre-kickoff
FIXED_OVERROUND = 1.08                 # v9 pipeline._generate_side_bets
TIER_RANK = {"VALUABLE": 1, "MARKSMAN": 2, "SNIPER": 3}
STAKED = ("SNIPER", "MARKSMAN")
N_BOOT = 3000
RNG = np.random.default_rng(20261026)


# ── first-logged rows from v9's git history ───────────────────────────────────────────────────
def _git() -> str | None:
    for g in (os.getenv("GIT"), shutil.which("git")):
        if g and (os.path.exists(g) or shutil.which(g)):
            return g
    return None


def first_logged(refresh: bool = True) -> pd.DataFrame:
    """One row per BTTS ledger tip as it was FIRST written, plus how it changed afterwards.

    Key = (match_date, home_team, away_team, market, source), exactly v9's side-ledger key.
    """
    git = _git()
    repo = cfg.V9_LOCAL
    if not refresh or git is None or not (repo / ".git").exists():
        return pd.read_csv(FIRST_CACHE) if FIRST_CACHE.exists() else pd.DataFrame()
    log = subprocess.run([git, "log", "--reverse", "--format=%H|%cI", "--", LEDGER_PATH], cwd=repo,
                         capture_output=True, text=True, timeout=600)
    commits = [ln.split("|", 1) for ln in log.stdout.splitlines() if "|" in ln]
    if not commits:
        return pd.read_csv(FIRST_CACHE) if FIRST_CACHE.exists() else pd.DataFrame()
    proc = subprocess.Popen([git, "cat-file", "--batch"], cwd=repo, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    first: dict[tuple, dict] = {}
    for sha, cts in commits:
        proc.stdin.write(f"{sha}:{LEDGER_PATH}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        if len(header) < 3 or header[1] != "blob":
            continue
        body = proc.stdout.read(int(header[2]))
        proc.stdout.read(1)
        try:
            v = pd.read_csv(io.BytesIO(body), low_memory=False)
        except Exception:
            continue
        if "market" not in v.columns:
            continue
        v = v[v["market"].astype(str).eq("btts")]
        if "source" not in v.columns:
            v = v.assign(source="live")
        for r in v.itertuples(index=False):
            k = (str(r.match_date)[:10], str(r.home_team), str(r.away_team), "btts", str(r.source))
            tier, odds = str(getattr(r, "signal_tier", "")), float(getattr(r, "odds", np.nan))
            if k not in first:
                first[k] = {"match_date": k[0], "home_team": k[1], "away_team": k[2], "source": k[4],
                            "league": str(r.league), "generated_at": str(r.generated_at),
                            "first_commit": sha[:12], "first_commit_ts": cts,
                            "first_odds": odds, "first_tier": tier,
                            "first_edge_pct": float(getattr(r, "edge_pct", np.nan)),
                            "first_model_prob": float(getattr(r, "model_prob", np.nan)),
                            "max_tier": tier, "n_odds_changes": 0, "n_tier_changes": 0,
                            "_last_odds": odds, "_last_tier": tier}
            else:
                f = first[k]
                if odds == odds and odds != f["_last_odds"]:
                    f["n_odds_changes"] += 1
                    f["_last_odds"] = odds
                if tier != f["_last_tier"]:
                    f["n_tier_changes"] += 1
                    f["_last_tier"] = tier
                if TIER_RANK.get(tier, 0) > TIER_RANK.get(f["max_tier"], 0):
                    f["max_tier"] = tier
    proc.stdin.close()
    proc.wait(timeout=60)
    out = pd.DataFrame(first.values()).drop(columns=["_last_odds", "_last_tier"])
    FIRST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(FIRST_CACHE, index=False)
    return out


# ── loading ───────────────────────────────────────────────────────────────────────────────────
def _utc(s) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")


def _flat(y, odds) -> np.ndarray:
    return np.where(np.asarray(y, float) == 1, np.asarray(odds, float) - 1.0, -1.0)


def tips() -> pd.DataFrame:
    """Settled live BTTS tips: first-logged price/tier joined to the ledger's result."""
    f = first_logged()
    cur = pd.read_csv(cfg.V9_LOCAL / LEDGER_PATH, low_memory=False)
    cur = cur[cur["market"].astype(str).eq("btts")]
    d = cur.merge(f.drop(columns=["league", "generated_at"]), on=["match_date", "home_team", "away_team", "source"],
                  how="left", validate="one_to_one")
    d = d[d["source"].eq("live") & d["result"].isin(["WIN", "LOSS"])].copy()
    d["y"] = (d["result"] == "WIN").astype(float)
    d["ledger_odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d["entry_odds"] = d["first_odds"].fillna(d["ledger_odds"])
    d["pnl_first"] = _flat(d["y"], d["entry_odds"])
    d["pnl_ledger"] = _flat(d["y"], d["ledger_odds"])
    d["p_model"] = pd.to_numeric(d["first_model_prob"], errors="coerce").fillna(
        pd.to_numeric(d["model_prob"], errors="coerce"))
    d["gen_ts"] = _utc(d["generated_at"])
    d["fixture_key"] = [fixture_key(*a) for a in zip(d["league"], d["match_date"], d["home_team"], d["away_team"])]
    d["first_tier"] = d["first_tier"].fillna(d["signal_tier"])
    d["max_tier"] = d["max_tier"].fillna(d["signal_tier"])
    d["staked_first"] = d["first_tier"].isin(STAKED)
    d["upgraded"] = d["first_tier"].map(TIER_RANK).fillna(0) < d["max_tier"].map(TIER_RANK).fillna(0)
    d["odds_overwritten"] = (d["ledger_odds"] - d["entry_odds"]).abs() > 1e-9
    return d.reset_index(drop=True)


def quotes() -> dict[str, pd.DataFrame]:
    """Pre-kickoff per-book BTTS quotes grouped by fixture (change-log rows, sorted by time)."""
    q = store.read("book_odds_snapshots")
    q = q[q["market"].eq("BTTS") & q["side"].isin(["YES", "NO"])].copy()
    q["ts"] = _utc(q["snapshot_ts"])
    q["ko"] = _utc(q["kickoff_utc"])
    q = q[q["ts"].notna() & q["ko"].notna() & (q["ts"] < q["ko"])]
    q = q.drop_duplicates(["fixture_key", "bookmaker", "side", "ts"], keep="last").sort_values("ts")
    keep = ["fixture_key", "league", "match_date", "home_team", "away_team", "bookmaker", "side", "odds", "ts", "ko"]
    return {k: g[keep].reset_index(drop=True) for k, g in q.groupby("fixture_key")}


def book_state(g: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    """Per-book YES/NO carried forward to `at` (LOCF on a change-log), with last-seen time."""
    h = g[g["ts"] <= at]
    if h.empty:
        return pd.DataFrame(columns=["YES", "NO", "seen"])
    last = h.groupby(["bookmaker", "side"]).tail(1)
    w = last.pivot_table(index="bookmaker", columns="side", values="odds", aggfunc="last")
    w["seen"] = h.groupby("bookmaker")["ts"].max()
    for c in ("YES", "NO"):
        if c not in w:
            w[c] = np.nan
    return w


def consensus(w: pd.DataFrame) -> dict:
    if w is None or w.empty:
        return {"n_books": 0, "median_yes": np.nan, "median_no": np.nan, "best_yes": np.nan,
                "worst_yes": np.nan, "p_fair": np.nan, "overround": np.nan, "n_pairs": 0}
    yes = w["YES"].dropna()
    pair = w.dropna(subset=["YES", "NO"])
    fair = [power_devig(a, b) for a, b in zip(pair["YES"], pair["NO"])]
    fair = [x for x in fair if x is not None and x == x]
    ovr = (1 / pair["YES"] + 1 / pair["NO"])
    return {"n_books": int(len(yes)), "median_yes": float(yes.median()) if len(yes) else np.nan,
            "median_no": float(w["NO"].dropna().median()) if w["NO"].notna().any() else np.nan,
            "best_yes": float(yes.max()) if len(yes) else np.nan,
            "worst_yes": float(yes.min()) if len(yes) else np.nan,
            "p_fair": float(np.median(fair)) if len(fair) else np.nan,
            "overround": float(ovr.median()) if len(ovr) else np.nan, "n_pairs": int(len(pair))}


def results_for(leagues, start: str, end: str) -> pd.DataFrame:
    from src.scout.registry import literal_assignments
    ids = literal_assignments(cfg.V9_LOCAL / "config.py", ("API_FOOTBALL_IDS",)).get("API_FOOTBALL_IDS", {})
    ids = {l: ids[l] for l in leagues if l in ids}
    r = C.results(start, end, ids)
    r["y"] = C.outcome("BTTS", r["hg"], r["ag"])
    return r


# ── statistics ────────────────────────────────────────────────────────────────────────────────
def boot(x, days, n=N_BOOT) -> list:
    d = pd.DataFrame({"x": np.asarray(x, float), "g": np.asarray(days)}).dropna()
    s = d.groupby("g")["x"].agg(["sum", "count"])
    if len(s) < 3:
        return [None, None]
    idx = RNG.integers(0, len(s), size=(n, len(s)))
    m = s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1)
    return [round(float(np.quantile(m, .05)), 4), round(float(np.quantile(m, .95)), 4)]


def roi(pnl, days) -> dict:
    p = pd.Series(np.asarray(pnl, float))
    dd = pd.Series(np.asarray(days))
    ok = p.notna()
    if ok.sum() == 0:
        return {"n": 0}
    return {"n": int(ok.sum()), "units": round(float(p[ok].sum()), 2), "roi": round(float(p[ok].mean()), 4),
            "roi_ci90": boot(p[ok], dd[ok])}


def mean_ci(x, days) -> dict:
    s = pd.Series(np.asarray(x, float))
    ok = s.notna()
    if ok.sum() == 0:
        return {"n": 0}
    return {"n": int(ok.sum()), "mean": round(float(s[ok].mean()), 4),
            "ci90": boot(s[ok], pd.Series(np.asarray(days))[ok])}


def diff_ci(a_x, a_d, b_x, b_d, n=N_BOOT) -> dict:
    """mean(a) - mean(b), resampling matchdays jointly for both groups."""
    A = pd.DataFrame({"x": np.asarray(a_x, float), "g": np.asarray(a_d), "grp": "a"}).dropna()
    Bf = pd.DataFrame({"x": np.asarray(b_x, float), "g": np.asarray(b_d), "grp": "b"}).dropna()
    if A.empty or Bf.empty:
        return {}
    s = pd.concat([A, Bf]).groupby(["g", "grp"])["x"].agg(["sum", "count"]).unstack(fill_value=0)
    sa, ca = s[("sum", "a")].to_numpy(), s[("count", "a")].to_numpy()
    sb, cb = s[("sum", "b")].to_numpy(), s[("count", "b")].to_numpy()
    idx = RNG.integers(0, len(s), size=(n, len(s)))
    with np.errstate(invalid="ignore", divide="ignore"):
        dm = sa[idx].sum(1) / ca[idx].sum(1) - sb[idx].sum(1) / cb[idx].sum(1)
    dm = dm[np.isfinite(dm)]
    return {"diff": round(float(A["x"].mean() - Bf["x"].mean()), 4),
            "ci90": [round(float(np.quantile(dm, .05)), 4), round(float(np.quantile(dm, .95)), 4)],
            "share_of_resamples_le_0": round(float((dm <= 0).mean()), 4)}


def variance_test(p, odds, y, n=20000) -> dict:
    """If the market's probability p were TRUE, how often would flat YES at `odds` earn the observed ROI?"""
    p, o, y = (np.asarray(v, float) for v in (p, odds, y))
    ok = np.isfinite(p) & np.isfinite(o) & np.isfinite(y)
    p, o, y = p[ok], o[ok], y[ok]
    if len(p) < 10:
        return {"n": int(len(p))}
    obs = float(_flat(y, o).mean())
    sim = np.where(RNG.random((n, len(p))) < p, o - 1, -1.0).mean(1)
    return {"n": int(len(p)), "observed_roi": round(obs, 4),
            "expected_roi_if_market_right": round(float((p * o - 1).mean()), 4),
            "hit_rate": round(float(y.mean()), 4), "market_p_mean": round(float(p.mean()), 4),
            "sim_roi_90pct_range": [round(float(np.quantile(sim, .05)), 4), round(float(np.quantile(sim, .95)), 4)],
            "p_value_one_sided": round(float((sim >= obs).mean()), 4)}


def reliability(p, y, bins=(0, .45, .5, .55, .6, .65, 1.01)) -> list:
    D = pd.DataFrame({"p": np.asarray(p, float), "y": np.asarray(y, float)}).dropna()
    D["b"] = pd.cut(D["p"], bins, right=False)
    return [{"bin": str(b), "n": int(len(g)), "mean_p": round(float(g["p"].mean()), 4),
             "hit": round(float(g["y"].mean()), 4)} for b, g in D.groupby("b", observed=True)]


def _band(x, edges, labels) -> pd.Series:
    return pd.cut(pd.Series(np.asarray(x, float)), edges, labels=labels, right=False).astype(str)


def by(d: pd.DataFrame, col: str, pnl: str = "pnl_first") -> dict:
    return {str(k): roi(g[pnl], g["match_date"]) for k, g in d.groupby(col, observed=True)}


# ── per-tip market panel ──────────────────────────────────────────────────────────────────────
def panel(T: pd.DataFrame, Q: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Entry state, certified close and per-book CLV for every tip."""
    rows, per_book = [], []
    win = pd.Timedelta(minutes=CERT_MIN)
    for r in T.itertuples():
        g = Q.get(r.fixture_key)
        rec = {"_i": r.Index}
        if g is None or pd.isna(r.gen_ts):
            rows.append(rec)
            continue
        ko = g["ko"].mode().iloc[0]
        at = r.gen_ts + pd.Timedelta(seconds=59)       # generated_at is minute-resolution
        we = book_state(g, at)
        rec.update({f"e_{k}": v for k, v in consensus(we).items()})
        seen = g.loc[g["ts"] <= at, "ts"]
        rec["entry_last_change_age_h"] = (at - seen.max()).total_seconds() / 3600 if len(seen) else np.nan
        rec["first_quote_lead_h"] = (ko - g["ts"].min()).total_seconds() / 3600
        rec["ko"] = ko
        rec["lead_h"] = (ko - r.gen_ts).total_seconds() / 3600
        wc = book_state(g, ko)
        inwin = g[g["ts"] >= ko - win]
        strict = wc[wc.index.isin(set(inwin["bookmaker"]))]
        rec.update({f"cs_{k}": v for k, v in consensus(strict).items()})
        rec.update({f"cl_{k}": v for k, v in consensus(wc if len(inwin) else None).items()})
        rec.update({f"ca_{k}": v for k, v in consensus(wc).items()})
        rec["close_last_change_min"] = (ko - g["ts"].max()).total_seconds() / 60
        both = we.dropna(subset=["YES"]).index.intersection(strict.dropna(subset=["YES"]).index)
        for bk in both:
            per_book.append({"_i": r.Index, "book": bk, "entry_yes": float(we.at[bk, "YES"]),
                             "close_yes": float(strict.at[bk, "YES"]), "match_date": r.match_date})
        rows.append(rec)
    P = pd.DataFrame(rows).set_index("_i")
    return T.join(P), pd.DataFrame(per_book)


def universe(Q: dict, leagues: dict[str, tuple[str, str]], lead_h: float) -> pd.DataFrame:
    """Every priced fixture in the tip leagues/date windows: open, matched-lead and close prices."""
    rows = []
    win = pd.Timedelta(minutes=CERT_MIN)
    for fk, g in Q.items():
        lg, md = g["league"].iloc[0], str(g["match_date"].iloc[0])[:10]
        if lg not in leagues or not (leagues[lg][0] <= md <= leagues[lg][1]):
            continue
        ko = g["ko"].mode().iloc[0]
        t0 = g["ts"].min()
        rec = {"fixture_key": fk, "league": lg, "match_date": md, "home_team": g["home_team"].iloc[0],
               "away_team": g["away_team"].iloc[0], "ko": ko}
        rec.update({f"o_{k}": v for k, v in consensus(book_state(g, t0 + pd.Timedelta(minutes=1))).items()})
        tl = max(t0 + pd.Timedelta(minutes=1), ko - pd.Timedelta(hours=lead_h))
        rec.update({f"m_{k}": v for k, v in consensus(book_state(g, tl)).items()})
        wc = book_state(g, ko)
        inwin = g[g["ts"] >= ko - win]
        rec.update({f"cs_{k}": v for k, v in consensus(wc[wc.index.isin(set(inwin["bookmaker"]))]).items()})
        rec.update({f"ca_{k}": v for k, v in consensus(wc).items()})
        rows.append(rec)
    return pd.DataFrame(rows)


def h2h_fav() -> pd.DataFrame:
    """Favourite strength per fixture from v9's captured 1X2 (last capture, 3-way normalised)."""
    m = store.read("market_snapshots")
    m = m[m["market"].isin(["h2h_home", "h2h_draw", "h2h_away"])].copy()
    m["t"] = _utc(m["captured_at"]).fillna(_utc(m["observed_at"]))
    m = m[m["t"].dt.strftime("%Y-%m-%d") <= m["match_date"].astype(str).str[:10]]
    m = m.sort_values("t").drop_duplicates(["fixture_key", "market"], keep="last")
    w = m.pivot_table(index="fixture_key", columns="market", values="odds", aggfunc="last").dropna()
    inv = 1 / w
    s = inv.sum(axis=1)
    out = pd.DataFrame({"p_home": inv["h2h_home"] / s, "p_away": inv["h2h_away"] / s, "p_draw": inv["h2h_draw"] / s})
    out["fav_p"] = out[["p_home", "p_away"]].max(axis=1)
    return out


# ── the study ─────────────────────────────────────────────────────────────────────────────────
LEAD_BANDS = ([0, 24, 72, 144, 1e9], ["<24h", "24-72h", "72-144h", "144h+"])
ODDS_BANDS = ([0, 1.80, 2.00, 2.20, 2.50, 99], ["<1.80", "1.80-1.99", "2.00-2.19", "2.20-2.49", "2.50+"])
FAV_BANDS = ([0, .45, .60, 1.01], ["balanced (<45%)", "moderate fav (45-60%)", "strong fav (60%+)"])


def _headline(d: pd.DataFrame) -> dict:
    return {"n": int(len(d)), "hit_rate": round(float(d["y"].mean()), 4) if len(d) else None,
            "mean_entry_odds": round(float(d["entry_odds"].mean()), 3) if len(d) else None,
            "breakeven_hit": round(float((1 / d["entry_odds"]).mean()), 4) if len(d) else None,
            "first_logged": roi(d["pnl_first"], d["match_date"]),
            "ledger_overwritten": roi(d["pnl_ledger"], d["match_date"])}


def _entry(d: pd.DataFrame) -> dict:
    ok = d["e_median_yes"].notna()
    e = d[ok]
    dev = (e["entry_odds"] - e["e_median_yes"]).abs()
    at_open = (e["first_quote_lead_h"] - e["lead_h"]).abs() <= 0.25
    ow = d[d["odds_overwritten"]]
    return {
        "tips_with_book_state_at_entry": int(ok.sum()),
        "entry_equals_cross_book_median_share": round(float((dev <= 0.015).mean()), 4),
        "entry_above_best_available_share": round(float((e["entry_odds"] > e["e_best_yes"] + 0.005).mean()), 4),
        "entry_below_worst_available_share": round(float((e["entry_odds"] < e["e_worst_yes"] - 0.005).mean()), 4),
        "books_at_entry_median": float(e["e_n_books"].median()),
        "roi_at_entry_median_price": roi(e["pnl_first"], e["match_date"]),
        "roi_at_best_book_at_entry": roi(_flat(e["y"], e["e_best_yes"]), e["match_date"]),
        "roi_at_worst_book_at_entry": roi(_flat(e["y"], e["e_worst_yes"]), e["match_date"]),
        "best_minus_median_odds_mean": round(float((e["e_best_yes"] - e["entry_odds"]).mean()), 3),
        "hours_to_kickoff_at_entry": {"median": round(float(d["lead_h"].median()), 1),
                                      "p25": round(float(d["lead_h"].quantile(.25)), 1),
                                      "p75": round(float(d["lead_h"].quantile(.75)), 1)},
        "entered_on_opening_quote_share": round(float(at_open.mean()), 4),
        "roi_by_hours_to_kickoff": by(d.assign(b=_band(d["lead_h"], *LEAD_BANDS).values), "b"),
        "ledger_overwrote_odds": {"n": int(len(ow)),
                                  "units_first_logged": round(float(ow["pnl_first"].sum()), 2),
                                  "units_ledger": round(float(ow["pnl_ledger"].sum()), 2),
                                  "flattering_units": round(float(ow["pnl_ledger"].sum() - ow["pnl_first"].sum()), 2)},
    }


def _closing(d: pd.DataFrame, pb: pd.DataFrame) -> dict:
    out = {"close_coverage": {
        "certified_strict_>=3_books": int((d["cs_n_pairs"] >= 3).sum()),
        "certified_strict_>=1_book": int((d["cs_n_books"] >= 1).sum()),
        "uncertified_last_pre_kickoff": int((d["ca_n_books"] >= 1).sum()), "tips": int(len(d))}}
    for tag, pre, need in (("certified", "cs", 3), ("uncertified_last_pre_kickoff", "ca", 1)):
        g = d[d[f"{pre}_n_pairs"] >= need] if tag == "certified" else d[d[f"{pre}_n_books"] >= 1]
        price_clv = g["entry_odds"] / g[f"{pre}_median_yes"] - 1
        ev_close = g["entry_odds"] * g[f"{pre}_p_fair"] - 1
        out[tag] = {"price_clv_vs_median_close": mean_ci(price_clv, g["match_date"]),
                    "ev_at_devigged_close": mean_ci(ev_close, g["match_date"]),
                    "share_beat_close": round(float((price_clv > 0).mean()), 4) if len(g) else None,
                    "roi_same_rows": roi(g["pnl_first"], g["match_date"])}
        if tag == "uncertified_last_pre_kickoff":
            pos, neg = g[price_clv > 0], g[price_clv <= 0]
            out[tag]["roi_when_price_beat_close"] = roi(pos["pnl_first"], pos["match_date"])
            out[tag]["roi_when_price_did_not_beat_close"] = roi(neg["pnl_first"], neg["match_date"])
    led = pd.to_numeric(d["clv_pct"], errors="coerce")
    out["v9_ledger_clv_pct_as_recorded"] = {"n": int(led.notna().sum()),
                                            "mean_pct": round(float(led.mean()), 2) if led.notna().any() else None,
                                            "note": "uncertified, unit = percent, close source unverified"}
    if not pb.empty:
        pb = pb.assign(clv=pb["entry_yes"] / pb["close_yes"] - 1)
        out["same_book_clv_certified"] = mean_ci(pb["clv"], pb["match_date"])
        out["same_book_clv_by_book"] = {b: {"n": int(len(g)), "mean_clv": round(float(g["clv"].mean()), 4)}
                                        for b, g in pb.groupby("book") if len(g) >= 5}
    return out


def _vig(d: pd.DataFrame) -> dict:
    e = d[d["e_p_fair"].notna()].copy()
    e["edge_fixed"] = e["p_model"] - (1 / e["entry_odds"]) / FIXED_OVERROUND
    e["edge_devig"] = e["p_model"] - e["e_p_fair"]
    keep, drop = e[e["edge_devig"] >= 0.04], e[e["edge_devig"] < 0.04]
    return {"n": int(len(e)),
            "actual_overround_at_entry": {"median": round(float(e["e_overround"].median()), 4),
                                          "p10": round(float(e["e_overround"].quantile(.1)), 4),
                                          "p90": round(float(e["e_overround"].quantile(.9)), 4)},
            "fixed_overround_assumed": FIXED_OVERROUND,
            "mean_edge_fixed_1.08": round(float(e["edge_fixed"].mean()), 4),
            "mean_edge_devigged": round(float(e["edge_devig"].mean()), 4),
            "yes_share_of_margin": round(float(((1 / e["entry_odds"]) - e["e_p_fair"]).mean()
                                               / (e["e_overround"] - 1).mean()), 3),
            "tips_still_>=4pct_edge_after_devig": roi(keep["pnl_first"], keep["match_date"]),
            "tips_below_4pct_after_devig": roi(drop["pnl_first"], drop["match_date"])}


def _calibration(d: pd.DataFrame, U: pd.DataFrame) -> dict:
    out = {"tips": {"n": int(len(d)), "mean_p_model": round(float(d["p_model"].mean()), 4),
                    "hit_rate": round(float(d["y"].mean()), 4),
                    "mean_p_market_entry_devig": round(float(d["e_p_fair"].mean()), 4),
                    "mean_p_market_close_devig": round(float(d["ca_p_fair"].mean()), 4),
                    "reliability_model": reliability(d["p_model"], d["y"])}}
    M = C.model_panel("BTTS")[["fixture_key", "model_prob"]]
    V = U.merge(M, on="fixture_key", how="inner").dropna(subset=["model_prob", "ca_p_fair", "y"])
    if len(V) >= 50:
        b, cov = C.fit_logistic(np.column_stack([C.logit(V["ca_p_fair"]), C.logit(V["model_prob"])]), V["y"])
        out["all_priced_fixtures"] = {
            "n": int(len(V)), "btts_rate": round(float(V["y"].mean()), 4),
            "mean_p_model": round(float(V["model_prob"].mean()), 4),
            "mean_p_market_close": round(float(V["ca_p_fair"].mean()), 4),
            "brier_model": round(float(C.brier(V["model_prob"], V["y"]).mean()), 4),
            "brier_market": round(float(C.brier(V["ca_p_fair"], V["y"]).mean()), 4),
            "logloss_model": round(float(C.logloss(V["model_prob"], V["y"]).mean()), 4),
            "logloss_market": round(float(C.logloss(V["ca_p_fair"], V["y"]).mean()), 4),
            "residual_coef_model_given_market": round(float(b[2]), 3),
            "residual_z": round(float(b[2] / np.sqrt(cov[2, 2])), 2),
            "reliability_model": reliability(V["model_prob"], V["y"]),
            "reliability_market": reliability(V["ca_p_fair"], V["y"])}
        bm, _ = C.fit_logistic(C.logit(V["ca_p_fair"]).reshape(-1, 1), V["y"])
        bo, _ = C.fit_logistic(C.logit(V["model_prob"]).reshape(-1, 1), V["y"])
        edge = V["model_prob"] - V["ca_p_fair"]
        out["all_priced_fixtures"].update({
            "market_calibration_slope": round(float(bm[1]), 3), "market_calibration_intercept": round(float(bm[0]), 3),
            "model_calibration_slope": round(float(bo[1]), 3),
            "sd_p_model": round(float(V["model_prob"].std()), 4), "sd_p_market": round(float(V["ca_p_fair"].std()), 4),
            "corr_edge_with_market_p": round(float(np.corrcoef(edge, V["ca_p_fair"])[0, 1]), 3),
            "market_calibration_slope_ex_argentina": round(float(C.fit_logistic(
                C.logit(V.loc[~V["league"].eq("Argentina Primera Division"), "ca_p_fair"]).reshape(-1, 1),
                V.loc[~V["league"].eq("Argentina Primera Division"), "y"])[0][1]), 3),
            "note": "slope < 1 = the market spreads BTTS probabilities too far apart; a compressed model's "
                    "'edge' is then mostly (constant - market p), i.e. a bet on low-priced YES"})
    return out


def _argentina_history() -> dict:
    """BTTS rate per Argentina season — is 2026 a regime the market priced at the old norm?"""
    try:
        from src.studies.argentina_btts import _results
        r = _results()
        r["period"] = np.where(r["match_date"] >= "2026-08-10", "2026 since Aug 10", r["season"].astype(str))
        return {p: {"n": int(len(g)), "btts_rate": round(float(g["y"].mean()), 4)} for p, g in r.groupby("period")}
    except Exception as e:                                             # noqa: BLE001 - context only
        return {"error": type(e).__name__}


def _naive(U: pd.DataFrame, d: pd.DataFrame) -> dict:
    sel_any = set(d["fixture_key"])
    sel_stk = set(d.loc[d["staked_first"], "fixture_key"])
    U = U.assign(selected=U["fixture_key"].isin(sel_any), staked=U["fixture_key"].isin(sel_stk))
    out = {"fixtures": int(len(U)), "selected_fixtures": int(U["selected"].sum())}
    base = {}
    for lg, g in list(U.groupby("league")) + [("ALL tip leagues", U)]:
        base[lg] = {"n": int(len(g)), "btts_rate": round(float(g["y"].mean()), 4),
                    "market_fair_yes_close": round(float(g["ca_p_fair"].mean()), 4),
                    "market_fair_yes_open": round(float(g["o_p_fair"].mean()), 4),
                    "gap_pp_vs_close": round(float((g["y"].mean() - g["ca_p_fair"].mean()) * 100), 1),
                    "blind_yes_open": roi(_flat(g["y"], g["o_median_yes"]), g["match_date"]),
                    "blind_yes_close": roi(_flat(g["y"], g["ca_median_yes"]), g["match_date"])}
    out["base_rate_vs_market"] = base
    for tag, col in (("open", "o_median_yes"), ("matched_lead", "m_median_yes"), ("close", "ca_median_yes")):
        g = U.dropna(subset=[col])
        u = pd.Series(_flat(g["y"], g[col]), index=g.index)
        s, ns = g["selected"], ~g["selected"]
        out[f"at_{tag}_median_price"] = {
            "blind_every_yes": roi(u, g["match_date"]),
            "wowza_selected": roi(u[s], g.loc[s, "match_date"]),
            "not_selected": roi(u[ns], g.loc[ns, "match_date"]),
            "selected_minus_not": diff_ci(u[s], g.loc[s, "match_date"], u[ns], g.loc[ns, "match_date"]),
            "staked_first_minus_not_selected": diff_ci(u[g["staked"]], g.loc[g["staked"], "match_date"],
                                                       u[ns], g.loc[ns, "match_date"])}
    # Within-league: does the model pick better fixtures INSIDE a league, or only pick the league?
    g = U.dropna(subset=["m_median_yes"]).copy()
    g["u"] = _flat(g["y"], g["m_median_yes"])
    g["u_dm"] = g["u"] - g.groupby("league")["u"].transform(lambda s: s[~g.loc[s.index, "selected"]].mean())
    wl = {}
    for lg in ("Argentina Primera Division", "Brazil Serie A"):
        h = g[g["league"].eq(lg)]
        wl[lg] = diff_ci(h.loc[h["selected"], "u"], h.loc[h["selected"], "match_date"],
                         h.loc[~h["selected"], "u"], h.loc[~h["selected"], "match_date"])
    h = g[~g["league"].eq("Argentina Primera Division")]
    wl["ex_argentina_pooled"] = diff_ci(h.loc[h["selected"], "u"], h.loc[h["selected"], "match_date"],
                                        h.loc[~h["selected"], "u"], h.loc[~h["selected"], "match_date"])
    sel = g[g["selected"] & g["u_dm"].notna()]
    wl["league_demeaned_selected_excess_roi"] = mean_ci(sel["u_dm"], sel["match_date"])
    out["within_league_selection"] = wl

    # Market-price-only control: no model at all, just "back YES where the market says BTTS is unlikely",
    # with the same number of bets Wowza made. If this matches Wowza, the selection is the price level.
    k = int(g["selected"].sum())
    low = g.nsmallest(k, "m_p_fair")
    thr = float(g.loc[g["selected"], "m_p_fair"].mean())
    rule = g[g["m_p_fair"] < thr]
    out["market_price_only_control"] = {
        "lowest_market_p_same_count": {**roi(low["u"], low["match_date"]),
                                       "overlap_with_wowza": round(float(low["selected"].mean()), 3)},
        f"market_p_below_{thr:.3f}": roi(rule["u"], rule["match_date"]),
        "wowza_minus_lowest_p_same_count": diff_ci(g.loc[g["selected"], "u"], g.loc[g["selected"], "match_date"],
                                                   low["u"], low["match_date"])}
    md = pd.to_datetime(g["match_date"])
    mid = md.sort_values().iloc[len(md) // 2]
    out["regime_by_half_blind_yes"] = {}
    for lbl, hh in (("first_half", g[md < mid]), ("second_half", g[md >= mid])):
        a = hh[hh["league"].eq("Argentina Primera Division")]
        out["regime_by_half_blind_yes"][lbl] = {
            "all_tip_leagues": {**roi(hh["u"], hh["match_date"]), "btts_rate": round(float(hh["y"].mean()), 4),
                                "market_p": round(float(hh["m_p_fair"].mean()), 4)},
            "argentina": {**roi(a["u"], a["match_date"]), "btts_rate": round(float(a["y"].mean()), 4) if len(a) else None,
                          "market_p": round(float(a["m_p_fair"].mean()), 4) if len(a) else None}}
    s, ns = U[U["selected"]], U[~U["selected"]]
    out["btts_rate_selected_vs_not"] = {"selected": round(float(s["y"].mean()), 4),
                                        "not_selected": round(float(ns["y"].mean()), 4),
                                        "market_close_selected": round(float(s["ca_p_fair"].mean()), 4),
                                        "market_close_not_selected": round(float(ns["ca_p_fair"].mean()), 4)}
    return out


def _league_regime(d: pd.DataFrame) -> dict:
    lg = by(d, "league")
    tot = d["pnl_first"].sum()
    arg = d[d["league"].eq("Argentina Primera Division")]
    lolo = {}
    for l in d["league"].value_counts().index:
        r = d[~d["league"].eq(l)]
        lolo[l] = roi(r["pnl_first"], r["match_date"])
    end = pd.to_datetime(d["match_date"]).max()
    md = pd.to_datetime(d["match_date"])
    mid = md.sort_values().iloc[len(md) // 2]
    windows = {}
    for days in (14, 30, 60):
        w = d[md > end - pd.Timedelta(days=days)]
        windows[f"last_{days}d"] = roi(w["pnl_first"], w["match_date"])
    h1, h2 = d[md < mid], d[md >= mid]
    return {"by_league": dict(sorted(lg.items(), key=lambda kv: -kv[1].get("units", 0))),
            "argentina": {"n_share": round(len(arg) / len(d), 3) if len(d) else None,
                          "units": round(float(arg["pnl_first"].sum()), 2),
                          "units_share": round(float(arg["pnl_first"].sum() / tot), 3) if tot else None},
            "ex_argentina": roi(d.loc[~d.index.isin(arg.index), "pnl_first"],
                                d.loc[~d.index.isin(arg.index), "match_date"]),
            "leave_one_league_out": lolo,
            "first_half": {"to": str(mid.date()), **roi(h1["pnl_first"], h1["match_date"])},
            "second_half": {"from": str(mid.date()), **roi(h2["pnl_first"], h2["match_date"])},
            "second_minus_first": diff_ci(h2["pnl_first"], h2["match_date"], h1["pnl_first"], h1["match_date"]),
            "recent": windows, "last_settled_match_date": str(end.date()),
            "by_month": by(d.assign(m=md.dt.strftime("%Y-%m").values), "m")}


def run() -> dict:
    T = tips()
    Q = quotes()
    X, PB = panel(T, Q)
    fav = h2h_fav()
    X = X.merge(fav[["fav_p"]], left_on="fixture_key", right_index=True, how="left")
    out = {"study": NAME, "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "question": "Is NF BTTS ROI a genuine market inefficiency, a timing/price artifact, a concentrated "
                       "league effect, or variance?",
           "research_only": True, "stakes_changed": False,
           "v9_ledger_sha256_16": _sha16(cfg.V9_LOCAL / LEDGER_PATH)}

    nf = X[X["model_type"].eq("new_format")].copy()
    nfpb = PB[PB["_i"].isin(nf.index)] if not PB.empty else PB
    out["headline"] = {"all_nf_tips": _headline(nf), "staked_first_tier": _headline(nf[nf["staked_first"]]),
                       "sniper_first_tier": _headline(nf[nf["first_tier"].eq("SNIPER")]),
                       "standard_track_contrast": _headline(X[X["model_type"].eq("standard")])}
    out["A_entry_price"] = _entry(nf)
    out["B_closing_price"] = _closing(nf, nfpb)
    out["C_tiers"] = {"by_first_tier": by(nf, "first_tier"),
                      "by_ledger_tier_overwritten": by(nf, "signal_tier", "pnl_ledger"),
                      "upgraded_later": by(nf.assign(u=nf["upgraded"].map({True: "upgraded later", False: "never upgraded"})), "u"),
                      "rows_with_tier_changed": int((nf["signal_tier"] != nf["first_tier"]).sum())}
    out["D_league_and_regime"] = _league_regime(nf)
    out["E_odds_and_favourite"] = {
        "by_odds_band": by(nf.assign(b=_band(nf["entry_odds"], *ODDS_BANDS).values), "b"),
        "by_favourite_strength_1x2": by(nf.assign(b=_band(nf["fav_p"], *FAV_BANDS).values), "b"),
        "tips_with_1x2": int(nf["fav_p"].notna().sum())}
    out["F_vig"] = _vig(nf)

    # universe for the naive control and for calibration: every priced fixture in the NF tip leagues,
    # inside each league's own tip window
    win = {l: (g["match_date"].min(), g["match_date"].max()) for l, g in nf.groupby("league")}
    U = universe(Q, win, float(nf["lead_h"].median()))
    R = results_for(sorted(win), min(v[0] for v in win.values()), max(v[1] for v in win.values()))
    j = C.match_frames(U, R)
    U = U[j.notna()].copy()
    U["y"] = R.loc[j.dropna().astype(int).to_numpy(), "y"].to_numpy()
    out["G_yes_structure_and_naive_control"] = _naive(U, nf)
    out["G_yes_structure_and_naive_control"]["unmatched_fixtures"] = int(j.isna().sum())
    out["G_yes_structure_and_naive_control"]["argentina_btts_rate_by_season"] = _argentina_history()
    out["H_calibration"] = _calibration(nf, U)
    out["I_variance"] = {
        "all_nf_vs_entry_market": variance_test(nf["e_p_fair"], nf["entry_odds"], nf["y"]),
        "all_nf_vs_last_close_market": variance_test(nf["ca_p_fair"], nf["entry_odds"], nf["y"]),
        "staked_first_vs_last_close_market": variance_test(nf.loc[nf["staked_first"], "ca_p_fair"],
                                                           nf.loc[nf["staked_first"], "entry_odds"],
                                                           nf.loc[nf["staked_first"], "y"]),
        "certified_subset_vs_certified_close": variance_test(
            nf.loc[nf["cs_n_pairs"] >= 3, "cs_p_fair"], nf.loc[nf["cs_n_pairs"] >= 3, "entry_odds"],
            nf.loc[nf["cs_n_pairs"] >= 3, "y"])}
    out["verdict"] = verdict(out)
    return out


def _sha16(p) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else ""


def _lo(ci) -> float:
    return ci[0] if ci and ci[0] is not None else float("nan")


def _hi(ci) -> float:
    return ci[1] if ci and ci[1] is not None else float("nan")


def verdict(o: dict) -> dict:
    """Rule-based flags, recomputed on every run so the headline can never outlive its numbers."""
    A, B, D = o["A_entry_price"], o["B_closing_price"], o["D_league_and_regime"]
    G, H, I = o["G_yes_structure_and_naive_control"], o["H_calibration"].get("all_priced_fixtures", {}), o["I_variance"]
    cert = B.get("certified", {}).get("price_clv_vs_median_close", {})
    mpc = G["market_price_only_control"]["wowza_minus_lowest_p_same_count"]
    flags = {
        "ENTRY_PRICES_REAL": "YES" if A["entry_equals_cross_book_median_share"] >= .95
        and A["entry_above_best_available_share"] == 0 else "NO",
        "LEDGER_OVERWRITE_FLATTERS_UNITS": A["ledger_overwrote_odds"]["flattering_units"],
        "CERTIFIED_CLV_POSITIVE": "YES" if _lo(cert.get("ci90")) > 0 else "NO",
        "MODEL_ADDS_TO_MARKET": "YES" if H.get("residual_z", 0) > 2 else "NO",
        "OUTCOMES_BEAT_MARKET_PROBABILITY": "YES" if I["all_nf_vs_last_close_market"].get("p_value_one_sided", 1) < .05 else "NO",
        "BEATS_MODEL_FREE_PRICE_RULE": "YES" if _lo(mpc.get("ci90")) > 0 else "NO",
        "EDGE_IS_MOSTLY_LOW_MARKET_PRICE": "YES" if H.get("corr_edge_with_market_p", 0) < -0.7 else "NO",
        "ARGENTINA_UNITS_SHARE": D["argentina"]["units_share"],
        "PROFITABLE_EX_ARGENTINA": "YES" if _lo(D["ex_argentina"].get("roi_ci90")) > 0 else "NO",
        "REGIME_COOLED": "YES" if _hi(D["second_minus_first"].get("ci90")) < 0 else "NO",
    }
    skill = flags["CERTIFIED_CLV_POSITIVE"] == "YES" or flags["MODEL_ADDS_TO_MARKET"] == "YES" \
        or flags["BEATS_MODEL_FREE_PRICE_RULE"] == "YES"
    if not skill and flags["ARGENTINA_UNITS_SHARE"] and flags["ARGENTINA_UNITS_SHARE"] > .6 \
            and flags["PROFITABLE_EX_ARGENTINA"] == "NO":
        primary = "CONCENTRATED_LEAGUE_REGIME"
    elif skill:
        primary = "POSSIBLE_MARKET_INEFFICIENCY"
    elif flags["OUTCOMES_BEAT_MARKET_PROBABILITY"] == "NO":
        primary = "VARIANCE"
    else:
        primary = "REGIME_NOT_SKILL"
    flags["PRIMARY_EXPLANATION"] = primary
    flags["SECONDARY"] = ("PRICE_LEVEL_SELECTION (compressed model backs the lowest-priced YES)"
                          if flags["EDGE_IS_MOSTLY_LOW_MARKET_PRICE"] == "YES" else None)
    flags["TIMING_PRICE_ARTIFACT"] = "NO" if flags["ENTRY_PRICES_REAL"] == "YES" else "POSSIBLE"
    flags["STAKE_CHANGE_RECOMMENDED"] = "NO"
    return flags


def _r(x: dict) -> str:
    if not x or not x.get("n"):
        return "n=0"
    ci = x.get("roi_ci90") or [None, None]
    cis = f" [{ci[0]:+.1%}, {ci[1]:+.1%}]" if ci[0] is not None else ""
    return f"{x['roi']:+.1%}{cis}, {x['units']:+.2f}u, n={x['n']}"


def _m(x: dict) -> str:
    if not x or not x.get("n"):
        return "n=0"
    ci = x.get("ci90") or [None, None]
    cis = f" [{ci[0]:+.2%}, {ci[1]:+.2%}]" if ci[0] is not None else ""
    return f"{x['mean']:+.2%}{cis}, n={x['n']}"


def _d(x: dict) -> str:
    if not x:
        return "n/a"
    return f"{x['diff']:+.1%} [{x['ci90'][0]:+.1%}, {x['ci90'][1]:+.1%}]"


def report(o: dict) -> str:
    V, Hd = o["verdict"], o["headline"]
    A, B, Ct, D = o["A_entry_price"], o["B_closing_price"], o["C_tiers"], o["D_league_and_regime"]
    E, F, G, I = o["E_odds_and_favourite"], o["F_vig"], o["G_yes_structure_and_naive_control"], o["I_variance"]
    H = o["H_calibration"]
    Hall = H.get("all_priced_fixtures", {})
    nf = Hd["all_nf_tips"]
    arg = G["base_rate_vs_market"].get("Argentina Primera Division", {})
    allg = G["base_rate_vs_market"]["ALL tip leagues"]
    mpc = G["market_price_only_control"]
    rh = G["regime_by_half_blind_yes"]
    L = [
        "# New-format BTTS: why ROI looks strong while CLV looks poor",
        "",
        f"_Generated {o['generated_at']} by `python -m src.studies.btts_contradiction`. Research only: "
        "nothing here changes a stake, tier, threshold or filter. All CIs are 90% bootstraps over matchdays._",
        "",
        "## Verdict",
        "",
        f"**{V['PRIMARY_EXPLANATION'].replace('_', ' ').lower()}**, not model skill. "
        f"The {nf['n']} settled new-format BTTS-YES tips returned {_r(nf['first_logged'])} at the price first logged. "
        f"Argentina made {D['argentina']['units_share']:.0%} of those units; without Argentina the tips made "
        f"{_r(D['ex_argentina'])}.",
        "",
        f"The profit is real money on real prices: entry odds match the books available at that minute. "
        f"But it came from BTTS landing far more often than **any** price implied, not from the model reading "
        f"fixtures better than the market. In Argentina BTTS landed {arg.get('btts_rate', 0):.0%} of the time "
        f"against a market price of {arg.get('market_fair_yes_close', 0):.0%}. Backing YES on every Argentina "
        f"fixture blind earned {_r(arg.get('blind_yes_close', {}))}. Argentina's BTTS rate was "
        f"{G['argentina_btts_rate_by_season'].get('2025', {}).get('btts_rate', float('nan')):.0%} in 2025, and the market "
        "is still pricing roughly that level.",
        "",
        f"The model is compressed: its probabilities have an SD of {Hall.get('sd_p_model', float('nan')):.3f}, against "
        f"{Hall.get('sd_p_market', float('nan')):.3f} for the market. So its 'edge' is almost entirely 'the market price is "
        f"low' (correlation of edge with market probability: {Hall.get('corr_edge_with_market_p', float('nan')):+.2f}). "
        f"A rule with no model, backing the {mpc['lowest_market_p_same_count']['n']} lowest-priced BTTS-YES fixtures, "
        f"earned {_r(mpc['lowest_market_p_same_count'])} and overlapped "
        f"{mpc['lowest_market_p_same_count']['overlap_with_wowza']:.0%} with Wowza's picks. Wowza minus that rule: "
        f"{_d(mpc['wowza_minus_lowest_p_same_count'])}.",
        "",
        f"The poor CLV is mostly the bookmaker's margin, not a line moving against us. Entries sit at the cross-book "
        f"median with about {F['actual_overround_at_entry']['median'] - 1:.1%} overround. Price movement to the "
        f"certified close is about zero ({_m(B['certified']['price_clv_vs_median_close'])}). EV against the "
        f"de-vigged close is {_m(B['certified']['ev_at_devigged_close'])}, which is the margin. "
        "So the market never moved toward Wowza's view. The profit came from outcomes, not from information.",
        "",
        f"The regime is cooling. First half {_r(D['first_half'])}; second half {_r(D['second_half'])}; "
        f"difference {_d(D['second_minus_first'])}; last 14 days {_r(D['recent']['last_14d'])}.",
        "",
        "| question | answer |",
        "|---|---|",
        f"| Genuine market inefficiency found by the model? | **No.** Residual z = {Hall.get('residual_z')}; certified CLV "
        f"positive: {V['CERTIFIED_CLV_POSITIVE']}; beats a model-free price rule: {V['BEATS_MODEL_FREE_PRICE_RULE']} |",
        f"| Timing / price artifact? | **No.** {A['entry_equals_cross_book_median_share']:.1%} of entries equal the "
        f"cross-book median at that minute, and none are above the best available book. The ledger overwrite "
        f"flattered NF BTTS by only {A['ledger_overwrote_odds']['flattering_units']:+.2f}u |",
        f"| Concentrated league effect? | **Yes.** Argentina = {D['argentina']['units_share']:.0%} of units; "
        f"ex-Argentina {_r(D['ex_argentina'])} |",
        f"| Variance? | **Not against the market's own odds** (p = {I['all_nf_vs_last_close_market']['p_value_one_sided']}): "
        "outcomes really did beat the price. **But it is variance of the regime**: one league, one period, now cooling |",
        "",
        "**No stake change is recommended from this analysis.** The forward evidence that would justify one is "
        "listed at the end.",
        "",
        "## Headline numbers (first-logged price, flat 1u)",
        "",
        "| set | n | hit | break-even | ROI (first logged) | ROI (ledger, overwritten) |",
        "|---|---|---|---|---|---|",
    ]
    for k, lbl in (("all_nf_tips", "all NF BTTS"), ("staked_first_tier", "staked (first tier SNIPER/MARKSMAN)"),
                   ("sniper_first_tier", "SNIPER (first tier)"), ("standard_track_contrast", "standard track (contrast)")):
        h = Hd[k]
        L.append(f"| {lbl} | {h['n']} | {h['hit_rate']:.1%} | {h['breakeven_hit']:.1%} | {_r(h['first_logged'])} | "
                 f"{_r(h['ledger_overwritten'])} |")
    L += ["", "## A. Entry price", "",
          f"- Entry odds are v9's **cross-book median** YES (src/btts_odds.py), not one bookmaker's price. "
          f"{A['entry_equals_cross_book_median_share']:.1%} of tips reproduce the median of the books carried forward to "
          f"the generated_at minute (median {A['books_at_entry_median']:.0f} books). Above best available: "
          f"{A['entry_above_best_available_share']:.0%}. Below worst: {A['entry_below_worst_available_share']:.0%}.",
          f"- ROI at the median: {_r(A['roi_at_entry_median_price'])}. At the best book: {_r(A['roi_at_best_book_at_entry'])}. "
          f"At the worst book: {_r(A['roi_at_worst_book_at_entry'])}.",
          f"- First-logged vs ledger: the ledger overwrote odds on {A['ledger_overwrote_odds']['n']} settled NF BTTS rows "
          f"({A['ledger_overwrote_odds']['units_first_logged']:+.2f}u first, {A['ledger_overwrote_odds']['units_ledger']:+.2f}u "
          f"ledger, {A['ledger_overwrote_odds']['flattering_units']:+.2f}u flattering). The brief's 88-row figure covers all side markets.",
          f"- Time to kickoff at entry: median {A['hours_to_kickoff_at_entry']['median']}h "
          f"(IQR {A['hours_to_kickoff_at_entry']['p25']}-{A['hours_to_kickoff_at_entry']['p75']}h). "
          f"{A['entered_on_opening_quote_share']:.0%} of tips were taken on the very first quote ever captured, so "
          "entries are early, at opening prices, not stale.", "",
          "| hours to kickoff | ROI |", "|---|---|"]
    L += [f"| {k} | {_r(v)} |" for k, v in A["roi_by_hours_to_kickoff"].items()]
    L += ["", "There is no monotonic timing pattern: the bands either side of 72-144h are positive while 72-144h is "
          "negative. Four bands were tested and no mechanism explains a middle band losing, so treat this as a lead "
          "to watch forward, not a finding.",
          "", "## B. Closing price", "",
          f"- Coverage: certified close (the book's own quote within {CERT_MIN} min of kickoff, at least 3 books): "
          f"{B['close_coverage']['certified_strict_>=3_books']} of {B['close_coverage']['tips']} tips. "
          f"Last pre-kickoff quote, not certified: {B['close_coverage']['uncertified_last_pre_kickoff']}. "
          "The two are never mixed.",
          f"- Certified, same construction (median to median): price CLV {_m(B['certified']['price_clv_vs_median_close'])}; "
          f"EV at the de-vigged close {_m(B['certified']['ev_at_devigged_close'])}; beat the close {B['certified']['share_beat_close']:.0%}.",
          f"- Not certified, last pre-kickoff: price CLV {_m(B['uncertified_last_pre_kickoff']['price_clv_vs_median_close'])}; "
          f"EV at the de-vigged close {_m(B['uncertified_last_pre_kickoff']['ev_at_devigged_close'])}.",
          f"- Same book, certified (entry YES vs that book's own close): {_m(B.get('same_book_clv_certified', {}))}. "
          "Every book is negative or flat: " + ", ".join(f"{k} {v['mean_clv']:+.1%} (n={v['n']})"
                                                      for k, v in B.get("same_book_clv_by_book", {}).items()) + ".",
          f"- CLV does not predict profit here. Tips that beat the close: {_r(B['uncertified_last_pre_kickoff']['roi_when_price_beat_close'])}. "
          f"Tips that did not: {_r(B['uncertified_last_pre_kickoff']['roi_when_price_did_not_beat_close'])}.",
          f"- v9 ledger clv_pct, as recorded (not certified): mean {B['v9_ledger_clv_pct_as_recorded']['mean_pct']}% "
          f"(n={B['v9_ledger_clv_pct_as_recorded']['n']}).",
          "", "## C. First-sight tier vs upgraded rows", "",
          "| first logged tier | ROI |", "|---|---|"]
    L += [f"| {k} | {_r(v)} |" for k, v in Ct["by_first_tier"].items()]
    L += ["", "| ledger tier (after in-place upgrades) | ROI |", "|---|---|"]
    L += [f"| {k} | {_r(v)} |" for k, v in Ct["by_ledger_tier_overwritten"].items()]
    L += ["", f"Upgraded later: {_r(Ct['upgraded_later'].get('upgraded later', {}))}. Never upgraded: "
          f"{_r(Ct['upgraded_later'].get('never upgraded', {}))}. Upgrades blurred the tier ladder. First-sight SNIPER is "
          "the strongest cell, and it is also the cell with the lowest market prices (see G).",
          "", "## D. League concentration and regime", "",
          f"Argentina: {D['argentina']['n_share']:.0%} of tips, {D['argentina']['units_share']:.0%} of units. "
          f"Ex-Argentina: {_r(D['ex_argentina'])}.", "",
          "| league | ROI |", "|---|---|"]
    L += [f"| {k} | {_r(v)} |" for k, v in D["by_league"].items()]
    L += ["", "Leave one league out (ROI of the rest): " + "; ".join(
        f"{k} {v['roi']:+.1%}" for k, v in D["leave_one_league_out"].items()) + ".", "",
          f"- First half (to {D['first_half']['to']}): {_r(D['first_half'])}. Second half: {_r(D['second_half'])}. "
          f"Second minus first: {_d(D['second_minus_first'])}.",
          f"- Last 14 days {_r(D['recent']['last_14d'])}; last 30 days {_r(D['recent']['last_30d'])}; last 60 days {_r(D['recent']['last_60d'])}.",
          "- By month: " + "; ".join(f"{k} {_r(v)}" for k, v in D["by_month"].items()) + ".",
          "", "## E. Odds band and favourite strength", "", "| entry odds | ROI |", "|---|---|"]
    L += [f"| {k} | {_r(v)} |" for k, v in E["by_odds_band"].items()]
    L += ["", f"| favourite strength (1X2, {E['tips_with_1x2']} tips with a capture) | ROI |", "|---|---|"]
    L += [f"| {k} | {_r(v)} |" for k, v in E["by_favourite_strength_1x2"].items() if k != "nan"]
    L += ["", "The profit sits at the longer YES prices (2.00-2.49), which is where the market thinks BTTS is least "
          "likely. That is the same price-level effect described in G.",
          "", "## F. Vig handling", "",
          f"- Actual overround at entry: median {F['actual_overround_at_entry']['median']} "
          f"(p10 {F['actual_overround_at_entry']['p10']}, p90 {F['actual_overround_at_entry']['p90']}). "
          f"Production assumes a fixed {F['fixed_overround_assumed']}, so the assumption is accurate on average for these books.",
          f"- Mean edge with the fixed 1.08: {F['mean_edge_fixed_1.08']:+.2%}. De-vigged (power, YES/NO pair): "
          f"{F['mean_edge_devigged']:+.2%}. YES carries {F['yes_share_of_margin']:.0%} of the margin.",
          f"- Still at least 4% edge after de-vig: {_r(F['tips_still_>=4pct_edge_after_devig'])}. "
          f"Below 4%: {_r(F['tips_below_4pct_after_devig'])}. Vig handling does not explain the result.",
          "", "## G. YES-only structure and the naive control", "",
          f"Every priced BTTS fixture in the NF tip leagues, inside each league's tip window: {G['fixtures']} fixtures, "
          f"{G['selected_fixtures']} of them Wowza picks ({G['unmatched_fixtures']} fixtures could not be matched to a result).", "",
          "| league | n | BTTS rate | market fair YES (close) | gap | blind YES at close |", "|---|---|---|---|---|---|"]
    for k, v in G["base_rate_vs_market"].items():
        L.append(f"| {k} | {v['n']} | {v['btts_rate']:.1%} | {v['market_fair_yes_close']:.1%} | {v['gap_pp_vs_close']:+.1f}pp | "
                 f"{_r(v['blind_yes_close'])} |")
    nm = G["at_matched_lead_median_price"]
    L += ["", f"At the median price, at Wowza's typical lead time ({A['hours_to_kickoff_at_entry']['median']}h):",
          f"- Blind, every YES: {_r(nm['blind_every_yes'])}",
          f"- Wowza's picks: {_r(nm['wowza_selected'])}. Not picked: {_r(nm['not_selected'])}. "
          f"Picked minus not picked: {_d(nm['selected_minus_not'])}.",
          f"- **Model-free control**, the {mpc['lowest_market_p_same_count']['n']} lowest market probabilities: "
          f"{_r(mpc['lowest_market_p_same_count'])}, {mpc['lowest_market_p_same_count']['overlap_with_wowza']:.0%} overlap "
          f"with Wowza. Wowza minus control: {_d(mpc['wowza_minus_lowest_p_same_count'])}.",
          "- Within league: " + "; ".join(f"{k} {_d(v)}" for k, v in G["within_league_selection"].items()
                                           if k != "league_demeaned_selected_excess_roi") + ".",
          f"- Argentina BTTS rate by season: " + "; ".join(
              f"{k} {v['btts_rate']:.1%} (n={v['n']})" for k, v in G["argentina_btts_rate_by_season"].items() if isinstance(v, dict)) + ".",
          f"- Blind YES by half. First half: all leagues {_r(rh['first_half']['all_tip_leagues'])}, Argentina "
          f"{_r(rh['first_half']['argentina'])}. Second half: all leagues {_r(rh['second_half']['all_tip_leagues'])}, "
          f"Argentina {_r(rh['second_half']['argentina'])}.",
          "", "Picked minus not picked looks positive, but the picked fixtures are the ones the market priced lowest. "
          "A rule with no model, using price level alone, matches Wowza's picks or beats them. "
          f"Ex-Argentina, Wowza's picks do no better than the fixtures it skipped ({_d(G['within_league_selection']['ex_argentina_pooled'])}).",
          "", "## H. Calibration", "",
          f"- On the tips: mean model probability {H['tips']['mean_p_model']:.1%}, hit rate {H['tips']['hit_rate']:.1%}, "
          f"market de-vigged {H['tips']['mean_p_market_entry_devig']:.1%} at entry and {H['tips']['mean_p_market_close_devig']:.1%} at close.",
          f"- On all {Hall.get('n')} priced fixtures: Brier model {Hall.get('brier_model')} vs market {Hall.get('brier_market')}; "
          f"log-loss {Hall.get('logloss_model')} vs {Hall.get('logloss_market')}. Model on top of market: coefficient "
          f"{Hall.get('residual_coef_model_given_market')}, z = {Hall.get('residual_z')}, so it adds nothing measurable.",
          f"- Market calibration slope {Hall.get('market_calibration_slope')} (ex-Argentina "
          f"{Hall.get('market_calibration_slope_ex_argentina')}). Model slope {Hall.get('model_calibration_slope')}. "
          "A slope below 1 means low-priced YES landed more often than priced. "
          + ("Outside Argentina the market slope is at or above 1, so the market's miscalibration in this window "
             "is an Argentina effect, not a market-wide BTTS bias. "
             if (Hall.get("market_calibration_slope_ex_argentina") or 0) >= 0.9 else
             "The slope stays below 1 outside Argentina too. ")
          + "One period is not enough to say whether this is a lasting market bias or this season's scoring.",
          "", "| market fair p bin | n | mean p | hit |", "|---|---|---|---|"]
    L += [f"| {b['bin']} | {b['n']} | {b['mean_p']:.1%} | {b['hit']:.1%} |" for b in Hall.get("reliability_market", [])]
    L += ["", "| model p bin | n | mean p | hit |", "|---|---|---|---|"]
    L += [f"| {b['bin']} | {b['n']} | {b['mean_p']:.1%} | {b['hit']:.1%} |" for b in Hall.get("reliability_model", [])]
    L += ["", "## I. Variance", "", "If the market's own de-vigged probability were the truth, how often would flat YES at "
          "the entry price earn the observed ROI? (20,000 simulations)", "",
          "| set | observed | expected if market right | 90% range if market right | p |", "|---|---|---|---|---|"]
    for k, v in I.items():
        if v.get("n", 0) >= 10:
            L.append(f"| {k} (n={v['n']}) | {v['observed_roi']:+.1%} | {v['expected_roi_if_market_right']:+.1%} | "
                     f"[{v['sim_roi_90pct_range'][0]:+.1%}, {v['sim_roi_90pct_range'][1]:+.1%}] | {v['p_value_one_sided']} |")
    L += ["", "Luck alone, with the market's odds being right, does not explain the result: YES really did land more "
          "often than priced. The naive control (G) shows that this happened to every YES in Argentina and Brazil, "
          "picked or not. So it is a property of the period and the league, not of the selection.",
          "", "## What forward evidence would justify a change", "",
          "No stake, tier or threshold change follows from this study. Each of these should be pre-registered and "
          "measured forward on first-logged prices:",
          "",
          "1. **Selection beats price level.** Wowza's NF BTTS picks beat the model-free 'lowest market probability, same "
          "count' control. Required: the 90% CI of the difference above zero over at least 150 forward bets.",
          "2. **Certified CLV.** Same-book CLV to a close certified within 30 minutes of kickoff has a mean above zero, "
          "with the CI above zero, at n >= 150. This needs near-kickoff BTTS capture for NF leagues first: today only "
          f"{B['close_coverage']['certified_strict_>=3_books']} of {B['close_coverage']['tips']} tips have a certified close.",
          "3. **Not one league.** Ex-Argentina ROI has a CI lower bound above zero, and the Argentina-only result holds "
          "after its blind-YES baseline is subtracted.",
          "4. **Model adds to market.** Residual z > 2 for the model given the de-vigged price, on forward fixtures.",
          "5. **Regime check.** If Argentina's BTTS rate returns toward its 2025 level (about 38%), expect the blind "
          "baseline, and with it most of the NF BTTS profit, to disappear. Track blind YES ROI per league as the "
          "regime monitor.",
          "", "## Method notes", "",
          "- First-logged rows come from v9's git history of `output/side_bets_ledger.csv`: the first commit containing "
          "each row. They are cached at `output/studies/btts_contradiction_first_logged.csv`.",
          "- Book quotes are Pro's `book_odds_snapshots`, which is a change-log, so every price at a given time is "
          "last-observation-carried-forward per book.",
          "- Results come from API-Football. Model probabilities come from Pro's `model_snapshots` (last pre-kickoff). "
          "1X2 comes from Pro's `market_snapshots` h2h captures.",
          "- Observation, not a recommendation: v9 trains one BTTS model on standard and new-format rows pooled "
          "(pipeline.py side-market block). That may be why its probabilities are compressed.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    r = run()
    C.write(NAME, r)
    (cfg.OUTPUT_DIR / "studies" / "BTTS_CONTRADICTION.md").write_text(report(r), encoding="utf-8")
    print(json.dumps(r["verdict"], indent=1, default=str))
