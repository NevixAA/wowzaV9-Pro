"""PRICE TRADER v2 — fixed entry horizons, A/B/C classification, state machine, controls, breakeven,
capacity, lineage (owner brief 2026-10-19). RESEARCH ONLY: no orders, no messages, no stakes.

    python -m src.price_trader.research      # after src.price_trader.lab -> output/price_trader/v2/*

Builds on the v1 lab's canonical data (trades.parquet + price_paths.parquet: real recorded quotes,
carried forward per book, never a later price for an earlier decision).

THREE THINGS KEPT APART (brief §4) — every trade outcome carries exactly one label:
  PREDICTED_PRICE_EDGE      entered expecting a better later price; nothing locked
  EXECUTABLE_BACK_TO_LAY    a later RECORDED hedge price was taken (bookmaker dutch of the opposite
                            side, or exchange back of the opposite side == a lay); P/L from that quote
  LOCKED_ARBITRAGE          both sides coverable at ONE timestamp with enough quoted size after costs.
                            Never assigned here: no stake size / lay ladder exists in the data, so a
                            same-moment price gap is reported as UNSIZED_SIMULTANEOUS_GAP instead.

ENTRY HORIZONS (§6) are fixed before any outcome is seen: EARLIEST (first quote at/after the Wowza
signal), T-48h, T-24h, T-12h, T-6h, T-3h, T-1h, T-30m. A horizon is eligible for a trade only if the
signal existed by then (signal_ts <= entry time) — the signal is never borrowed from the future.

EXIT RULES (§9), PRE-REGISTERED in registry/price_trader/registration_v1.json:
  GREEN_{1,2,3}PCT   hedge the first time the locked ROI on the back stake reaches the target
  PROB_{1,2,3}PP     hedge the first time the market moves toward the side by that many pp
  STOP_{1,2,3}PP     hedge the first time the market moves AGAINST the side by that many pp
  each falls back to TIME: hedge at the last quote at or before T-1h (else the last pre-kickoff quote)
A rule only ever looks at the current and earlier rows of the path.

CONTROLS (§11), scored at the SAME entries with the SAME rule: OPPOSITE, RANDOM_DIRECTION (seeded coin),
SHUFFLED_RESIDUAL (Wowza sides permuted within league x market), MARKET_ONLY (back the market favourite),
LONG_MOMENTUM (side the market moved toward in the 24h before entry), MEAN_REVERSION (the other one).
"""
from __future__ import annotations

import hashlib
import json
import subprocess

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.price_trader import hedge as H
from src.price_trader.lab import OUT as V1

CALC = "price_trader-2.0.0"
OUT = V1 / "v2"
REG_DIR = cfg.BASE_DIR / "registry" / "price_trader"
HORIZONS = {"EARLIEST": None, "T-48h": 48 * 60, "T-24h": 24 * 60, "T-12h": 12 * 60, "T-6h": 360,
            "T-3h": 180, "T-1h": 60, "T-30m": 30}
RULES = {**{f"GREEN_{k}PCT": ("green", k / 100) for k in (1, 2, 3)},
         **{f"PROB_{k}PP": ("prob", k / 100) for k in (1, 2, 3)},
         **{f"STOP_{k}PP": ("stop", k / 100) for k in (1, 2, 3)},
         "TIME_T-1h": ("time", None)}
PRIMARY = ("EARLIEST", "GREEN_2PCT", "book", 0.0, 0.0)          # horizon, rule, venue, commission, slip
VENUES = {"book": 0.0, "exchange_2pct": 0.02, "exchange_5pct": 0.05}
SLIPS = (0.0, 0.01)
STAKES = (10, 100, 500, 1000)
TIME_EXIT_MIN = 60
CONTROLS = ("OPPOSITE", "RANDOM_DIRECTION", "SHUFFLED_RESIDUAL", "MARKET_ONLY", "LONG_MOMENTUM",
            "MEAN_REVERSION")


