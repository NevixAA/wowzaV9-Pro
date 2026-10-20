"""O/U INFORMATION INPUTS — do injuries (and, later, lineups / team news / price movement) improve
v9's O/U 2.5 model? (owner 2026-10-19: "of course we need to use that for the models")

    python -m src.studies.ou_info_inputs fetch      # API-Football injuries + fixtures, cached
    python -m src.studies.ou_info_inputs features   # as-of injury features joined to v9's frame
    python -m src.studies.ou_info_inputs audit      # leakage + data-integrity checks
    python -m src.studies.ou_info_inputs eval       # walk-forward, v9's own trainer, both arms
    python -m src.studies.ou_info_inputs report

THE LOOP (owner rule): v9 runs · v11 researches · Pro tests · Pro beats v9 -> upgrade, and only after
the data has been checked for bugs and leakage. This study is the "Pro tests" step for one family of
inputs. It never writes into v9; an upgrade is a separate, owner-approved change that the v9 champion
gate then has to confirm on its own holdout.

WHY INJURIES FIRST. v9 already computes `key_attacker_absent_home/away` (feature_engineering.py) but
does not train on it, and API-Football keeps a full injury history per league-season — one request
each — so it is the only collected-but-unused input with enough HISTORY to train and test today.
Lineups / team news exist only since 2026-08-30 (418 team rows) and price movement since 2026-08-11:
those are collected forward and evaluated when they have volume (see `coverage()`).

AS-OF DISCIPLINE. A feature for fixture F may use only (a) the injury list API-Football attaches to F
and (b) player output from matches strictly BEFORE F's date. The audit step tests (a) for hindsight.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies import common

EXP = cfg.BASE_DIR / "experiments" / "ou_info_inputs_2026_10"
CACHE = EXP / "cache"                      # raw API responses — never committed
OUT = cfg.OUTPUT_DIR / "studies"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
AF = "https://v3.football.api-sports.io"


def _league_ids() -> dict[str, int]:
    """Our standard + new-format leagues -> API-Football id, read from v9's config text (no import:
    v9's `config` would shadow Pro's)."""
    import ast
    src = (Path(cfg.V9_LOCAL) / "config.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    vals = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("API_FOOTBALL_IDS", "STANDARD_FORMAT_LEAGUES", "NEW_FORMAT_LEAGUES"):
                try:
                    vals[name] = ast.literal_eval(node.value)
                except Exception:                                      # noqa: BLE001
                    pass
    ours = set(vals.get("STANDARD_FORMAT_LEAGUES", [])) | set(vals.get("NEW_FORMAT_LEAGUES", []))
    return {k: v for k, v in vals["API_FOOTBALL_IDS"].items() if k in ours}


def _get(endpoint: str, params: dict) -> dict:
    import requests
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (endpoint + "_" + "_".join(f"{k}{v}" for k, v in sorted(params.items())) + ".json")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    for attempt in range(3):
        r = requests.get(f"{AF}/{endpoint}", headers={"x-apisports-key": common._af_key()},
                         params=params, timeout=90)
        body = r.json()
        if not body.get("errors"):
            break
        time.sleep(2 + attempt * 3)
    if body.get("errors"):
        raise RuntimeError(f"API-Football {endpoint} {params}: {body['errors']}")
    f.write_text(json.dumps(body), encoding="utf-8")
    time.sleep(0.15)
    return body


def fetch() -> dict:
    """One /injuries and one /fixtures call per league-season. Permanent cache (finished seasons
    never change; the live season is re-fetched by deleting its two files)."""
    calls = 0
    inj, fx = [], []
    for lg, lid in sorted(_league_ids().items()):
        for s in SEASONS:
            before = len(list(CACHE.glob("*.json"))) if CACHE.exists() else 0
            bi = _get("injuries", {"league": lid, "season": s})
            bf = _get("fixtures", {"league": lid, "season": s})
            calls += len(list(CACHE.glob("*.json"))) - before
            for x in bi.get("response", []):
                fx_ = x.get("fixture") or {}
                inj.append({"league": lg, "season": s, "af_fixture_id": fx_.get("id"),
                            "fixture_ts": fx_.get("date"), "team_id": (x.get("team") or {}).get("id"),
                            "team": (x.get("team") or {}).get("name"),
                            "player_id": (x.get("player") or {}).get("id"),
                            "player": (x.get("player") or {}).get("name"),
                            "type": (x.get("player") or {}).get("type"),
                            "reason": (x.get("player") or {}).get("reason")})
            for x in bf.get("response", []):
                fx.append({"league": lg, "season": s, "af_fixture_id": x["fixture"]["id"],
                           "fixture_ts": x["fixture"]["date"], "status": x["fixture"]["status"]["short"],
                           "home_id": x["teams"]["home"]["id"], "home_team": x["teams"]["home"]["name"],
                           "away_id": x["teams"]["away"]["id"], "away_team": x["teams"]["away"]["name"],
                           "hg": x["goals"]["home"], "ag": x["goals"]["away"]})
    EXP.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(inj).to_parquet(EXP / "injuries.parquet", index=False)
    pd.DataFrame(fx).to_parquet(EXP / "af_fixtures.parquet", index=False)
    cov = (pd.DataFrame(inj).groupby(["league", "season"]).size().rename("injury_rows").reset_index()
           if inj else pd.DataFrame())
    cov.to_csv(EXP / "injury_coverage.csv", index=False)
    return {"api_calls_made": calls, "injury_rows": len(inj), "fixtures": len(fx),
            "league_seasons_with_injuries": int((cov["injury_rows"] > 0).sum()) if len(cov) else 0}


#: A league-season counts as COVERED only with real volume. Below this, API-Football lists a handful of
#: long-term absentees and nothing else, and a zero would claim "nobody missing" — invariant 9: NaN.
MIN_ROWS_COVERED = 500
INJ_COLS = ["inj_n_missing", "inj_n_questionable", "inj_minutes_share", "inj_goal_share"]
LOOKBACK = 10                               # team matches used to weight a missing player


def dedup_alias_matches(fr: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop the second copy of a real match stored under another spelling of a club.

    FOUND 2026-10-19: v9's training frame holds the same match twice when football-data and the
    API-Football bank spell a club differently (`AIK` / `AIK Stockholm`, `Hull` / `Hull City`) — same
    date, same score. 6,229 rows since 2023 (14%). A copy is: same league, same date, same score, and
    both clubs the same by `common.same_club`. The first row is kept."""
    d = fr.reset_index(drop=True)
    drop = set()
    for _, g in d.groupby(["league", "date", "home_goals", "away_goals"], sort=False):
        if len(g) < 2:
            continue
        idx = list(g.index)
        for a_i, a in enumerate(idx):
            if a in drop:
                continue
            for b in idx[a_i + 1:]:
                if b not in drop and common.same_club(d.at[a, "home_team"], d.at[b, "home_team"]) \
                        and common.same_club(d.at[a, "away_team"], d.at[b, "away_team"]):
                    drop.add(b)
    return d.drop(index=sorted(drop)).reset_index(drop=True), len(drop)


