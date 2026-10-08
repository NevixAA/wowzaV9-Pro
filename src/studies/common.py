"""Shared plumbing for the October 2026 upgrade studies (src/studies/*).

    results(start, end)        every finished fixture in Wowza's leagues, from API-Football
    model_panel(market)        v9's model probability per fixture, last snapshot before kickoff
    book_panel(market)         per-book quotes -> de-vigged consensus, Pinnacle, n_books
    match_frames(left, right)  join two fixture lists that disagree on date and club names

WHY A FUZZY JOIN AND NOT fixture_key. fixture_key hashes (league, date, club slug), and the two
sides disagree on both: v9 stamps a LOCAL match date while API-Football uses UTC, so an evening
kickoff in Buenos Aires lands on the next UTC day; and club names differ by source ("Dep.
Riestra" / "Deportivo Riestra", "Atl. Tucuman" / "Atletico Tucuman"). Measured 2026-10-08: of
1,318 fixtures with a model probability, only 565 joined results on fixture_key. The matcher here
accepts a date difference of one day and a token-prefix name match, and REFUSES any fixture that
matches more than one candidate — a wrong join is worse than a missing one.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.data.entities import norm_name
from src.market.devig import power_devig

CACHE = cfg.BASE_DIR / "experiments" / "upgrade_studies_2026_10"
RNG = np.random.default_rng(20261008)

_GENERIC = {"fc", "cf", "sc", "afc", "cd", "ac", "ss", "as", "us", "if", "fk", "sk", "bk", "club",
            "cp", "sd", "de", "la", "el", "the", "ca", "cs", "ud", "rc", "fsv", "sv", "vfl", "vfb",
            "tsg", "bsc", "ifk", "calcio", "1"}
_ALIAS = {"utd": "united", "jrs": "juniors", "jr": "juniors", "dep": "deportivo",
          "atl": "atletico", "ind": "independiente", "est": "estudiantes", "gimn": "gimnasia"}


def _toks(name) -> set[str]:
    out = set()
    for t in norm_name(name).split():
        t = _ALIAS.get(t, t)
        if t and t not in _GENERIC and not t.isdigit():
            out.add(t)
    return out


def same_club(a, b) -> bool:
    """Every identity token of the shorter name maps to a token of the longer one (exact, or a
    prefix of 3+ characters). 'Atl Tucuman' == 'Atletico Tucuman'; 'Real Madrid' != 'Real Sociedad'."""
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)

    def hit(t):
        return any(t == o or (len(t) >= 3 and o.startswith(t)) or (len(o) >= 3 and t.startswith(o))
                   for o in big)
    return all(hit(t) for t in small)


def match_frames(left: pd.DataFrame, right: pd.DataFrame, *, l_cols=("league", "match_date", "home_team", "away_team"),
                 r_cols=("league", "match_date", "home_team", "away_team"), day_tol: int = 1) -> pd.Series:
    """For each row of `left`, the index of its unique match in `right`, or NaN."""
    rl, rd, rh, ra = r_cols
    R = right.assign(_d=pd.to_datetime(right[rd].astype(str).str[:10], errors="coerce"))
    by_league = {k: g for k, g in R.groupby(rl)} if rl else {None: R}
    out = []
    ll, ld, lh, la = l_cols
    for _, r in left.iterrows():
        g = by_league.get(r[ll] if ll else None)
        if g is None:
            out.append(np.nan)
            continue
        d = pd.to_datetime(str(r[ld])[:10], errors="coerce")
        c = g[(g["_d"] - d).abs() <= pd.Timedelta(days=day_tol)]
        c = c[[same_club(r[lh], h) and same_club(r[la], a) for h, a in zip(c[rh], c[ra])]]
        out.append(c.index[0] if len(c) == 1 else np.nan)
    return pd.Series(out, index=left.index)


# ── results ───────────────────────────────────────────────────────────────────────────────────
def _af_key() -> str:
    import os
    k = os.getenv("APIFOOTBALL_KEY", "")
    if k:
        return k
    for p in (cfg.BASE_DIR / ".env", cfg.V9_LOCAL / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("APIFOOTBALL_KEY"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("APIFOOTBALL_KEY not available")


def results(start: str, end: str, league_ids: dict[str, int]) -> pd.DataFrame:
    """Finished fixtures, one /fixtures?date call per day, cached per day (a finished day never
    changes, so the cache is permanent)."""
    import requests
    id2name = {v: k for k, v in league_ids.items()}
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in pd.date_range(start, end):
        day = d.strftime("%Y-%m-%d")
        f = CACHE / f"fixtures_{day}.json"
        if f.exists():
            body = json.loads(f.read_text(encoding="utf-8"))
        else:
            body = requests.get("https://v3.football.api-sports.io/fixtures",
                                headers={"x-apisports-key": _af_key()},
                                params={"date": day}, timeout=60).json()
            if body.get("errors"):
                raise RuntimeError(f"API-Football error for {day}: {body['errors']}")
            # keep only our leagues, so the cache stays small
            body = {"response": [x for x in body.get("response", []) if x["league"]["id"] in id2name]}
            f.write_text(json.dumps(body), encoding="utf-8")
            time.sleep(0.2)
        for x in body["response"]:
            st = x["fixture"]["status"]["short"]
            if x["league"]["id"] not in id2name or st not in ("FT", "AET", "PEN"):
                continue
            rows.append({"league": id2name[x["league"]["id"]], "match_date": x["fixture"]["date"][:10],
                         "kickoff_utc": x["fixture"]["date"], "home_team": x["teams"]["home"]["name"],
                         "away_team": x["teams"]["away"]["name"], "hg": x["goals"]["home"],
                         "ag": x["goals"]["away"], "af_fixture_id": x["fixture"]["id"]})
    return pd.DataFrame(rows)


def outcome(market: str, hg, ag):
    hg, ag = np.asarray(hg, float), np.asarray(ag, float)
    t = hg + ag
    return {"OU15": t > 1.5, "OU25": t > 2.5, "OU35": t > 3.5, "BTTS": (hg > 0) & (ag > 0)}[market].astype(float)


# ── model and market panels ───────────────────────────────────────────────────────────────────
def _names() -> pd.DataFrame:
    """fixture_key -> (league, match_date, home_team, away_team), from v9's market snapshots."""
    m = store.read("market_snapshots")
    m = m.dropna(subset=["home_team", "away_team"])
    return m.drop_duplicates("fixture_key")[["fixture_key", "league", "match_date", "home_team", "away_team"]]