# ── lineage ──────────────────────────────────────────────────────────────────────────────────
def _git(path) -> str:
    import os
    if os.getenv(GITHUB_SHA) and str(path) == str(cfg.BASE_DIR):
        return os.getenv(GITHUB_SHA)[:12]
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=path, capture_output=True,
                               text=True, timeout=20).stdout.strip() or "unknown"
    except Exception:                                                  # noqa: BLE001
        return "unknown"


def _sha(p) -> str:
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    except Exception:                                                  # noqa: BLE001
        return "missing"


def lineage(data_start, data_end, n_rows) -> dict:
    return {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "source_git_sha": {"pro": _git(cfg.BASE_DIR), "v9": _git(cfg.V9_LOCAL)},
            "calculation_version": CALC, "data_start": str(data_start)[:19], "data_end": str(data_end)[:19],
            "number_of_rows": int(n_rows), "registration_version": registration()["version"],
            "input_hashes": {"trades.parquet": _sha(V1 / "trades.parquet"),
                             "price_paths.parquet": _sha(V1 / "price_paths.parquet")}}


# ── registration (immutable; a change is a NEW version and a new forward window) ───────────────
REGISTRATION_V1 = {
    "version": "price_trader_registration_v1",
    "registered_at": "2026-10-19",
    "forward_window_start": "2026-10-20",
    "status": "PAPER_SHADOW_ONLY",
    "eligible_leagues": "every non-paper league Wowza tips (paper league USA MLS excluded)",
    "markets": ["OU15", "OU25", "OU35", "BTTS"],
    "entry_horizons": list(HORIZONS),
    "exit_rules": list(RULES),
    "primary_setup": {"horizon": PRIMARY[0], "rule": PRIMARY[1], "venue": PRIMARY[2],
                      "commission": PRIMARY[3], "slippage": PRIMARY[4]},
    "time_exit": "last quote at or before T-1h, else last pre-kickoff quote",
    "commission_assumptions": VENUES,
    "slippage_assumptions": list(SLIPS),
    "minimum_liquidity": "UNKNOWN — no size data; CAPACITY_UNKNOWN until an exchange ladder is captured",
    "controls": list(CONTROLS),
    "success_gates": {
        "PRICE_EDGE": ["N >= 150 completed paper trades", ">= 30 match days", "positive mean net P/L",
                       "90% lower bound > 0", "median price improvement (CLV) > 0",
                       "beats every control at the same entries", "no league > 50% of profit"],
        "EXECUTABLE_EDGE": ["PRICE_EDGE", "real exchange lay quotes with size", "commission + slippage included",
                            ">= 80% of intended hedge volume executable", "positive P/L after all costs"],
        "ARBITRAGE_PROVEN": ["simultaneous executable prices", "both outcomes positive",
                             "sufficient quoted size", "no hypothetical leg"]},
}


def registration() -> dict:
    """Write v1 once; afterwards verify it was never edited. A mutated file raises."""
    REG_DIR.mkdir(parents=True, exist_ok=True)
    p = REG_DIR / "registration_v1.json"
    body = json.dumps(REGISTRATION_V1, indent=1, sort_keys=True)
    if not p.exists():
        p.write_text(body, encoding="utf-8")
    on_disk = p.read_text(encoding="utf-8")
    if json.loads(on_disk) != REGISTRATION_V1:
        raise RuntimeError("registration_v1.json differs from the frozen v1 — create v2, never edit v1")
    return REGISTRATION_V1


# ── data status ──────────────────────────────────────────────────────────────────────────────
def data_status(P: pd.DataFrame) -> dict:
    ex = P["exch_opposite"].notna().mean() if len(P) else 0.0
    return {"BOOKMAKER_QUOTES_REAL": "YES",
            "EXCHANGE_BACK_PRICES_RECORDED": "YES" if ex > 0 else "NO",
            "exchange_opposite_coverage_of_path_rows": round(float(ex), 4),
            "EXCHANGE_LAY_LADDER_AVAILABLE": "NO",
            "EXECUTABLE_EXCHANGE_DATA_AVAILABLE": "NO",
            "EXECUTABLE_EXCHANGE_NOTE": ("exchange BACK prices on the opposite side exist (== a lay price) but "
                                         "with no matched/available size, so executability is unverified"),
            "STRICT_ARBITRAGE_TESTABLE": "NO",
            "CAPACITY_UNKNOWN": "YES",
            "SYNTHETIC_ODDS_USED": "NO"}


