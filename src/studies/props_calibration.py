"""Props calibration monitor — does v9's live props model predict what actually happens on its tips?

    python -m src.studies.props_calibration     # -> output/studies/props_calibration.json + PROPS_CALIBRATION.md

WHY (owner, 2026-10-14). The props hit rate rose Aug -> Oct (SOT 1+ 36% -> 43%), which looked like the
model improving. Split by market it was the opposite: the model PREDICTED ~29% on SOT 1+ while 43%
happened - it under-predicts the starters it tips, because it was trained on every appearance
(substitutes included) and does not know who starts. That is a model defect the calibration PR and
Player V3 (expected minutes) are meant to fix. This monitor keeps measuring it, daily, so a fix shows
up as the gap closing - or does not.

Reads v9's own settled ledger (player_ledger.csv, WIN/LOSS only). Per market and month, and for the
last 30 days: tips, mean model probability, realised hit rate, gap = hit - predicted with a 90% CI by
bootstrap over match days. Priced tips also get the break-even view: hit rate vs the bookmaker's
implied probability (a higher hit rate is worth nothing if the price already says more).

Status per market (last 30 days, >= 100 tips): UNDER_PREDICTS (CI above 0), OVER_PREDICTS (CI below
0), CALIBRATED (CI includes 0); fewer tips -> INSUFFICIENT. Research only; changes nothing in v9.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.common import block_ci

MIN_N = 100
OUT = cfg.OUTPUT_DIR / "studies"


def load() -> pd.DataFrame:
    d = pd.read_csv(cfg.V9_LOCAL / "output" / "player_ledger.csv", low_memory=False)
    d = d[d["result"].isin(["WIN", "LOSS"])].copy()
    d["win"] = (d["result"] == "WIN").astype(float)
    for c in ("model_prob", "market_odds", "pnl"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["day"] = pd.to_datetime(d["match_date"].astype(str).str[:10], errors="coerce")
    return d.dropna(subset=["day", "model_prob"])


def _cell(g: pd.DataFrame) -> dict:
    gap = g["win"] - g["model_prob"]
    out = {"n": int(len(g)), "predicted": round(float(g["model_prob"].mean()), 3),
           "hit": round(float(g["win"].mean()), 3), "gap": round(float(gap.mean()), 3),
           "gap_ci90": block_ci(gap, g["day"].dt.strftime("%Y-%m-%d")) if len(g) >= 30 else [None, None]}
    pr = g[g["market_odds"] > 1]
    if len(pr):
        out["priced"] = {"n": int(len(pr)), "hit": round(float(pr["win"].mean()), 3),
                         "implied": round(float((1 / pr["market_odds"]).mean()), 3)}
    return out


def build() -> dict:
    d = load()
    cut = d["day"].max() - pd.Timedelta(days=30)
    res = {"by_month": {}, "last_30_days": {}, "status": {}}
    for (mk, per), g in d.groupby([d["market"], d["day"].dt.strftime("%Y-%m")]):
        res["by_month"].setdefault(mk, {})[per] = _cell(g)
    for mk, g in d[d["day"] > cut].groupby("market"):
        c = _cell(g)
        res["last_30_days"][mk] = c
        lo, hi = c["gap_ci90"]
        res["status"][mk] = ("INSUFFICIENT" if c["n"] < MIN_N or lo is None else
                             "UNDER_PREDICTS" if lo > 0 else "OVER_PREDICTS" if hi < 0 else "CALIBRATED")
    res["generated_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    res["data_to"] = str(d["day"].max().date())
    return res


def to_md(r: dict) -> str:
    L = [f"# Props calibration — live v9 model vs what happened ({r['generated_at']})", "",
         f"Settled prop tips to {r['data_to']}. Gap = realised hit rate minus the model's probability "
         "(positive = the model under-predicts). 90% CI by match day.", "",
         "## Last 30 days", "", "| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |",
         "|---|---|---|---|---|---|---|---|"]
    for mk, c in r["last_30_days"].items():
        p = c.get("priced")
        priced = "{:.0%} vs {:.0%} (n {})".format(p["hit"], p["implied"], p["n"]) if p else "—"
        L.append(f"| {mk} | {c['n']} | {c['predicted']:.1%} | {c['hit']:.1%} | {c['gap']:+.1%} | {c['gap_ci90']} | "
                 f"{r['status'][mk]} | {priced} |")
    L += ["", "## By month", "", "| Market | Month | Tips | Predicted | Happened | Gap |", "|---|---|---|---|---|---|"]
    for mk, months in r["by_month"].items():
        for per, c in months.items():
            L.append(f"| {mk} | {per} | {c['n']} | {c['predicted']:.1%} | {c['hit']:.1%} | {c['gap']:+.1%} |")
    L += ["", "A rising hit rate with a positive gap is the model being too cautious about the starters it tips, "
              "not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) "
              "and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's "
              "implied probability."]
    return "\n".join(L) + "\n"


def main() -> int:
    r = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "props_calibration.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "PROPS_CALIBRATION.md").write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