def model_panel(market: str) -> pd.DataFrame:
    """Last model probability observed for each fixture. model_prob is P(OVER) / P(YES)."""
    ms = store.read("model_snapshots")
    ms = ms[ms["market"] == market].sort_values("observed_at")
    ms = ms[pd.to_datetime(ms["observed_at"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
            <= ms["match_date"].astype(str)]                    # never a post-match snapshot
    ms = ms.drop_duplicates("fixture_key", keep="last")[["fixture_key", "model_type", "model_prob", "observed_at"]]
    return ms.merge(_names(), on="fixture_key", how="inner")


def book_panel(market: str) -> pd.DataFrame:
    """Per fixture: de-vigged consensus P(OVER/YES) (median over books quoting both sides),
    n_books, dispersion, and Pinnacle's fair probability. Last PRE-kickoff quote per book."""
    bo = store.read("book_odds_snapshots")
    bo = bo[(bo["market"] == market) & ~bo["is_post_kickoff"].astype(bool)]
    bo = bo.sort_values("snapshot_ts").drop_duplicates(["fixture_key", "bookmaker", "side"], keep="last")
    first = {"OU15": "OVER", "OU25": "OVER", "OU35": "OVER", "BTTS": "YES"}[market]
    w = bo.pivot_table(index=["fixture_key", "bookmaker"], columns="side", values="odds", aggfunc="last")
    other = [c for c in w.columns if c != first]
    if first not in w.columns or not other:
        return pd.DataFrame()
    w = w.dropna(subset=[first, other[0]]).reset_index()
    w["p"] = [power_devig(a, b) for a, b in zip(w[first], w[other[0]])]
    w = w.dropna(subset=["p"])
    g = w.groupby("fixture_key")
    out = pd.DataFrame({"p_market": g["p"].median(), "n_books": g["p"].size(), "dispersion": g["p"].std()})
    pin = w[w["bookmaker"].str.lower() == "pinnacle"].set_index("fixture_key")["p"]
    out["p_pinnacle"] = pin
    best_first = w.groupby("fixture_key")[first].max()
    out["best_odds_first"] = best_first
    return out.reset_index()


# ── statistics ────────────────────────────────────────────────────────────────────────────────
def block_ci(x, groups, n_boot: int = 3000, q=(0.05, 0.95)) -> list:
    """CI of mean(x) resampling whole groups (matchdays)."""
    d = pd.DataFrame({"x": np.asarray(x, float), "g": np.asarray(groups)}).dropna()
    s = d.groupby("g")["x"].agg(["sum", "count"])
    if len(s) < 3:
        return [None, None]
    idx = RNG.integers(0, len(s), size=(n_boot, len(s)))
    m = s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1)
    return [round(float(np.quantile(m, q[0])), 4), round(float(np.quantile(m, q[1])), 4)]


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(p, y):
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def fit_logistic(X, y, l2: float = 1e-6):
    """Newton-Raphson logistic regression with a tiny ridge for stability. Returns (beta, cov)."""
    X = np.column_stack([np.ones(len(X)), np.asarray(X, float)])
    b = np.zeros(X.shape[1])
    for _ in range(100):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu)
        H = X.T @ (X * W[:, None]) + l2 * np.eye(len(b))
        step = np.linalg.solve(H, X.T @ (np.asarray(y, float) - mu) - l2 * b)
        b += step
        if np.abs(step).max() < 1e-9:
            break
    return b, np.linalg.inv(H)


def predict_logistic(b, X):
    X = np.column_stack([np.ones(len(X)), np.asarray(X, float)])
    return 1 / (1 + np.exp(-X @ b))


def write(name: str, obj: dict) -> Path:
    out = cfg.OUTPUT_DIR / "studies"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{name}.json"
    p.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    return p