# ── per-trade simulation ─────────────────────────────────────────────────────────────────────
def _side_view(path: pd.DataFrame, flip: bool) -> dict:
    """Prices from the point of view of the side taken (flip = the opposite side), as plain lists."""
    p = path["consensus_probability"].astype(float).tolist()
    return {"ts": list(pd.to_datetime(path["timestamp"], utc=True)),
            "mins": path["minutes_to_kickoff"].astype(float).tolist(),
            "back": (path["best_opposite"] if flip else path["best_back"]).astype(float).tolist(),
            "opp": (path["best_back"] if flip else path["best_opposite"]).astype(float).tolist(),
            "ex_opp": (path["exch_back"] if flip else path["exch_opposite"]).astype(float).tolist(),
            "p": [1 - x for x in p] if flip else p}


def entry_row(v: pd.DataFrame, horizon_min, signal_ts, kickoff) -> int | None:
    """The quote LIVE at the entry moment, or None if the trader could not have entered then.

    EARLIEST: the first recorded quote at or after the signal.
    T-H:      eligible only if the signal existed by kickoff - H; the entry price is the last quote
              recorded at or before kickoff - H (paths are carry-forward, so that quote is the live one).
    Never a quote after the entry moment, never a signal from the future."""
    ts = v["ts"]
    if horizon_min is None:
        return next((i for i, x in enumerate(ts) if x >= signal_ts), None)
    entry_time = kickoff - pd.Timedelta(minutes=horizon_min)
    if signal_ts > entry_time:
        return None
    idx = [i for i, x in enumerate(ts) if x <= entry_time]
    return idx[-1] if idx else None


def simulate(v, i0: int, rule: str, venue_c: float, slip: float, use_exchange: bool) -> dict:
    """Deterministic state machine over rows i0..end. Only rows <= current are ever read.
     is a dict of plain lists (speed: ~1M simulations per run)."""
    kind, thr = RULES[rule]
    ts, mins, back, opp, exo, prob = v["ts"], v["mins"], v["back"], v["opp"], v["ex_opp"], v["p"]
    o = back[i0] * (1 - slip)
    p0 = prob[i0]
    log = [("CANDIDATE", None), ("ENTERED", ts[i0]), ("WAITING_FOR_TARGET", ts[i0])]
    if not (o > 1) or p0 != p0:
        return {"state": "VOID_DATA_FAILURE", "pnl": float("nan"), "label": "PREDICTED_PRICE_EDGE",
                "log": log + [("VOID_DATA_FAILURE", ts[i0])]}
    hedge_col = exo if use_exchange else opp

    def locked_at(j):
        u = hedge_col[j]
        if not (u == u and u > 1):
            return float("nan")
        u = u * (1 - slip)
        return H.locked_roi(o, u, venue_c) if u > 1 else float("nan")
    n = len(ts)
    t_exit = None
    for j in range(n - 1, i0, -1):
        if mins[j] >= TIME_EXIT_MIN:
            t_exit = j
            break
    last_pre = None
    for j in range(n - 1, i0, -1):
        if mins[j] >= 0:
            last_pre = j
            break
    for j in range(i0 + 1, n):
        if mins[j] < 0:
            break
        lk = locked_at(j)
        mv = prob[j] - p0
        hit = ((kind == "green" and lk == lk and lk >= thr) or (kind == "prob" and mv >= thr)
               or (kind == "stop" and mv <= -thr))
        if hit and lk == lk:
            st = {"green": "FULL_GREEN_AVAILABLE", "prob": "PARTIAL_HEDGE_AVAILABLE", "stop": "STOP_TRIGGERED"}[kind]
            closed = "CLOSED_GREEN" if lk > 0 else ("CLOSED_STOP" if kind == "stop" else "CLOSED_PARTIAL")
            return {"state": closed, "pnl": lk, "exit_ts": ts[j], "label": "EXECUTABLE_BACK_TO_LAY",
                    "log": log + [(st, ts[j]), (closed, ts[j])]}
        if t_exit is not None and j >= t_exit:
            break
    j = t_exit if t_exit is not None else last_pre
    if j is None:
        return {"state": "HELD_TO_KICKOFF", "pnl": float("nan"), "label": "PREDICTED_PRICE_EDGE",
                "log": log + [("HELD_TO_KICKOFF", None)]}
    lk = locked_at(j)
    if lk != lk:
        return {"state": "HELD_TO_KICKOFF", "pnl": float("nan"), "label": "PREDICTED_PRICE_EDGE",
                "log": log + [("HELD_TO_KICKOFF", ts[j])]}
    st = "CLOSED_GREEN" if lk > 0 else "CLOSED_STOP"
    return {"state": st, "pnl": lk, "exit_ts": ts[j], "label": "EXECUTABLE_BACK_TO_LAY",
            "log": log + [("TIME_EXIT", ts[j]), (st, ts[j])]}