def _frame() -> pd.DataFrame:
    """v9's own O/U training frame (v9 loader + feature builder), de-duplicated (see above)."""
    p = EXP / "v9_frame_dedup.parquet"
    if p.exists():
        return pd.read_parquet(p)
    fr = pd.read_parquet(EXP / "v9_frame.parquet")
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    out, n = dedup_alias_matches(fr)
    out.to_parquet(p, index=False)
    (EXP / "dedup.json").write_text(json.dumps({"rows_before": len(fr), "duplicates_dropped": n}),
                                    encoding="utf-8")
    return out


def _player_history() -> pd.DataFrame:
    cols = ["fixture_id", "player_id", "date", "league", "team", "minutes", "goals", "assists"]
    d = pd.read_parquet(Path(cfg.V9_LOCAL) / "player_history.parquet", columns=cols)
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    return d.dropna(subset=["date", "player_id"])


def _importance(ph: pd.DataFrame, inj: pd.DataFrame) -> pd.DataFrame:
    """Per (fixture, team, player listed): the player's share of team minutes and of team goals +
    assists over the team's LOOKBACK matches strictly BEFORE the fixture date. As-of by construction."""
    ph = ph.copy()
    ph["ga"] = ph["goals"].fillna(0) + ph["assists"].fillna(0)
    tm = (ph.groupby(["team", "fixture_id", "date"], as_index=False)
            .agg(team_minutes=("minutes", "sum"), team_goals=("goals", "sum")))
    out = []
    by_team = {t: g.sort_values("date") for t, g in tm.groupby("team")}
    by_tp = {k: g for k, g in ph.groupby(["team", "player_id"])}
    for r in inj.itertuples(index=False):
        g = by_team.get(r.ph_team)
        if g is None:
            out.append((np.nan, np.nan))
            continue
        prev = g[g["date"] < r.fx_date].tail(LOOKBACK)
        if prev.empty:
            out.append((np.nan, np.nan))
            continue
        p = by_tp.get((r.ph_team, r.player_id))
        pm = p[p["fixture_id"].isin(prev["fixture_id"])] if p is not None else None
        mins = float(pm["minutes"].sum()) if pm is not None else 0.0
        ga = float(pm["ga"].sum()) if pm is not None else 0.0
        out.append((mins / max(1.0, prev["team_minutes"].sum()) * 11,   # ~= share of a starting slot
                    ga / max(1.0, prev["team_goals"].sum())))
    inj = inj.copy()
    inj["min_share"], inj["ga_share"] = zip(*out) if out else ([], [])
    return inj


