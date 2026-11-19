"""
The 1X2 model's ONE door into v9's repaired data (owner 2026-11-09). Runs INSIDE v9's environment.

    python src/pipelines/onex2_v9_bridge.py history  <v9_root> <out_dir> <fd_raw_dir>
    python src/pipelines/onex2_v9_bridge.py upcoming <v9_root> <fixtures_csv> <out_dir>

Executed as a SCRIPT with v9's root first on sys.path, so `src` is v9's package, never Pro's (Pro
calls it through a subprocess; nothing in Pro imports it).

Both modes load v9's served match frame from the COMMITTED data, offline: the football-data download
is switched off and the network is blocked, every loader correction applies, COVID seasons are
excluded. The SAME src.feature_engineering.build_features makes the training features and the
serving features:

  history   matches.parquet, features.parquet, prices.parquet (real 1X2 prices joined through v9's
            league-scoped resolver: football-data pre-match / closing / Bet365, and the v9 sharp
            tracker's opening and last pre-kickoff h2h snapshot), meta.json
  upcoming  upcoming_features.parquet: the fixtures of <fixtures_csv> (fixture_key, league - v9
            canonical name -, kickoff_utc, home_team, away_team) appended to the history WITHOUT a
            result and passed through build_features, so a fixture gets exactly the pre-match
            features training uses (checked: a played match blanked to 'upcoming' gets identical
            features, 0 of 43 columns differ). matches.parquet (the history, for Elo), meta.json.

Nothing is guessed. A club no provable rule places in the league's history pool is not served
(reason name_unresolved); a club with an EARLIER fixture still pending in the same file is not
served (reason earlier_fixture_pending: its form would have to assume a result).

meta.json carries `feature_fingerprint` = sha256 of v9's src/feature_engineering.py plus the
feature list. A model trained under one fingerprint refuses to serve under another.
"""
from __future__ import annotations

import glob
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

RESULT_COLS = ("home_goals", "away_goals", "ftr", "total_goals", "over25", "over15", "over35", "btts",
               "home_shots", "away_shots", "home_sot", "away_sot", "home_corners", "away_corners",
               "home_fouls", "away_fouls", "ht_home_goals", "ht_away_goals", "ht_total_goals",
               "ht_over05", "ht_over15", "home_xg", "away_xg", "home_insidebox", "away_insidebox",
               "home_yellows", "away_yellows", "home_sot_ratio", "away_sot_ratio")


def _block_network() -> None:
    import socket

    def _no_net(*a, **k):
        raise OSError("network blocked (onex2 bridge reads committed v9 data only)")
    socket.socket.connect = _no_net
    socket.create_connection = _no_net


def _load(v9_root: str):
    sys.path.insert(0, v9_root)
    import os
    os.chdir(v9_root)
    import pandas as pd
    _block_network()
    import config
    from src import data_loader as DL
    DL._ci_download_all = lambda have=None: []
    DL._report_training_coverage = lambda out: None
    raw = DL.load_all_matches(force=True)
    covid = config.covid_season_mask(raw)
    raw = raw[~covid].copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    raw = raw.dropna(subset=["home_goals", "away_goals"])
    raw["row_id"] = _row_ids(raw)
    dup = int(raw["row_id"].duplicated().sum())
    raw = raw.drop_duplicates("row_id", keep="first")
    cfg = json.loads((Path(v9_root) / "config" / "phase2_retrain.json").read_text(encoding="utf-8"))
    f = cfg["features"]
    never = set(f.get("never_model_inputs") or [])
    cols = [c for g in f["groups"].values() if g.get("include") for c in g.get("columns", [])
            if c not in never]
    fe = (Path(v9_root) / "src" / "feature_engineering.py").read_bytes()
    fp = hashlib.sha256(fe + json.dumps(cols).encode("utf-8")).hexdigest()[:16]
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=v9_root, capture_output=True,
                         text=True).stdout.strip()
    meta = {"v9_commit": sha, "feature_fingerprint": fp, "feature_columns": cols,
            "require_present": list(cfg["data"].get("require_present") or []),
            "matches": int(len(raw)), "covid_rows_excluded": int(covid.sum()),
            "duplicate_row_ids_dropped": dup}
    return raw, meta, DL