def _control_sides(T: pd.DataFrame, P_by: dict) -> dict:
    """trade_id -> {control: flip?} decided from information at or before the EARLIEST entry."""
    rng = np.random.default_rng(20261019)
    out = {}
    # shuffled residual: permute Wowza's side choice within league x market (flip flag permuted)
    T = T.copy()
    T["flip_shuffle"] = False
    for _, g in T.groupby(["league", "market"]):
        sides = g["side"].to_numpy()
        perm = rng.permutation(sides)
        T.loc[g.index, "flip_shuffle"] = perm != sides
    for r in T.itertuples(index=False):
        path = P_by.get(r.trade_id)
        if path is None or path.empty:
            continue
        sig = pd.Timestamp(r.signal_ts)
        pre = path[path["timestamp"] <= sig]
        p_now = float(pre["consensus_probability"].iloc[-1]) if len(pre) else np.nan
        past = pre[pre["timestamp"] <= sig - pd.Timedelta(hours=24)]
        p_then = float(past["consensus_probability"].iloc[-1]) if len(past) else np.nan
        mom = (p_now - p_then) if (p_now == p_now and p_then == p_then) else np.nan
        out[r.trade_id] = {"OPPOSITE": True, "RANDOM_DIRECTION": bool(rng.random() < 0.5),
                           "SHUFFLED_RESIDUAL": bool(r.flip_shuffle),
                           "MARKET_ONLY": bool(p_now == p_now and p_now < 0.5),
                           "LONG_MOMENTUM": None if mom != mom or mom == 0 else bool(mom < 0),
                           "MEAN_REVERSION": None if mom != mom or mom == 0 else bool(mom > 0)}
    return out