def features() -> dict:
    """Injury inputs per v9 fixture row, home and away. NaN where the league-season is not covered."""
    inj = pd.read_parquet(EXP / "injuries.parquet")
    afx = pd.read_parquet(EXP / "af_fixtures.parquet")
    cov = pd.read_csv(EXP / "injury_coverage.csv")
    covered = set(map(tuple, cov.loc[cov["injury_rows"] >= MIN_ROWS_COVERED, ["league", "season"]].values))
    afx = afx[[(l, s) in covered for l, s in zip(afx["league"], afx["season"])]].copy()
    afx["fx_date"] = pd.to_datetime(afx["fixture_ts"], utc=True).dt.tz_localize(None).dt.normalize()

    fr = _frame()
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    fr = fr.reset_index(drop=True)
    leagues = sorted({l for l, _ in covered})
    sub = fr[fr["league"].isin(leagues) & (fr["date"] >= afx["fx_date"].min() - pd.Timedelta(days=2))]
    afx_m = afx.rename(columns={"fx_date": "match_date"}).reset_index(drop=True)
    idx = common.match_frames(sub.rename(columns={"date": "match_date"}), afx_m)
    fr["af_fixture_id"] = np.nan
    ok = idx.dropna().astype(int)
    fr.loc[ok.index, "af_fixture_id"] = afx_m.loc[ok.values, "af_fixture_id"].values
    # one AF fixture may match two v9 rows only through a name bug — drop both rather than guess
    dup = fr["af_fixture_id"].notna() & fr["af_fixture_id"].duplicated(keep=False)
    fr.loc[dup, "af_fixture_id"] = np.nan
    j = fr.dropna(subset=["af_fixture_id"]).merge(
        afx[["af_fixture_id", "home_id", "away_id", "home_team", "away_team", "hg", "ag", "fx_date"]]
        .rename(columns={"home_team": "af_home", "away_team": "af_away"}), on="af_fixture_id", how="left")

    # injuries -> fixture side, weights from player history (club names via AF ids in player_history)
    ph = _player_history()
    i = inj.merge(afx[["af_fixture_id", "home_id", "away_id", "home_team", "away_team", "fx_date"]],
                  on="af_fixture_id", how="inner")
    i = i.drop_duplicates(["af_fixture_id", "player_id", "team_id"])
    i["side"] = np.where(i["team_id"] == i["home_id"], "home",
                         np.where(i["team_id"] == i["away_id"], "away", None))
    i = i[i["side"].notna()]
    # player_history names clubs by API-Football name: same source as the injury list
    i["ph_team"] = i["team"]
    i = _importance(ph, i)
    i["is_missing"] = (i["type"] == "Missing Fixture").astype(int)
    i["is_q"] = (i["type"] == "Questionable").astype(int)
    miss = i[i["is_missing"] == 1]
    agg = (i.groupby(["af_fixture_id", "side"])
             .agg(inj_n_missing=("is_missing", "sum"), inj_n_questionable=("is_q", "sum")).reset_index())
    w = (miss.groupby(["af_fixture_id", "side"])
             .agg(inj_minutes_share=("min_share", "sum"), inj_goal_share=("ga_share", "sum")).reset_index())
    agg = agg.merge(w, on=["af_fixture_id", "side"], how="left")
    wide = agg.pivot(index="af_fixture_id", columns="side", values=INJ_COLS)
    wide.columns = [f"{s}_{c}" for c, s in wide.columns]
    wide = wide.reset_index()
    out = j.merge(wide, on="af_fixture_id", how="left")
    # a covered fixture with no listed absentee is a real zero, not missing data
    for c in [f"{s}_{x}" for s in ("home", "away") for x in INJ_COLS]:
        if c not in out.columns:
            out[c] = 0.0
        out[c] = out[c].fillna(0.0)
    out["total_inj_minutes_share"] = out["home_inj_minutes_share"] + out["away_inj_minutes_share"]
    out["total_inj_goal_share"] = out["home_inj_goal_share"] + out["away_inj_goal_share"]
    keep = ["league", "date", "home_team", "away_team", "af_fixture_id", "hg", "ag", "af_home", "af_away"] + \
           [c for c in out.columns if "inj_" in c]
    out[keep].to_parquet(EXP / "injury_features.parquet", index=False)
    return {"v9_rows": len(fr), "rows_in_covered_leagues": int(len(sub)),
            "joined_to_af_fixture": int(len(j)),
            "join_rate": round(len(j) / max(1, len(sub)), 4),
            "covered_league_seasons": len(covered), "covered_leagues": leagues}