#: closing columns of football-data's new-format files, in preference order (average first, as for
#: the main files' FD_CLOSE)
NEWFMT_CLOSE_PREFS = ("AvgC", "PSC", "B365C", "MaxC")


def newfmt_close_rows(df) -> list[dict]:
    """Closing 1X2 triples of a football-data /new/ file: {date, home, away, book, o}. A row
    without one complete real triple (all three > 1) yields nothing; nothing is filled."""
    import pandas as pd
    if not {"Date", "Home", "Away"} <= set(df.columns):
        return []
    out = []
    dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce").dt.normalize()
    for i, x in df.iterrows():
        d = dates.loc[i]
        if pd.isna(d) or pd.isna(x["Home"]) or pd.isna(x["Away"]):
            continue
        for p in NEWFMT_CLOSE_PREFS:
            o = [pd.to_numeric(x.get(p + s), errors="coerce") for s in ("H", "D", "A")]
            if all(pd.notna(v) and v > 1.0 for v in o):
                out.append({"date": d, "home": str(x["Home"]), "away": str(x["Away"]), "book": p,
                            "o": [float(v) for v in o]})
                break
    return out


def _row_ids(d):
    return (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"].astype(str) + "|"
            + d["home_team"].astype(str) + "|" + d["away_team"].astype(str))


def _pools(raw):
    return {lg: sorted(set(g["home_team"].astype(str)) | set(g["away_team"].astype(str)))
            for lg, g in raw.groupby("league")}