def run() -> dict:
    T = pd.read_parquet(V1 / "trades.parquet")
    P = pd.read_parquet(V1 / "price_paths.parquet")
    P["timestamp"] = pd.to_datetime(P["timestamp"], utc=True)
    T = T[T["status"] == "OK"].copy()
    T["signal_ts"] = pd.to_datetime(T["signal_ts"], utc=True)
    T["kickoff"] = pd.to_datetime(T["kickoff"], utc=True)
    P_by = {k: g.sort_values("timestamp").reset_index(drop=True) for k, g in P.groupby("trade_id")}
    reg = registration()
    ctl = _control_sides(T, P_by)
    fwd_start = pd.Timestamp(reg["forward_window_start"], tz="UTC")
    rows, logs = [], []
    for r in T.itertuples(index=False):
        path = P_by.get(r.trade_id)
        if path is None or len(path) < 1:
            continue
        sides = {"WOWZA": False, **{c: f for c, f in ctl.get(r.trade_id, {}).items()}}
        for who, flip in sides.items():
            if flip is None:
                continue
            v = _side_view(path, flip)
            for hz, hmin in HORIZONS.items():
                i0 = entry_row(v, hmin, r.signal_ts, r.kickoff)
                if i0 is None:
                    continue
                pre_ko = [k for k, m in enumerate(v["mins"]) if m >= 0]
                c_back = v["back"][pre_ko[-1]] if pre_ko else np.nan
                p_close = v["p"][pre_ko[-1]] if pre_ko else np.nan
                for rule in RULES:
                    for venue, c in VENUES.items():
                        if who != "WOWZA" and venue != "book":
                            continue                       # controls on the primary venue only
                        for slip in SLIPS:
                            if who != "WOWZA" and slip:
                                continue
                            s = simulate(v, i0, rule, c, slip, use_exchange=venue != "book")
                            rec = {"trade_id": r.trade_id, "who": who, "league": r.league, "market": r.market,
                                   "side": r.side if not flip else ("UNDER" if r.side == "OVER" else
                                                                    "OVER" if r.side == "UNDER" else
                                                                    "NO" if r.side == "YES" else "YES"),
                                   "match_date": r.match_date, "horizon": hz, "rule": rule, "venue": venue,
                                   "commission": c, "slippage": slip, "entry_ts": v["ts"][i0],
                                   "entry_mins": float(v["mins"][i0]), "entry_back": v["back"][i0],
                                   "entry_p": v["p"][i0], "close_p": p_close,
                                   "move_pp": (p_close - v["p"][i0]) * 100 if p_close == p_close else np.nan,
                                   "clv": (v["back"][i0] / c_back - 1) if c_back == c_back and c_back > 1 else np.nan,
                                   "state": s["state"], "label": s.get("label", "PREDICTED_PRICE_EDGE"),
                                   "pnl": s["pnl"], "forward": bool(v["ts"][i0] >= fwd_start)}
                            rows.append(rec)
                            if who == "WOWZA" and (hz, rule, venue, c, slip) == PRIMARY:
                                for st, ts in s["log"]:
                                    logs.append({"trade_id": r.trade_id, "state": st,
                                                 "ts": None if ts is None else str(ts)})
    D = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    D.to_parquet(OUT / "sim_rows.parquet", index=False)
    pd.DataFrame(logs).to_csv(OUT / "paper_state_log.csv", index=False)
    return report(D, P)


# ── reporting ────────────────────────────────────────────────────────────────────────────────
def _ci(x, g, q=(0.05, 0.95), n=3000, seed=7):
    d = pd.DataFrame({"x": x, "g": g}).dropna().groupby("g")["x"].agg(["sum", "count"])
    if len(d) < 5:
        return [None, None]
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(d), size=(n, len(d)))
    m = d["sum"].to_numpy()[i].sum(1) / d["count"].to_numpy()[i].sum(1)
    return [round(float(np.quantile(m, v)), 5) for v in q]


def breakeven(g: pd.DataFrame) -> dict:
    """Observed favourable-exit rate vs the rate needed for zero expected P/L, given the average
    win and average loss of THIS setup after its costs (brief §10)."""
    d = g["pnl"].dropna()
    if len(d) < 10:
        return {"observed_favourable": None, "required_favourable": None, "tradeable": "INSUFFICIENT"}
    wins, losses = d[d > 0], d[d <= 0]
    obs = float((d > 0).mean())
    if len(wins) == 0:
        return {"observed_favourable": obs, "required_favourable": None, "tradeable": "NO (never favourable)"}
    if len(losses) == 0:
        return {"observed_favourable": obs, "required_favourable": 0.0, "tradeable": "YES"}
    req = float(abs(losses.mean()) / (wins.mean() + abs(losses.mean())))
    return {"observed_favourable": round(obs, 4), "required_favourable": round(req, 4),
            "margin_pp": round((obs - req) * 100, 2), "tradeable": "YES" if obs > req else "NO"}


