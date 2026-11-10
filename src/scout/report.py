"""League scout report: which leagues' markets look soft, on evidence.

    python -m src.scout.report

Writes output/scout/report.json, output/scout/REPORT.md, output/scout/league_status.json and
output/scout/scout_health.json. Read-only on the store.

EVERY NUMBER HERE COMES FROM src/scout/truth.py (Data Truth, 2026-11-10): 90-minute results, the one
genuine-close rule (<= 60 min before the ACTUAL kickoff; Pinnacle, else a median of >= 3 books),
fixtures moved > 48 h void, model rows only with the result's league + team ids, frozen before the
actual kickoff and with a real prediction.

FOR EACH LEAGUE x MARKET, on settled fixtures with a genuine close:

  market skill   Brier of the de-vigged GENUINE close against the result, compared with the league's
                 base rate built ONLY from that league's results before each fixture's freeze (or
                 kickoff, without a freeze) — no look-ahead.
  model vs market
                 Brier of the frozen baseline model, and the RESIDUAL test: logistic regression of the
                 result on logit(market) and logit(model).
  paper bets     where the frozen model beat Bet365's price AT FREEZE TIME by more than EDGE_BAR:
                 flat-stake ROI at that price. The price must have been observed at most
                 close_max_minutes() before the freeze (the same age limit as a genuine close).

EDGE_BAR IS A PRE-REGISTERED RESEARCH GATE (owner 2026-11-10). It decides which paper cells are worth
studying, never what to bet: no staking or betting code may read it (tests/test_scout_data_truth.py).
A bar that bets is per league, like v9's.

NOTHING HERE IS A VERDICT UNTIL A LEAGUE HAS VOLUME. Status per league x market:
    COLLECTING  < 100 settled fixtures with a genuine close
    EARLY       100 - 299
    READABLE    >= 300
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.scout import leagues as reg
from src.scout import truth as T

OUT = cfg.OUTPUT_DIR / "scout"
#: Research gate only (see the module docstring). Never a staking bar.
EDGE_BAR = 0.05
RESEARCH_GATE_ONLY = True
STATUS = ((300, "READABLE"), (100, "EARLY"), (0, "COLLECTING"))
SIDE = T.SIDE
MODEL_COL = T.MODEL_COL
outcome = T.outcome
fair_prob = T.fair_prob


def asof(odds: pd.DataFrame, when: pd.DataFrame, max_age_min: float | None = None) -> pd.DataFrame:
    """Price per key as it stood at each fixture's freeze time (carry-forward), from the cleaned
    change-log. With `max_age_min`, a price observed longer than that before the freeze is not a
    bet-time price and is dropped (missing, not carried)."""
    o = T.clean_odds(odds).merge(when[["fixture_id", "frozen_ts"]], on="fixture_id")
    if o.empty:
        return o
    o = o.assign(_s=T._epoch(o["snapshot_ts"]), _f=T._epoch(o["frozen_ts"]))
    o = o[o["_s"] <= o["_f"]].sort_values("_s", kind="mergesort")
    o = o.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"], keep="last")
    if max_age_min is not None:
        o = o[(o["_f"] - o["_s"]) <= max_age_min * 60]
    return o.drop(columns=["_s", "_f"])


def residual(y, p_mkt, p_mod) -> dict:
    """Logistic regression y ~ a + b*logit(p_mkt) + c*logit(p_mod), Newton-Raphson.
    Returns c, its standard error and z. Positive c reliably above zero = model adds signal."""
    lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731
    cols = [np.ones(len(y)), lg(p_mkt), lg(p_mod)]
    # A market that quotes one price for every fixture is collinear with the intercept; it then
    # carries no information and is dropped rather than making the fit singular.
    if np.std(cols[1]) < 1e-9:
        cols.pop(1)
    X = np.column_stack(cols)
    beta = np.zeros(X.shape[1])
    if X.shape[1] == 3:
        beta[1] = 1.0
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ beta))
        W = mu * (1 - mu)
        H = X.T @ (X * W[:, None])
        try:
            step = np.linalg.solve(H, X.T @ (y - mu))
        except np.linalg.LinAlgError:
            return {"coef": None, "se": None, "z": None}
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    try:
        se = float(np.sqrt(np.linalg.inv(H)[-1, -1]))
    except np.linalg.LinAlgError:
        return {"coef": None, "se": None, "z": None}
    return {"coef": round(float(beta[-1]), 4), "se": round(se, 4), "z": round(float(beta[-1]) / se, 2)}


def _tables():
    return (store.read("scout_results"), store.read("scout_odds"), store.read("scout_model"),
            store.read("scout_results_ft90"), store.read("scout_fixture_status"))


def _cutoff(s: pd.DataFrame) -> pd.Series:
    """Freeze time where there is one, else the kickoff (epoch seconds) — the base-rate horizon."""
    ep = T._epoch(s["frozen_ts"])
    ep.index = s.index
    return ep.where(ep.notna(), s["kickoff_ts"].astype(float))


def build(tables: tuple | None = None) -> dict:
    res, odds, mdl, ft90, _st = tables if tables is not None else _tables()
    names = {x["id"]: (x["country"], x["name"], x["priority"]) for x in reg.load()}
    out = {"generated_at": cfg.utc_now_iso(),
           "status_rule": "COLLECTING <100, EARLY 100-299, READABLE >=300 settled fixtures with a GENUINE "
                          "close (<= 60 min before the actual kickoff; Pinnacle, else median of >= 3 books)",
           "data_truth": "src/scout/truth.py: 90-minute results, genuine close, >48h reschedules void, "
                         "model rows matched on league + team ids, frozen before the actual kickoff",
           "totals": {"results": 0 if res.empty else int(res["fixture_id"].nunique()),
                      "odds_rows": int(len(odds)), "fixtures_priced": 0 if odds.empty else
                      int(odds["fixture_id"].nunique()),
                      "fixtures_frozen": 0 if mdl.empty else int(mdl["fixture_id"].nunique())},
           "cells": []}
    if res.empty or odds.empty:
        return out
    s = T.settled(res, odds, mdl if not mdl.empty else None, ft90)
    out["excluded"] = s.attrs.get("excluded", {})
    if s.empty:
        return out
    served = T.results(res, ft90).dropna(subset=["home_goals", "away_goals", "kickoff_ts"])
    cutoff = _cutoff(s)
    paper_cap = T.close_max_minutes()
    for (lid, m), g in s.groupby(["league_id", "market"]):
        n = len(g)
        base = T.base_rate_before(served, lid, m, cutoff.loc[g.index])
        hb = base.notna()
        cell = {"league_id": int(lid), "country": names.get(lid, ("?",))[0],
                "league": names.get(lid, ("", "?"))[1],
                "priority": names.get(lid, ("", "", 9))[2], "market": m, "n": n,
                "status": next(lab for lim, lab in STATUS if n >= lim),
                "rate": round(float(g["y"].mean()), 4),
                "n_base_rate": int(hb.sum()),
                "brier_base_rate": round(float(((base[hb] - g["y"][hb]) ** 2).mean()), 4) if hb.any() else None,
                "brier_market_close": round(float(((g["p_close"] - g["y"]) ** 2).mean()), 4),
                "brier_market_close_on_base_rows": (round(float(((g["p_close"][hb] - g["y"][hb]) ** 2).mean()), 4)
                                                    if hb.any() else None),
                "reference": "pinnacle" if m != "btts" else "median"}
        cell["market_skill_vs_base"] = (round(1 - cell["brier_market_close_on_base_rows"] / cell["brier_base_rate"], 4)
                                        if cell["brier_base_rate"] else None)
        gm = g[g["p_model"].notna()].set_index("fixture_id")
        if len(gm) >= 30:
            cell["n_model"] = len(gm)
            cell["brier_model"] = round(float(((gm["p_model"] - gm["y"]) ** 2).mean()), 4)
            cell["residual"] = residual(gm["y"].to_numpy(), gm["p_close"].to_numpy(), gm["p_model"].to_numpy())
        if len(gm):
            bets = gm.join(raw_two_sided(odds, m, gm, paper_cap), how="inner")
            if len(bets):
                pm = bets["p_model"]
                take_first = (pm - 1 / bets["o_first"]) > EDGE_BAR
                take_second = (((1 - pm) - 1 / bets["o_second"]) > EDGE_BAR) & ~take_first
                ret = np.where(take_first, np.where(bets["y"] == 1, bets["o_first"] - 1, -1.0),
                               np.where(take_second, np.where(bets["y"] == 0, bets["o_second"] - 1, -1.0),
                                        np.nan))
                ret = pd.Series(ret).dropna()
                if len(ret):
                    cell["paper_bets"] = int(len(ret))
                    cell["paper_roi"] = round(float(ret.mean()), 4)
                    # one-sidedness is the failure signature to watch for (v9's MLS: 100% UNDER)
                    cell["paper_first_side_share"] = round(float(take_first.sum() / len(ret)), 3)
        out["cells"].append(cell)
    out["cells"].sort(key=lambda r: (r["priority"], -r["n"]))
    return out


def raw_two_sided(odds, m, gm: pd.DataFrame, max_age_min: float | None = None) -> pd.DataFrame:
    """Bet365's two prices at freeze time, as columns o_first / o_second. gm: index fixture_id,
    column frozen_ts."""
    when = gm.reset_index()[["fixture_id", "frozen_ts"]]
    o = asof(odds[(odds["market"] == m) & (odds["bookmaker"] == "bet365")
                  & odds["fixture_id"].isin(gm.index)], when, max_age_min)
    if o.empty:
        return pd.DataFrame(columns=["o_first", "o_second"])
    w = o.pivot_table(index="fixture_id", columns="selection", values="odds", aggfunc="last")
    a, b = SIDE[m]
    if a not in w or b not in w:
        return pd.DataFrame(columns=["o_first", "o_second"])
    return w.rename(columns={a: "o_first", b: "o_second"})[["o_first", "o_second"]].dropna()


def to_md(r: dict, health: dict | None = None) -> str:
    t = r["totals"]
    lines = [f"# League scout — {r['generated_at'][:16]} UTC", "",
             f"Results stored: {t['results']:,} · fixtures priced: {t['fixtures_priced']:,} · "
             f"model frozen: {t['fixtures_frozen']:,}", "", r["status_rule"], ""]
    if r.get("excluded"):
        lines += ["Left out by the Data Truth rules: " + ", ".join(f"{k} {v:,}" for k, v in r["excluded"].items()), ""]
    if health:
        lines += _health_md(health)
    if not r["cells"]:
        lines.append("No settled fixtures with a genuine close yet.")
        return "\n".join(lines)
    lines += ["| P | League | Market | n | Status | Market skill vs base rate | Model resid. z | Paper ROI (n) |",
              "|---|---|---|---|---|---|---|---|"]
    for c in r["cells"]:
        z = (c.get("residual") or {}).get("z")
        pr = f"{c['paper_roi']:+.1%} ({c['paper_bets']})" if "paper_roi" in c else "–"
        sk = "–" if c["market_skill_vs_base"] is None else f"{c['market_skill_vs_base']:+.3f}"
        lines.append(f"| {c['priority']} | {c['country']} {c['league']} | {c['market']} | {c['n']} | "
                     f"{c['status']} | {sk} | {'–' if z is None else z} | {pr} |")
    return "\n".join(lines)


def _health_md(h: dict) -> list[str]:
    L = ["## Coverage and staleness (Data Truth R15)", "",
         f"Since {h.get('scout_start')}: {h['totals']['finished']:,} finished watched fixtures, "
         f"{h['totals']['with_any_odds']:,} with any odds, {h['totals']['with_genuine_close']:,} with a genuine "
         f"close. Stale in-season leagues: {len(h['stale_leagues'])}. No odds offered by the API: "
         f"{len(h['no_odds_offered'])}. Unexplained missing results: "
         f"{h['counts'].get('due_without_result_unexplained', 0)}.", "",
         "| League | finished | odds coverage | genuine-close coverage | last price | flags |",
         "|---|---|---|---|---|---|"]
    for x in h["leagues"]:
        if x["flags"]:
            L.append(f"| {x['country']} {x['league']} ({x['league_id']}) | {x['finished']} | {x['odds_coverage']} | "
                     f"{x['close_coverage']} | {x['last_price_seen'] or '–'} | {', '.join(x['flags'])} |")
    return L + [""]


def _ledger_odds_answers(runs: pd.DataFrame | None = None) -> tuple[dict, dict]:
    """{league_id: polls recorded}, {league_id: polls whose /odds answer was empty} — from sweep
    ledger records that carry `leagues_empty` (recorded from 2026-11-10)."""
    if runs is None:
        try:
            from src.monitoring import collection_policy as pol
            runs = pol.load_runs()
        except Exception:                                              # noqa: BLE001
            return {}, {}
    polled, empty = {}, {}
    if runs is None or runs.empty or "detail" not in runs.columns:
        return polled, empty
    for r in runs[runs["collector"] == "scout_sweep"].itertuples():
        d = r.detail if isinstance(r.detail, dict) else {}
        if "leagues_empty" not in d:
            continue
        for lid in (d.get("leagues_polled") or {}):
            polled[int(lid)] = polled.get(int(lid), 0) + 1
        for lid in d.get("leagues_empty") or []:
            empty[int(lid)] = empty.get(int(lid), 0) + 1
    return polled, empty


def odds_offered(lid: int, last_price, polled: dict, empty: dict) -> str:
    """NO_ODDS_OFFERED: every recorded poll of the league came back empty and no price was ever
    stored. OFFERED: a price was stored. UNKNOWN: no recorded poll says either way."""
    has_price = last_price is not None and pd.notna(last_price)
    if has_price:
        return "OFFERED"
    if polled.get(lid, 0) and empty.get(lid, 0) == polled[lid]:
        return "NO_ODDS_OFFERED"
    return "UNKNOWN"


def health(tables: tuple | None = None, now: pd.Timestamp | None = None,
           runs: pd.DataFrame | None = None) -> dict:
    """Per-league coverage and staleness line + every Data Truth count (output/scout/scout_health.json)."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    res, odds, mdl, ft90, st = tables if tables is not None else _tables()
    watch = reg.load()
    served = T.results(res, ft90) if not res.empty else res
    start = pd.to_datetime(odds["snapshot_ts"], utc=True, errors="coerce").min() if not odds.empty else None
    s = (T.settled(res, odds, mdl if not mdl.empty else None, ft90)
         if not (res.empty or odds.empty) else pd.DataFrame())
    gfx = set(s["fixture_id"]) if len(s) else set()
    priced = set(odds["fixture_id"]) if not odds.empty else set()
    last_px = (pd.to_datetime(odds.groupby("league_id")["snapshot_ts"].max(), utc=True).to_dict()
               if not odds.empty else {})
    last_res = (served.dropna(subset=["kickoff_ts"]).groupby("league_id")["kickoff_ts"].max().to_dict()
                if len(served) else {})
    polled, empty = _ledger_odds_answers(runs)
    stale_cut = now - pd.Timedelta(days=T.STALE_DAYS)
    rows, tot = [], {"finished": 0, "with_any_odds": 0, "with_genuine_close": 0}
    for lg in watch:
        lid = lg["id"]
        if start is not None and len(served):
            f = set(served[(served["league_id"] == lid) & (served["kickoff_ts"] >= start.timestamp())]["fixture_id"])
        else:
            f = set()
        n_odds, n_close = len(f & priced), len(f & gfx)
        tot["finished"] += len(f)
        tot["with_any_odds"] += n_odds
        tot["with_genuine_close"] += n_close
        lp, lr = last_px.get(lid), last_res.get(lid)
        in_season = lr is not None and pd.notna(lr) and lr >= stale_cut.timestamp()
        stale = bool(in_season and (lp is None or pd.isna(lp) or lp < stale_cut))
        offered = odds_offered(lid, lp, polled, empty)
        flags = []
        if stale:
            flags.append(f"STALE >{T.STALE_DAYS}d in season")
        if offered == "NO_ODDS_OFFERED":
            flags.append("NO_ODDS_OFFERED by the API")
        if f and n_odds == 0:
            flags.append("NO_ODDS_CAPTURED")
        elif f and n_odds / len(f) < 0.5:
            flags.append("ODDS_COVERAGE_UNDER_HALF")
        rows.append({"league_id": lid, "country": lg["country"], "league": lg["name"], "finished": len(f),
                     "with_any_odds": n_odds, "with_genuine_close": n_close,
                     "odds_coverage": round(n_odds / len(f), 3) if f else None,
                     "close_coverage": round(n_close / len(f), 3) if f else None,
                     "last_price_seen": None if lp is None or pd.isna(lp) else lp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "days_since_price": None if lp is None or pd.isna(lp) else round((now - lp).total_seconds() / 86400, 1),
                     "last_result_kickoff": (None if lr is None or pd.isna(lr)
                                             else pd.Timestamp(lr, unit="s", tz="UTC").strftime("%Y-%m-%d")),
                     "in_season": bool(in_season), "stale": stale, "odds_offered": offered, "flags": flags})
    counts = T.audit(res, odds, mdl, ft90, st, now) if not res.empty else {}
    return {"generated_at": cfg.utc_now_iso(), "scout_start": None if start is None else start.strftime("%Y-%m-%d"),
            "rules": {"stale_days": T.STALE_DAYS, "result_grace_hours": T.RESULT_GRACE_HOURS,
                      "reschedule_void_hours": T.RESCHEDULE_VOID_HOURS,
                      "genuine_close_max_minutes": T.close_max_minutes()},
            "totals": tot, "counts": counts,
            "stale_leagues": [x["league_id"] for x in rows if x["stale"]],
            "no_odds_offered": [x["league_id"] for x in rows if x["odds_offered"] == "NO_ODDS_OFFERED"],
            "leagues": rows}