def history(v9_root: str, out_dir: str, fd_raw: str) -> int:
    raw, meta, DL = _load(v9_root)
    import pandas as pd
    from src.feature_engineering import build_features
    from src.standard_repair import FD_CODES, frame_hash
    from src.team_names import resolve
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(out / "matches.parquet")
    feat = build_features(raw)
    feat["date"] = pd.to_datetime(feat["date"]).dt.normalize()
    feat["row_id"] = _row_ids(feat)
    feat = feat.drop_duplicates("row_id", keep="first")
    feat.to_parquet(out / "features.parquet")

    pools = _pools(raw)
    cache: dict = {}

    def canon(lg, name):
        pool = pools.get(lg)
        if not pool:
            return None
        if name in pool:
            return name
        k = (lg, name)
        if k not in cache:
            try:
                cache[k] = resolve(name, pool)
            except Exception:                                        # noqa: BLE001
                cache[k] = None
        return cache[k]

    index = {}
    for lg, g in raw.groupby("league"):
        for d, h, a, rid in zip(g["date"], g["home_team"].astype(str), g["away_team"].astype(str),
                                g["row_id"]):
            index[(lg, d, h, a)] = rid

    def find(lg, day, h, a):
        """Same league, both names resolved, date equal or one day apart. Exactly one or nothing."""
        ch, ca = canon(lg, h), canon(lg, a)
        if ch is None or ca is None:
            return None, "name_unresolved"
        hits = [index[k] for k in ((lg, day + pd.Timedelta(days=o), ch, ca) for o in (0, -1, 1))
                if k in index]
        if len(hits) != 1:
            return None, ("no_match_on_date" if not hits else "ambiguous_date")
        return hits[0], "ok"

    rows, stats = [], {}

    def note(src, lg, why):
        stats.setdefault(src, {}).setdefault(lg, Counter())[why] += 1

    inv = {v: k for k, v in FD_CODES.items()}
    for f in sorted(glob.glob(str(Path(fd_raw) / "*_*.csv"))):
        code = Path(f).stem.rsplit("_", 1)[0]
        lg = inv.get(code)
        if lg is None:
            continue
        try:
            r = pd.read_csv(f, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
        except UnicodeDecodeError:
            r = pd.read_csv(f, encoding="cp1252", encoding_errors="replace", on_bad_lines="skip",
                            low_memory=False)
        if not {"Date", "HomeTeam", "AwayTeam"} <= set(r.columns):
            continue
        r = r.assign(_d=pd.to_datetime(r["Date"], dayfirst=True, errors="coerce").dt.normalize())
        for _, x in r.dropna(subset=["_d", "HomeTeam", "AwayTeam"]).iterrows():
            rid, why = find(lg, x["_d"], str(x["HomeTeam"]), str(x["AwayTeam"]))
            note("FD", lg, why)
            if rid is None:
                continue
            for cls, prefs in (("FD_ENTRY", ("Avg", "B365", "PS")),
                               ("FD_CLOSE", ("AvgC", "B365C", "PSC"))):
                for p in prefs:
                    o = [pd.to_numeric(x.get(p + s), errors="coerce") for s in ("H", "D", "A")]
                    if all(pd.notna(v) and v > 1.0 for v in o):
                        rows.append({"row_id": rid, "source": "football-data", "class": cls,
                                     "book": p, "o_home": o[0], "o_draw": o[1], "o_away": o[2],
                                     "price_at": None, "file": Path(f).name})
                        break
            o = [pd.to_numeric(x.get("B365" + s), errors="coerce") for s in ("H", "D", "A")]
            if all(pd.notna(v) and v > 1.0 for v in o):
                rows.append({"row_id": rid, "source": "football-data", "class": "FD_BET365_ENTRY",
                             "book": "B365", "o_home": o[0], "o_draw": o[1], "o_away": o[2],
                             "price_at": None, "file": Path(f).name})

    # football-data NEW-FORMAT files (<CODE>_new.csv, e.g. ROM_new.csv for Romania): CLOSING prices
    # only - a benchmark, never a bettable price (owner 2026-11-09). The league comes from v9's
    # registry (football_data_code + football_data_format "new"), never from the file name alone.
    reg = json.loads((Path(v9_root) / "config" / "leagues.json").read_text(encoding="utf-8"))["leagues"]
    newfmt = {v["football_data_code"]: v["name"] for v in reg
              if v.get("football_data_format") == "new" and v.get("football_data_code")}
    for f in sorted(glob.glob(str(Path(fd_raw) / "*_new.csv"))):
        lg = newfmt.get(Path(f).stem[:-len("_new")])
        if lg is None or lg not in pools:
            continue
        try:
            r = pd.read_csv(f, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
        except UnicodeDecodeError:
            r = pd.read_csv(f, encoding="cp1252", encoding_errors="replace", on_bad_lines="skip",
                            low_memory=False)
        for x in newfmt_close_rows(r):
            rid, why = find(lg, x["date"], x["home"], x["away"])
            note("FD_NEW", lg, why)
            if rid is None:
                continue
            rows.append({"row_id": rid, "source": "football-data new-format (closing only)",
                         "class": "FD_CLOSE", "book": x["book"], "o_home": x["o"][0],
                         "o_draw": x["o"][1], "o_away": x["o"][2], "price_at": None,
                         "file": Path(f).name, "closing_only": True})

    for f in sorted(glob.glob(str(Path(v9_root) / "output" / "sharp_history" / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for v in (d.values() if isinstance(d, dict) else d):
            for s in (v if isinstance(v, list) else [v]):
                if not isinstance(s, dict) or s.get("market") != "h2h":
                    continue
                lg = s.get("league")
                ko = pd.to_datetime(str(s.get("date")), errors="coerce")
                if lg not in pools or pd.isna(ko):
                    note("SHARP", str(lg), "league_or_kickoff_unknown")
                    continue
                rid, why = find(lg, ko.normalize(), str(s.get("home")), str(s.get("away")))
                note("SHARP", lg, why)
                if rid is None:
                    continue
                snaps = []
                for sn in (s.get("snapshots") or []):
                    at = pd.to_datetime(str(sn.get("at")), errors="coerce")
                    o = sn.get("odds") or {}
                    oo = [o.get("odds_home"), o.get("odds_draw"), o.get("odds_away")]
                    if pd.isna(at) or at >= ko or not all(isinstance(z, (int, float)) and z > 1.0
                                                         for z in oo):
                        continue
                    snaps.append((at, oo))
                if not snaps:
                    continue
                snaps.sort(key=lambda t: t[0])
                for cls, (at, oo) in (("SHARP_OPEN", snaps[0]), ("SHARP_CLOSE", snaps[-1])):
                    rows.append({"row_id": rid, "source": "v9 sharp_history", "class": cls,
                                 "book": "sharp_tracker", "o_home": float(oo[0]),
                                 "o_draw": float(oo[1]), "o_away": float(oo[2]),
                                 "price_at": at.strftime("%Y-%m-%d %H:%M"), "file": Path(f).name})

    prices = pd.DataFrame(rows).drop_duplicates(["row_id", "class"], keep="first")
    prices.to_parquet(out / "prices.parquet")
    meta.update({"frame_hash": frame_hash(raw), "feature_rows": int(len(feat)),
                 "prices_by_class": prices["class"].value_counts().to_dict() if len(prices) else {},
                 "join": stats})
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    (out / "extract.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k not in ("join", "feature_columns")},
                     default=str))
    return 0


def upcoming(v9_root: str, fixtures_csv: str, out_dir: str) -> int:
    raw, meta, DL = _load(v9_root)
    import numpy as np
    import pandas as pd
    from src.feature_engineering import build_features
    from src.standard_repair import frame_hash
    from src.team_names import resolve_identity
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fx = pd.read_csv(fixtures_csv, dtype=str)
    fx["_ko"] = pd.to_datetime(fx["kickoff_utc"], utc=True, errors="coerce")
    pools = _pools(raw)
    aliases = getattr(DL, "IDENTITY_ALIASES", {}) or {}
    reasons: Counter = Counter()
    rows = []
    for _, f in fx.sort_values("_ko").iterrows():
        lg = f["league"]
        pool = pools.get(lg)
        if not pool or pd.isna(f["_ko"]):
            reasons["league_not_in_history" if not pool else "kickoff_unknown"] += 1
            continue
        h = resolve_identity(str(f["home_team"]), pool, aliases.get(lg))
        a = resolve_identity(str(f["away_team"]), pool, aliases.get(lg))
        if h is None or a is None:
            reasons["name_unresolved"] += 1
            continue
        rows.append({"fixture_key": f["fixture_key"], "league": lg,
                     "date": f["_ko"].tz_convert(None).normalize(), "home_team": h, "away_team": a,
                     "kickoff_utc": f["kickoff_utc"]})
    up = pd.DataFrame(rows)
    if len(up):
        # a club with an earlier fixture still pending: its form for the later one would need a
        # result that does not exist yet -> not served
        seen, keep = set(), []
        for _, r in up.sort_values("date").iterrows():
            k1, k2 = (r["league"], r["home_team"]), (r["league"], r["away_team"])
            keep.append(not (k1 in seen or k2 in seen))
            seen.update([k1, k2])
        up = up.sort_values("date")
        reasons["earlier_fixture_pending"] += int((~np.array(keep)).sum())
        up = up[np.array(keep)]
        # a fixture whose result is already in the history (same clubs, within a day) is not upcoming
        played = set(zip(raw["league"], raw["home_team"], raw["away_team"], raw["date"]))
        done = np.array([any((lg, h, a, d + pd.Timedelta(days=o)) in played for o in (-1, 0, 1))
                         for lg, h, a, d in zip(up["league"], up["home_team"], up["away_team"], up["date"])],
                        dtype=bool)
        reasons["already_in_history"] += int(done.sum())
        up = up[~done]
    feats = pd.DataFrame()
    if len(up):
        app = up[["league", "date", "home_team", "away_team"]].copy()
        for c in raw.columns:
            if c not in app.columns:
                app[c] = np.nan if c in RESULT_COLS or c not in ("season", "row_source") else None
        app["row_source"] = "upcoming"
        app["season"] = raw["season"].iloc[-1] if "season" in raw.columns else None
        both = pd.concat([raw.drop(columns=["row_id"]), app[raw.drop(columns=["row_id"]).columns]],
                         ignore_index=True)
        F = build_features(both)
        F["date"] = pd.to_datetime(F["date"]).dt.normalize()
        key = ["league", "date", "home_team", "away_team"]
        feats = up.merge(F, on=key, how="inner")
        reasons["served"] += int(len(feats))
    raw.to_parquet(out / "matches.parquet")
    feats.to_parquet(out / "upcoming_features.parquet")
    meta.update({"frame_hash": frame_hash(raw), "fixtures_in": int(len(fx)),
                 "reasons": dict(reasons)})
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"fixtures_in": int(len(fx)), "reasons": dict(reasons),
                      "feature_fingerprint": meta["feature_fingerprint"]}))
    return 0


if __name__ == "__main__":
    mode, *rest = sys.argv[1:]
    raise SystemExit({"history": history, "upcoming": upcoming}[mode](*rest))