def audit() -> dict:
    """Bugs and wrong data, before any model is trained (owner: check 100 times)."""
    f = pd.read_parquet(EXP / "injury_features.parquet")
    fr = _frame()
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    m = f.merge(fr[["league", "date", "home_team", "away_team", "over25"]],
                on=["league", "date", "home_team", "away_team"], how="left")
    goals_ok = ((m["hg"] + m["ag"] > 2.5).astype(float) == m["over25"]).mean()
    inj = pd.read_parquet(EXP / "injuries.parquet")
    ph = _player_history()
    played = ph[ph["minutes"].fillna(0) > 0][["fixture_id", "player_id"]].drop_duplicates()
    played["played"] = 1
    x = inj.merge(played, left_on=["af_fixture_id", "player_id"], right_on=["fixture_id", "player_id"],
                  how="left")
    x["played"] = x["played"].fillna(0)
    in_ph = inj["af_fixture_id"].isin(set(ph["fixture_id"]))
    xx = x[in_ph.values]
    res = {
        "join_goal_agreement": round(float(goals_ok), 4),
        "duplicate_listings": int(inj.duplicated(["af_fixture_id", "player_id"]).sum()),
        # HINDSIGHT TEST. If lists were written after the match, 'Missing Fixture' players would never
        # have played and 'Questionable' would mirror the outcome. A pre-match list shows some
        # Questionable players playing and almost no Missing ones playing.
        "missing_listed_but_played": round(float(xx.loc[xx["type"] == "Missing Fixture", "played"].mean()), 4),
        "questionable_listed_and_played": round(float(xx.loc[xx["type"] == "Questionable", "played"].mean()), 4),
        "listings_checkable_in_player_history": int(in_ph.sum()),
    }
    # live-vs-history: Pro's own pre-kickoff team_news injury counts vs the historical endpoint today
    try:
        tn = pd.read_parquet(cfg.BASE_DIR / "data" / "season_2026_27" / "team_news")
        tn = tn[tn["minutes_to_kickoff"].astype(float) > 0]
        tn = tn.sort_values("first_seen_ts").drop_duplicates(["fixture_id", "team"], keep="last")
        hist = inj.groupby(["af_fixture_id", "team"]).size().rename("hist_n").reset_index()
        c = tn.merge(hist, left_on=["fixture_id", "team"], right_on=["af_fixture_id", "team"], how="inner")
        res["live_vs_history_pairs"] = int(len(c))
        if len(c) >= 10:
            res["live_vs_history_corr"] = round(float(np.corrcoef(c["injuries_n"].astype(float), c["hist_n"])[0, 1]), 3)
            res["history_minus_live_mean"] = round(float((c["hist_n"] - c["injuries_n"].astype(float)).mean()), 3)
    except Exception as e:                                             # noqa: BLE001
        res["live_vs_history"] = f"unavailable: {e}"
    res["feature_ranges"] = {c: [round(float(f[c].min()), 3), round(float(f[c].quantile(.5)), 3),
                                 round(float(f[c].max()), 3)] for c in f.columns if "inj_" in c}
    (EXP / "audit.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


#: PRE-REGISTERED 2026-10-19, before any result was seen. Injuries "help" only if, on covered
#: fixtures, log loss falls by at least MATERIAL with a 90% day-block CI entirely below zero. Even then
#: the verdict is an UPPER BOUND until the prospective list-revision check (`forward`) is clean.
MATERIAL = 0.001


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def report() -> dict:
    r = pd.read_parquet(EXP / "eval_rows.parquet")
    r = r[r["over25"].notna()]
    out = {"pre_registered_rule": f"delta <= -{MATERIAL} and 90% CI upper < 0 on covered fixtures",
           "tracks": {}}
    rows = []
    for track, g in r.groupby("track"):
        for scope, s in (("covered", g[g["inj_covered"] == 1]), ("all", g)):
            if len(s) < 100:
                continue
            dl = _ll(s["p_inj"], s["over25"]) - _ll(s["p_base"], s["over25"])
            ci = common.block_ci(dl, s["date"].astype(str).to_numpy())
            mk = {}
            if {"odds_over25", "odds_under25"} <= set(s.columns):
                o, u = pd.to_numeric(s["odds_over25"], errors="coerce"), pd.to_numeric(s["odds_under25"], errors="coerce")
                ok = (o > 1) & (u > 1)
                pm = (1 / o) / (1 / o + 1 / u)
                if ok.sum() >= 100:
                    mk = {"n_priced": int(ok.sum()),
                          "ll_market": round(float(_ll(pm[ok], s.loc[ok, "over25"]).mean()), 5),
                          "ll_base_priced": round(float(_ll(s.loc[ok, "p_base"], s.loc[ok, "over25"]).mean()), 5),
                          "ll_inj_priced": round(float(_ll(s.loc[ok, "p_inj"], s.loc[ok, "over25"]).mean()), 5)}
            rec = {"track": track, "scope": scope, "n": int(len(s)),
                   "ll_base": round(float(_ll(s["p_base"], s["over25"]).mean()), 5),
                   "ll_inj": round(float(_ll(s["p_inj"], s["over25"]).mean()), 5),
                   "delta": round(float(dl.mean()), 5), "ci90": [round(float(x), 5) for x in ci],
                   "brier_delta": round(float(((s["p_inj"] - s["over25"]) ** 2).mean()
                                              - ((s["p_base"] - s["over25"]) ** 2).mean()), 5),
                   "spread_base": round(float(s["p_base"].std()), 4),
                   "spread_inj": round(float(s["p_inj"].std()), 4), **mk}
            if scope == "covered":
                rec["verdict"] = ("HELPS (upper bound — prospective check pending)"
                                  if rec["delta"] <= -MATERIAL and ci[1] < 0 else
                                  "HURTS" if ci[0] > 0 else "NO MEASURABLE EFFECT")
            rows.append(rec)
        cov = g[g["inj_covered"] == 1]
        for lg, s in cov.groupby("league"):
            if len(s) < 150:
                continue
            dl = _ll(s["p_inj"], s["over25"]) - _ll(s["p_base"], s["over25"])
            rows.append({"track": track, "scope": f"league:{lg}", "n": int(len(s)),
                         "delta": round(float(dl.mean()), 5),
                         "ci90": [round(float(x), 5) for x in common.block_ci(dl, s["date"].astype(str).to_numpy())]})
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "ou_info_inputs.csv", index=False)
    out["results"] = rows
    out["audit"] = json.loads((EXP / "audit.json").read_text(encoding="utf-8")) if (EXP / "audit.json").exists() else {}
    out["dedup"] = json.loads((EXP / "dedup.json").read_text(encoding="utf-8")) if (EXP / "dedup.json").exists() else {}
    out["generated_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    common.write("ou_info_inputs", out)
    return out


# ── lineups (history: one /fixtures/lineups call per finished fixture) ──────────────────────────
LINEUP_FROM = "2023-07-01"
LINEUP_CACHE = EXP / "lineups"


def fetch_lineups(max_calls: int = 32000, workers: int = 6) -> dict:
    """Starting XI + formation for every finished fixture since LINEUP_FROM in our leagues.

    A lineup is published ~1h before kickoff and never revised, so — unlike injury lists — it has no
    hindsight risk. Budget: capped per run (`max_calls`), cached per fixture forever, resumable.
    Production uses ~10-14k/day of a 75k/day plan; this stays inside the remaining headroom."""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    LINEUP_CACHE.mkdir(parents=True, exist_ok=True)
    afx = pd.read_parquet(EXP / "af_fixtures.parquet")
    afx = afx[afx["status"].isin(["FT", "AET", "PEN"])]
    afx = afx[pd.to_datetime(afx["fixture_ts"], utc=True) >= pd.Timestamp(LINEUP_FROM, tz="UTC")]
    todo = [int(f) for f in afx["af_fixture_id"] if not (LINEUP_CACHE / f"{int(f)}.json").exists()][:max_calls]
    key = common._af_key()

    def one(fid):
        for attempt in range(3):
            try:
                b = requests.get(f"{AF}/fixtures/lineups", headers={"x-apisports-key": key},
                                 params={"fixture": fid}, timeout=60).json()
                if b.get("errors"):
                    if "rateLimit" in str(b["errors"]) or "requests" in str(b["errors"]).lower():
                        time.sleep(5 + 5 * attempt)
                        continue
                    return "error"
                (LINEUP_CACHE / f"{fid}.json").write_text(json.dumps(b.get("response", [])), encoding="utf-8")
                return "ok" if b.get("response") else "empty"
            except Exception:                                          # noqa: BLE001
                time.sleep(3)
        return "error"
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, todo))
    from collections import Counter
    return {"fixtures_in_scope": int(len(afx)), "requested": len(todo), **Counter(res)}