def league_status(report: dict | None = None, tables: tuple | None = None, hl: dict | None = None) -> dict:
    """One row per WATCHED league — all of them, including ones with no data yet — for the dashboard.

    The dashboard is a viewer and must not read the season store's parquet partitions at render
    time (it has ~1 GB and has died from that twice), so every count it shows is computed here.
    """
    import json as _json
    watch = reg.load()
    res, odds, mdl, ft90, _st = tables if tables is not None else _tables()
    done_f = OUT / "history_done.json"
    done = _json.loads(done_f.read_text(encoding="utf-8")) if done_f.exists() else {}
    now = pd.Timestamp.now(tz="UTC")
    served = T.results(res, ft90) if not res.empty else res

    def per_league(df, col="fixture_id"):
        if df is None or df.empty or "league_id" not in df.columns:
            return {}
        return df.groupby("league_id")[col].nunique().to_dict()

    n_res = per_league(served)
    n_px = per_league(odds)
    n_frozen = per_league(mdl)
    last_px = (odds.groupby("league_id")["snapshot_ts"].max().to_dict()
               if not odds.empty and "league_id" in odds.columns else {})
    upcoming = {}
    if not odds.empty and "kickoff_ts" in odds.columns:
        fut = odds[odds["kickoff_ts"] > now.timestamp()]
        upcoming = fut.groupby("league_id")["fixture_id"].nunique().to_dict()
    cells = {}
    for c in (report or {}).get("cells", []):
        cells.setdefault(c["league_id"], []).append(c)
    hrow = {x["league_id"]: x for x in (hl or {}).get("leagues", [])}
    rank = {"READABLE": 3, "EARLY": 2, "COLLECTING": 1}
    rows = []
    for lg in watch:
        lid = lg["id"]
        cs = cells.get(lid, [])
        best = max(cs, key=lambda c: rank.get(c["status"], 0)) if cs else None
        seasons = sum(1 for k in done if k.startswith(f"{lid}:"))
        status = (best["status"] if best else
                  "PRICING" if n_px.get(lid) else
                  "HISTORY_ONLY" if n_res.get(lid) else "NOT_STARTED")
        h = hrow.get(lid, {})
        rows.append({
            "league_id": lid, "country": lg["country"], "league": lg["name"], "priority": lg["priority"],
            "status": status, "history_seasons": seasons, "results": int(n_res.get(lid, 0)),
            "fixtures_priced": int(n_px.get(lid, 0)), "upcoming_priced": int(upcoming.get(lid, 0)),
            "model_frozen": int(n_frozen.get(lid, 0)),
            # genuine closes only (Data Truth R7): the report's cells count nothing else
            "settled_with_close": max((c["n"] for c in cs), default=0),
            "last_price_seen": last_px.get(lid),
            "odds_coverage": h.get("odds_coverage"), "close_coverage": h.get("close_coverage"),
            "stale": h.get("stale"), "odds_offered": h.get("odds_offered"), "coverage_flags": h.get("flags", []),
            "markets": {c["market"]: {k: c.get(k) for k in ("n", "status", "rate", "market_skill_vs_base",
                                                             "residual", "paper_bets", "paper_roi",
                                                             "paper_first_side_share")} for c in cs},
        })
    return {"generated_at": cfg.utc_now_iso(), "n_leagues": len(rows),
            "status_counts": pd.Series([r["status"] for r in rows]).value_counts().to_dict(),
            "status_meaning": {
                "NOT_STARTED": "nothing collected yet",
                "HISTORY_ONLY": "past results stored; no current prices captured yet (off-season or no fixtures)",
                "PRICING": "prices are being captured; no settled fixture with a genuine close yet",
                "COLLECTING": "fewer than 100 settled fixtures with a genuine close — no verdict possible",
                "EARLY": "100-299 settled — a first, noisy read",
                "READABLE": "300+ settled — the market-skill and residual tests can be read"},
            "leagues": rows}


def main() -> int:
    tables = _tables()
    r = build(tables)
    hl = health(tables)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "league_status.json").write_text(json.dumps(league_status(r, tables, hl), indent=1, default=str),
                                            encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "scout_health.json").write_text(json.dumps(hl, indent=1, default=str), encoding="utf-8")
    (OUT / "REPORT.md").write_text(to_md(r, hl), encoding="utf-8")
    print(f"[scout report] {len(r['cells'])} league x market cell(s); totals {r['totals']}")
    print(f"[scout health] {hl['totals']}; stale {hl['stale_leagues']}; no odds offered {hl['no_odds_offered']}")
    print(f"[scout health] counts {hl['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
