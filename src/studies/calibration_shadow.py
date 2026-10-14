"""Grades v9's calibration SHADOW: production Platt vs log-odds Platt on settled matches.

    python -m src.studies.calibration_shadow      # -> output/studies/calibration_shadow.json + .md

WHAT. v9 branch `calibration-logit-shadow` (owner-approved 2026-10-14) makes every retrain fit a
second Platt on the log-odds of the raw probability and logs both numbers at first sight to
v9 output/calibration_shadow/{team,props}_<YYYY-MM>.csv. Production keeps using the old one. This
module settles those rows and asks one question per model family: is the shadow's log loss lower?

RULE - registered 2026-10-14, before any shadow row exists; never tuned after results:
  * metric: mean per-row log loss, shadow minus production (negative = shadow better);
    90% CI by bootstrap over whole match days (rows on one day are not independent).
  * per family (team: ou25, btts, over15, over35; props: each market):
      COLLECTING        n < N_MIN
      SHADOW_BETTER     n >= N_MIN and CI upper < 0
      SHADOW_WORSE      n >= N_MIN and CI lower > 0
      NOT_SHOWN         n >= N_MIN and CI includes 0
  * SWITCH_CANDIDATE overall = at least one family SHADOW_BETTER and none SHADOW_WORSE.
    A switch is still an owner decision and a separate v9 PR (flip predict to the shadow calibrator).
  N_MIN: team 1,000 fixtures per family; props 2,000 player rows per market. The retrospective gain
  was small for team models (-0.0004 to -0.0010), so a short window could not see it.

Results: team rows via API-Football (Pro's day-cached loader); props via v9's own player match log
(player_history.parquet target_<market>, joined on player_id and date +-1 day). Research only.
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.common import block_ci, logloss, match_frames, outcome, results, write

REGISTERED_ON = "2026-10-14"
N_MIN = {"team": 1000, "props": 2000}
TEAM_OUTCOME = {"ou25": "OU25", "btts": "BTTS", "over15": "OU15", "over35": "OU35"}
SHADOW_DIR = cfg.V9_LOCAL / "output" / "calibration_shadow"


def _read(kind: str) -> pd.DataFrame:
    files = sorted(glob.glob(str(SHADOW_DIR / f"{kind}_*.csv")))
    if not files:
        return pd.DataFrame()
    d = pd.concat([pd.read_csv(f, low_memory=False) for f in files], ignore_index=True)
    for c in ("p_prod", "p_raw_prod", "p_logit_shadow"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["date"] = d["date"].astype(str).str[:10]
    return d


def settle_team(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return d
    from src.scout.registry import literal_assignments
    ids = literal_assignments(cfg.V9_LOCAL / "config.py", ("API_FOOTBALL_IDS",)).get("API_FOOTBALL_IDS", {})
    end = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    d = d[d["date"] <= end]
    if d.empty:
        return d
    r = results(d["date"].min(), end, ids)
    if r.empty:
        return d.iloc[0:0]
    fx = d.drop_duplicates(["league", "date", "home_team", "away_team"])[["league", "date", "home_team", "away_team"]]
    fx = fx.assign(_ix=match_frames(fx, r, l_cols=("league", "date", "home_team", "away_team")))
    fx = fx.dropna(subset=["_ix"])
    fx[["hg", "ag"]] = r.loc[fx["_ix"].astype(int), ["hg", "ag"]].to_numpy()
    d = d.merge(fx.drop(columns="_ix"), on=["league", "date", "home_team", "away_team"], how="inner")
    d["y"] = [float(outcome(TEAM_OUTCOME[m], [h], [a])[0]) if m in TEAM_OUTCOME else np.nan
              for m, h, a in zip(d["market"], d["hg"], d["ag"])]
    return d.rename(columns={"p_prod": "p_old"}).dropna(subset=["y", "p_old", "p_logit_shadow"])


def settle_props(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty or "player_id" not in d.columns:
        return d.iloc[0:0]
    import pyarrow.dataset as ds
    path = cfg.V9_LOCAL / "player_history.parquet"
    have = set(ds.dataset(str(path)).schema.names)
    markets = sorted(d["market"].dropna().unique())
    cols = [c for c in ["player_id", "date"] + [f"target_{m}" for m in markets] if c in have]
    h = pd.read_parquet(path, columns=cols)
    h["date"] = pd.to_datetime(h["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    h = h.dropna(subset=["player_id", "date"])
    h["player_id"] = pd.to_numeric(h["player_id"], errors="coerce")
    d = d.copy()
    d["player_id"] = pd.to_numeric(d["player_id"], errors="coerce")
    d = d[d["player_id"].notna() & (d["player_id"] > 0)]
    out = []
    for shift in (0, 1, -1):                                         # local vs UTC dates
        dd = d.assign(_d=(pd.to_datetime(d["date"]) + pd.Timedelta(days=shift)).dt.strftime("%Y-%m-%d"))
        out.append(dd.merge(h, left_on=["player_id", "_d"], right_on=["player_id", "date"],
                            how="inner", suffixes=("", "_h")))
    s = pd.concat(out, ignore_index=True).drop_duplicates(["player_id", "date", "market"])
    s["y"] = np.nan
    for m in markets:
        if f"target_{m}" in s.columns:
            mk = s["market"] == m
            s.loc[mk, "y"] = pd.to_numeric(s.loc[mk, f"target_{m}"], errors="coerce")
    return s.rename(columns={"p_raw_prod": "p_old"}).dropna(subset=["y", "p_old", "p_logit_shadow"])


def grade(d: pd.DataFrame, kind: str) -> dict:
    out = {}
    for m, g in d.groupby("market"):
        diff = logloss(g["p_logit_shadow"], g["y"]) - logloss(g["p_old"], g["y"])
        n = int(len(g))
        ci = block_ci(diff, g["date"]) if n >= 30 else [None, None]
        if n < N_MIN[kind]:
            v = "COLLECTING"
        elif ci[1] is not None and ci[1] < 0:
            v = "SHADOW_BETTER"
        elif ci[0] is not None and ci[0] > 0:
            v = "SHADOW_WORSE"
        else:
            v = "NOT_SHOWN"
        out[m] = {"n": n, "n_min": N_MIN[kind], "delta_logloss": round(float(np.mean(diff)), 5),
                  "ci90": ci, "verdict": v, "days": int(g["date"].nunique())}
    return out


def build() -> dict:
    team_raw, props_raw = _read("team"), _read("props")
    res = {"registered_on": REGISTERED_ON, "logged": {"team": int(len(team_raw)), "props": int(len(props_raw))},
           "team": {}, "props": {}}
    if not team_raw.empty:
        res["team"] = grade(settle_team(team_raw), "team")
    if not props_raw.empty:
        res["props"] = grade(settle_props(props_raw), "props")
    fam = [x["verdict"] for k in ("team", "props") for x in res[k].values()]
    if not fam:
        overall = "WAITING_FOR_SHADOW_ROWS"      # branch not merged, or no retrain since merge
    elif "SHADOW_WORSE" in fam:
        overall = "NO_SWITCH"
    elif "SHADOW_BETTER" in fam:
        overall = "SWITCH_CANDIDATE"
    else:
        overall = "COLLECTING"
    res["overall"] = overall
    res["generated_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    return res


def to_md(r: dict) -> str:
    L = [f"# Calibration shadow — v9 Platt vs log-odds Platt ({r['generated_at']})", "",
         f"Rule registered {r['registered_on']} (module docstring). Overall: **{r['overall']}**. "
         f"Logged rows: team {r['logged']['team']:,}, props {r['logged']['props']:,}.", "",
         "Δ = shadow log loss minus production (negative = shadow better), 90% CI by match day.", "",
         "| Family | Market | n settled / needed | Δ log loss | 90% CI | Verdict |", "|---|---|---|---|---|---|"]
    for k in ("team", "props"):
        for m, x in r[k].items():
            L.append(f"| {k} | {m} | {x['n']:,} / {x['n_min']:,} | {x['delta_logloss']:+.5f} | {x['ci90']} | {x['verdict']} |")
    if r["overall"] == "WAITING_FOR_SHADOW_ROWS":
        L += ["", "No shadow rows yet: v9 logs them only after the `calibration-logit-shadow` PR is merged "
                  "and the next retrain has fitted the shadow calibrators."]
    return "\n".join(L) + "\n"


def main() -> int:
    r = build()
    write("calibration_shadow", r)
    (cfg.OUTPUT_DIR / "studies" / "CALIBRATION_SHADOW.md").write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
