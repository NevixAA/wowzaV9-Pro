"""LONGSHOT ENGINE — frozen version + PROSPECTIVE monthly evaluation (owner brief 2026-10-19 §20).

    python -m src.analytics.longshot_forward     # -> output/longshot_plan/forward_monthly.csv + status json

The 2026-10-17 plan found the BET_ENABLED filter does NOT beat the best simple baseline. That result
stands. This module freezes the filter AS IT IS (no re-tuning until the answer turns positive) and
scores it once per completed month, from the first full month after the freeze, against simple
baselines on the SAME month:

    ALL_NEW_FORMAT, NEW_FORMAT_BTTS, CURRENT_BALANCED_POLICY, SNIPER_ONLY,
    SHORTEST_ODDS (each day, as many bets as the engine kept, the shortest-odds non-MLS bets),
    RANDOM_MATCHED (each day, as many bets as the engine kept, drawn at random; mean of 500 draws)

Metrics: ROI, profit, max drawdown, profit/drawdown, CLV, bet count, top-league share.
A month is logged ONCE (append-only) after it has fully settled. >= 6 forward months before the filter
may inform production eligibility, unless the owner explicitly overrides.

FROZEN = registry/longshot/registration_v1.json, which records a SHA-256 of longshot_plan.py: if the
gate logic changes, the hash no longer matches and the forward log refuses to continue under v1.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.analytics import core as C
from src.analytics import longshot_plan as LP

VERSION = "longshot-1.0.0"
REG = cfg.BASE_DIR / "registry" / "longshot" / "registration_v1.json"
OUT = cfg.OUTPUT_DIR / "longshot_plan"
LOG = OUT / "forward_monthly.csv"
FORWARD_FROM = "2026-11"          # first full month after the 2026-10-19 freeze
MIN_MONTHS = 6
SETTLE_LAG_DAYS = 4


def _src_sha() -> str:
    return hashlib.sha256(Path(LP.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def registration() -> dict:
    REG.parent.mkdir(parents=True, exist_ok=True)
    body = {"version": VERSION, "frozen_at": "2026-10-19", "forward_from_month": FORWARD_FROM,
            "gate_logic_file": "src/analytics/longshot_plan.py", "gate_logic_sha256": _src_sha(),
            "gates": LP.GATES, "shrink_K": LP.K, "eligibility": "a bet is kept unless any gate it belongs to is "
            "FALSE, flags computed on data before the month (walk_forward)",
            "baselines": ["ALL_NEW_FORMAT", "NEW_FORMAT_BTTS", "CURRENT_BALANCED_POLICY", "SNIPER_ONLY",
                          "SHORTEST_ODDS", "RANDOM_MATCHED"],
            "min_forward_months_before_production_use": MIN_MONTHS,
            "historical_result_at_freeze": "FILTER_BEATS_SIMPLE_BASELINES = NO (2026-10-17 plan)"}
    if not REG.exists():
        REG.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")
    return json.loads(REG.read_text(encoding="utf-8"))


def _metrics(x: pd.DataFrame) -> dict:
    if x is None or len(x) == 0:
        return {"N": 0}
    dd = C.drawdown(x).get("max_drawdown_units", np.nan)
    pnl = float(x["pnl"].sum())
    pos = x.groupby("league")["pnl"].sum()
    return {"N": int(len(x)), "PnL": round(pnl, 3), "ROI": round(float(x["pnl"].mean()), 4),
            "max_drawdown": round(float(dd), 3) if dd == dd else None,
            "profit_over_drawdown": round(pnl / dd, 3) if dd and dd == dd and dd > 0 else None,
            "avg_CLV": round(float(x["clv"].mean()), 4) if x["clv"].notna().any() else None,
            "top_league_share": round(float(pos.max() / pos[pos > 0].sum()), 3) if (pos > 0).any() else None}


def month_table(pool: pd.DataFrame, kept: pd.DataFrame, policy: dict, month: str, seeds: int = 500) -> list[dict]:
    start = pd.Timestamp(month + "-01")
    end = start + pd.offsets.MonthEnd(0)
    w = pool[(pool["date"] >= start) & (pool["date"] <= end)]
    k = kept[(kept["date"] >= start) & (kept["date"] <= end)]
    tracks = policy.get("tracks", {})

    def in_policy(r):
        t = tracks.get(f"{r['model']}|{r['market']}", {})
        return (t.get("state") in ("ACTIVE", "ACTIVE_LOW") and r["tier"] in C.CORE_TIERS
                and float(t.get("min_odds") or 1) <= r["odds"] <= float(t.get("max_odds") or 99))
    per_day = k.groupby("day").size()
    short = pd.concat([w[w["day"] == d].nsmallest(n, "odds") for d, n in per_day.items()]) if len(per_day) else w.iloc[0:0]
    sets = {"LONGSHOT_ENGINE_v1": k, "ALL_NEW_FORMAT": w[w.model == "new_format"],
            "NEW_FORMAT_BTTS": w[(w.model == "new_format") & (w.market == "BTTS")],
            "CURRENT_BALANCED_POLICY": w[w.apply(in_policy, axis=1)] if len(w) else w,
            "SNIPER_ONLY": w[w.tier == "SNIPER"], "SHORTEST_ODDS": short}
    rows = [{"month": month, "strategy": n, **_metrics(x)} for n, x in sets.items()]
    rng = np.random.default_rng(int(month.replace("-", "")))
    sims = []
    for _ in range(seeds):
        draw = pd.concat([w[w["day"] == d].sample(n=min(n, (w["day"] == d).sum()),
                                                  random_state=int(rng.integers(1e9)))
                          for d, n in per_day.items()]) if len(per_day) else w.iloc[0:0]
        sims.append(float(draw["pnl"].sum()))
    rows.append({"month": month, "strategy": "RANDOM_MATCHED (mean of 500)", "N": int(per_day.sum()),
                 "PnL": round(float(np.mean(sims)), 3) if sims else None,
                 "ROI": round(float(np.mean(sims) / per_day.sum()), 4) if sims and per_day.sum() else None,
                 "random_p05_p95_PnL": [round(float(np.quantile(sims, q)), 2) for q in (0.05, 0.95)] if sims else None,
                 "engine_percentile_vs_random": (round(float((np.array(sims) < float(k["pnl"].sum())).mean()), 3)
                                                 if sims else None)})
    for r in rows:
        r.update({"version": VERSION, "logged_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")})
    return rows


def run() -> dict:
    reg = registration()
    sha_ok = reg.get("gate_logic_sha256") == _src_sha()
    I = LP.D.load_inputs()
    s = LP.prepare(I["s"])
    pool = C.universes(s, cfg.PAPER_LEAGUES, I["policy"])["NON_MLS"]
    latest = pool["date"].max()
    months = sorted(m for m in pool["month"].unique() if m >= "2026-09")
    _, wf_bets = LP.walk_forward(pool, None, months)
    kept = wf_bets[wf_bets["kept"]] if len(wf_bets) else wf_bets
    logged = set(pd.read_csv(LOG)["month"]) if LOG.exists() else set()
    complete = [m for m in months if m >= FORWARD_FROM and m not in logged
                and (pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0)) + pd.Timedelta(days=SETTLE_LAG_DAYS) <= latest]
    new_rows = []
    if sha_ok:
        for m in complete:
            new_rows += month_table(pool, kept, I["policy"], m)
        if new_rows:
            OUT.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(new_rows).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
    # pre-freeze months: EXPLORATORY, recomputed, never logged as forward evidence
    pre = [r for m in months if m < FORWARD_FROM for r in month_table(pool, kept, I["policy"], m, seeds=200)]
    pd.DataFrame(pre).to_csv(OUT / "pre_freeze_months_EXPLORATORY.csv", index=False)
    n_fwd = len(set(pd.read_csv(LOG)["month"])) if LOG.exists() else 0
    status = {"version": VERSION, "gate_logic_unchanged": sha_ok,
              "forward_months_logged": n_fwd, "forward_months_required": MIN_MONTHS,
              "STATUS": ("FROZEN_LOGIC_CHANGED — start registration_v2" if not sha_ok else
                         "COLLECTING" if n_fwd < MIN_MONTHS else "READY_FOR_REVIEW"),
              "PRODUCTION_ELIGIBILITY_USE": "NO", "latest_settled": str(latest.date()),
              "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")}
    (OUT / "forward_status.json").write_text(json.dumps(status, indent=1), encoding="utf-8")
    return status


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