def report(D: pd.DataFrame, P: pd.DataFrame) -> dict:
    W = D[D["who"] == "WOWZA"]
    hz_rows = []
    for (hz, rule, venue, c, slip), g in W.groupby(["horizon", "rule", "venue", "commission", "slippage"]):
        trades = g.dropna(subset=["pnl"])
        rec = {"horizon": hz, "rule": rule, "venue": venue, "commission": c, "slippage": slip,
               "fixtures": int(g["trade_id"].nunique()), "completed": int(len(trades)),
               "held_or_void": int(g["pnl"].isna().sum()),
               "favourable_move_rate": round(float((g["move_pp"] > 0).mean()), 4),
               "adverse_move_rate": round(float((g["move_pp"] < 0).mean()), 4),
               "mean_move_pp": round(float(g["move_pp"].mean()), 3),
               "median_clv": round(float(g["clv"].median()), 4) if g["clv"].notna().any() else None,
               "full_green_rate": round(float((trades["pnl"] > 0).mean()), 4) if len(trades) else None,
               "mean_pnl_per_unit": round(float(trades["pnl"].mean()), 5) if len(trades) else None,
               "pnl_ci90": _ci(trades["pnl"], trades["match_date"]) if len(trades) else [None, None],
               "p05_pnl": round(float(trades["pnl"].quantile(0.05)), 4) if len(trades) else None,
               **breakeven(g)}
        hz_rows.append(rec)
    HZ = pd.DataFrame(hz_rows)
    HZ.to_csv(OUT / "horizon_rule_results.csv", index=False)

    # controls vs Wowza at identical entries (primary venue, no slippage), per horizon x rule
    B = D[(D["venue"] == "book") & (D["slippage"] == 0)]
    ctl_rows = []
    for (hz, rule), g in B.groupby(["horizon", "rule"]):
        w = g[g["who"] == "WOWZA"].set_index("trade_id")
        for c in CONTROLS:
            k = g[g["who"] == c].set_index("trade_id")
            common_ids = w.index.intersection(k.index)
            if len(common_ids) < 20:
                continue
            a, b = w.loc[common_ids], k.loc[common_ids]
            d = (a["pnl"] - b["pnl"]).dropna()
            ctl_rows.append({"horizon": hz, "rule": rule, "control": c, "n": int(len(common_ids)),
                             "wowza_toward_rate": round(float((a["move_pp"] > 0).mean()), 4),
                             "control_toward_rate": round(float((b["move_pp"] > 0).mean()), 4),
                             "wowza_minus_control_toward": round(float((a["move_pp"] > 0).mean()
                                                                       - (b["move_pp"] > 0).mean()), 4),
                             "wowza_mean_pnl": round(float(a["pnl"].mean()), 5),
                             "control_mean_pnl": round(float(b["pnl"].mean()), 5),
                             "pnl_diff_ci90": _ci(d.to_numpy(), a.loc[d.index, "match_date"].to_numpy())})
    CT = pd.DataFrame(ctl_rows)
    CT.to_csv(OUT / "controls.csv", index=False)

    # league-specific placebo at the primary setup
    hz, rule = PRIMARY[0], PRIMARY[1]
    g = B[(B["horizon"] == hz) & (B["rule"] == rule)]
    lg_rows = []
    for lg, x in g.groupby("league"):
        w = x[x["who"] == "WOWZA"].set_index("trade_id")
        for c in ("SHUFFLED_RESIDUAL", "RANDOM_DIRECTION", "MARKET_ONLY"):
            k = x[x["who"] == c].set_index("trade_id")
            ids = w.index.intersection(k.index)
            if len(ids) < 10:
                continue
            lg_rows.append({"league": lg, "control": c, "n": len(ids),
                            "wowza_toward": round(float((w.loc[ids, "move_pp"] > 0).mean()), 4),
                            "control_toward": round(float((k.loc[ids, "move_pp"] > 0).mean()), 4),
                            "sample_status": "OK" if len(ids) >= 50 else "SMALL"})
    pd.DataFrame(lg_rows).to_csv(OUT / "placebo_by_league.csv", index=False)

    # capacity: no size data -> linear, explicitly theoretical
    prim = W[(W["horizon"] == PRIMARY[0]) & (W["rule"] == PRIMARY[1]) & (W["venue"] == PRIMARY[2])
             & (W["slippage"] == PRIMARY[4])].dropna(subset=["pnl"])
    mean_unit = float(prim["pnl"].mean()) if len(prim) else np.nan
    cap = {"CAPACITY_UNKNOWN": "YES", "available_back_size": "UNKNOWN", "available_lay_size": "UNKNOWN",
           "max_executable_stake": "UNKNOWN",
           **{f"expected_pnl_per_trade_at_{s}": (round(mean_unit * s, 2) if mean_unit == mean_unit else None)
              for s in STAKES},
           "note": "linear in stake ONLY because no size data exists; real limits would cut this"}

    # state counts + label counts at primary
    states = prim["state"].value_counts().to_dict() if len(prim) else {}
    labels = W[(W["horizon"] == PRIMARY[0]) & (W["rule"] == PRIMARY[1]) & (W["venue"] == "book")
               & (W["slippage"] == 0)]["label"].value_counts().to_dict()

    # forward gates on the primary setup
    fw = prim[prim["forward"]]
    days = fw["match_date"].nunique()
    ci = _ci(fw["pnl"], fw["match_date"]) if len(fw) else [None, None]
    lg_share = (fw.groupby("league")["pnl"].sum() / fw["pnl"].sum()).max() if len(fw) and fw["pnl"].sum() > 0 else None
    beats = None
    if len(CT):
        cp = CT[(CT["horizon"] == PRIMARY[0]) & (CT["rule"] == PRIMARY[1])]
        beats = bool(len(cp) and all((x[0] or 0) > 0 for x in cp["pnl_diff_ci90"]))
    gates = {"N_completed_forward": int(len(fw)), "N_required": 150, "match_days": int(days), "days_required": 30,
             "mean_pnl": round(float(fw["pnl"].mean()), 5) if len(fw) else None, "ci90": ci,
             "median_clv": round(float(fw["clv"].median()), 4) if len(fw) and fw["clv"].notna().any() else None,
             "beats_all_controls_historical": beats, "max_league_profit_share": lg_share}
    if len(fw) < 150 or days < 30:
        evidence = "COLLECTING"
    elif (ci[0] or -1) > 0 and (gates["median_clv"] or -1) > 0 and beats and (lg_share is None or lg_share <= 0.5):
        evidence = "PRICE_SIGNAL"
    else:
        evidence = "NO_EDGE"
    hist = W[(W["horizon"] == PRIMARY[0]) & (W["rule"] == PRIMARY[1]) & (W["venue"] == "book") & (W["slippage"] == 0)]
    verdict = {
        "EVIDENCE_STATE": evidence,
        "PRICE_EDGE": "NO" if evidence != "PRICE_SIGNAL" else "CANDIDATE",
        "EXECUTABLE_EDGE": "NOT_TESTABLE (no lay ladder / size)",
        "ARBITRAGE_PROVEN": "NOT_TESTABLE (no simultaneous sized quotes)",
        "historical_primary": {"n": int(hist["pnl"].notna().sum()),
                               "mean_pnl_per_unit": round(float(hist["pnl"].mean()), 5) if len(hist) else None,
                               "full_green_rate": round(float((hist["pnl"] > 0).mean()), 4) if len(hist) else None,
                               "status": "EXPLORATORY (pre-registration history)"},
        "forward_gates": gates, "states_primary": states, "labels_primary": labels,
        "data_status": data_status(P), "capacity": cap,
        "PRODUCTION_SELECTION_CHANGED": "NO", "PRODUCTION_THRESHOLDS_CHANGED": "NO",
        "PRODUCTION_STAKING_CHANGED": "NO", "REAL_BETTING_ENABLED": "NO",
        "lineage": lineage(D["entry_ts"].min(), D["entry_ts"].max(), len(D)),
    }
    (OUT / "verdict_v2.json").write_text(json.dumps(verdict, indent=1, default=str), encoding="utf-8")
    return verdict


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