# ── price movement (football-data raw files: opening AND closing O/U 2.5 prices) ─────────────────
FD_SEASONS = ("2223", "2324", "2425", "2526", "2627")


def _fd_codes() -> dict[str, str]:
    import ast
    src = (Path(cfg.V9_LOCAL) / "config.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "FOOTBALL_DATA_LEAGUES":
            return ast.literal_eval(node.value)
    return {}


def movement_features() -> dict:
    """Per standard-league match: de-vigged P(over 2.5) at the OPENING average price, at the CLOSING
    average price, and the move between them. Opening is known when v9 first tips; the close only
    near kickoff — so `p_open` is an EARLY input and `move` / `p_close` are LATE inputs."""
    import io
    import requests
    from src.data.entities import norm_name  # noqa: F401  (kept for parity with other modules)
    rows = []
    calls = 0
    cache = EXP / "fd_raw"
    cache.mkdir(parents=True, exist_ok=True)
    for lg, code in _fd_codes().items():
        if not isinstance(code, str) or len(code) > 3:
            continue
        for s in FD_SEASONS:
            f = cache / f"{code}_{s}.csv"
            if not f.exists():
                # files normally arrive via pro_fd_raw_fetch.yml (this laptop's network blocks the site)
                try:
                    r = requests.get(f"https://www.football-data.co.uk/mmz4281/{s}/{code}.csv", timeout=60)
                except Exception:                                      # noqa: BLE001
                    continue
                calls += 1
                if r.status_code != 200 or b"Date" not in r.content[:200]:
                    continue
                f.write_bytes(r.content)
                time.sleep(0.3)
            try:
                d = pd.read_csv(f, encoding="latin-1", on_bad_lines="skip")
            except Exception:                                          # noqa: BLE001
                continue
            need = {"Avg>2.5", "Avg<2.5", "AvgC>2.5", "AvgC<2.5", "HomeTeam", "AwayTeam", "Date"}
            if not need <= set(d.columns):
                continue
            d = d.dropna(subset=["HomeTeam", "AwayTeam"])

            def devig(o, u):
                o, u = pd.to_numeric(o, errors="coerce"), pd.to_numeric(u, errors="coerce")
                return (1 / o) / (1 / o + 1 / u)
            po, pc = devig(d["Avg>2.5"], d["Avg<2.5"]), devig(d["AvgC>2.5"], d["AvgC<2.5"])
            rows.append(pd.DataFrame({"league": lg, "match_date": pd.to_datetime(d["Date"], dayfirst=True,
                                                                                 errors="coerce"),
                                      "home_team": d["HomeTeam"].values, "away_team": d["AwayTeam"].values,
                                      "p_open": po.values, "p_close": pc.values,
                                      "move": (pc - po).values}))
    mv = pd.concat(rows, ignore_index=True).dropna(subset=["match_date"])
    mv = mv[(mv["p_open"].between(0.05, 0.95)) & (mv["p_close"].between(0.05, 0.95))].reset_index(drop=True)
    fr = _frame()
    fr = fr[fr["track"] == "standard"].reset_index(drop=True)
    fr["match_date"] = pd.to_datetime(fr["date"]).dt.normalize()
    # fast path: exact names (v9's standard rows come from these same files), then fuzzy for the rest
    k = ["league", "match_date", "home_team", "away_team"]
    m = fr[k].merge(mv, on=k, how="left")
    miss = m["p_open"].isna()
    if miss.any():
        idx = common.match_frames(fr.loc[miss.values, k], mv, day_tol=1)
        ok = idx.dropna().astype(int)
        for c in ("p_open", "p_close", "move"):
            m.loc[ok.index, c] = mv.loc[ok.values, c].values
    out = m.rename(columns={"match_date": "date"})[["league", "date", "home_team", "away_team",
                                                    "p_open", "p_close", "move"]]
    out.to_parquet(EXP / "movement_features.parquet", index=False)
    res = {"fd_files_downloaded": calls, "fd_rows": len(mv), "standard_rows": len(fr),
           "matched": int(out["p_open"].notna().sum()),
           "match_rate": round(float(out["p_open"].notna().mean()), 4),
           "move_abs_mean_pp": round(float(out["move"].abs().mean() * 100), 3),
           "open_close_corr": round(float(out[["p_open", "p_close"]].corr().iloc[0, 1]), 4)}
    (EXP / "movement_audit.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


# ── prospective leak check ──────────────────────────────────────────────────────────────────────
SNAP = OUT / "injury_snapshots.parquet"
FORWARD_LEAGUES = ("Championship", "Denmark Superliga", "Norway Eliteserien", "Sweden Allsvenskan",
                   "Brazil Serie A", "League One")


def forward() -> dict:
    """Capture API-Football's CURRENT injury list for every not-yet-played fixture in the covered
    bet leagues, stamped with capture time. One live call per league; never cached. Comparing these
    pre-kickoff lists with the same fixtures' lists after full time is the only way to know whether
    the historical lists were revised with hindsight — history alone cannot tell."""
    import requests
    ids = _league_ids()
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for lg in FORWARD_LEAGUES:
        lid = ids.get(lg)
        if lid is None:
            continue
        season = 2026
        body = requests.get(f"{AF}/injuries", headers={"x-apisports-key": common._af_key()},
                            params={"league": lid, "season": season}, timeout=90).json()
        for x in body.get("response", []):
            ts = pd.to_datetime((x.get("fixture") or {}).get("date"), utc=True, errors="coerce")
            rows.append({"captured_at": now, "league": lg, "af_fixture_id": (x.get("fixture") or {}).get("id"),
                         "fixture_ts": ts, "team_id": (x.get("team") or {}).get("id"),
                         "player_id": (x.get("player") or {}).get("id"),
                         "type": (x.get("player") or {}).get("type"),
                         "pre_kickoff": bool(pd.notna(ts) and ts > now)})
        time.sleep(0.2)
    new = pd.DataFrame(rows)
    old = pd.read_parquet(SNAP) if SNAP.exists() else pd.DataFrame()
    allr = pd.concat([old, new], ignore_index=True) if len(old) else new
    # keep: every pre-kickoff observation + the LATEST post-kickoff one per fixture (the "final" list)
    pre = allr[allr["pre_kickoff"]]
    post = allr[~allr["pre_kickoff"]]
    if len(post):
        last = post.groupby("af_fixture_id")["captured_at"].transform("max")
        post = post[post["captured_at"] == last]
    keep = pd.concat([pre, post], ignore_index=True).drop_duplicates(
        ["captured_at", "af_fixture_id", "player_id", "type"])
    OUT.mkdir(parents=True, exist_ok=True)
    keep.to_parquet(SNAP, index=False)
    return {"captured": len(new), "pre_kickoff_rows": int(new["pre_kickoff"].sum()) if len(new) else 0,
            "snapshot_rows": len(keep)}


def forward_check() -> dict:
    """For fixtures seen BOTH before kickoff and after full time: how much did the list change?"""
    if not SNAP.exists():
        return {"status": "no snapshots yet"}
    s = pd.read_parquet(SNAP)
    pre = s[s["pre_kickoff"]].sort_values("captured_at").groupby("af_fixture_id")
    last_pre = {k: set(map(tuple, g[g["captured_at"] == g["captured_at"].max()][["player_id", "type"]].values))
                for k, g in pre}
    post = {k: set(map(tuple, g[["player_id", "type"]].values)) for k, g in s[~s["pre_kickoff"]].groupby("af_fixture_id")}
    both = sorted(set(last_pre) & set(post))
    added = sum(len(post[k] - last_pre[k]) for k in both)
    removed = sum(len(last_pre[k] - post[k]) for k in both)
    total_post = sum(len(post[k]) for k in both)
    res = {"fixtures_compared": len(both), "post_listings": total_post,
           "added_after_kickoff": added, "removed_after_kickoff": removed,
           "share_of_final_list_added_after_kickoff": round(added / total_post, 3) if total_post else None,
           "verdict": ("INSUFFICIENT (< 50 fixtures)" if len(both) < 50 else
                       "CLEAN — historical lists match pre-kickoff lists" if total_post and added / total_post < 0.05
                       else "REVISED — historical lists contain hindsight; history backtest is an upper bound only")}
    common.write("ou_info_inputs_forward_check", res)
    return res


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    fn = {"fetch": fetch, "features": features, "audit": audit, "report": report,
          "forward": forward, "forward_check": forward_check, "fetch_lineups": fetch_lineups,
          "movement": movement_features}[step]
    print(json.dumps(fn(), indent=2, default=str))
