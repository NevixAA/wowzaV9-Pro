"""
Extract the inputs of the 1X2 review (src/studies/onex2_review.py) FROM v9, inside v9's environment.

    python src/studies/onex2_extract_v9.py <v9_root> <out_dir> <pro_fd_raw_dir>

Run as a SCRIPT, with v9's root put first on sys.path, so that `src` is v9's package, never Pro's.
The review calls it through a subprocess; nothing in Pro imports it.

WHAT IT WRITES (out_dir, never inside either repository's tracked tree):
  matches.parquet   v9's served match frame from the COMMITTED data, offline (the Phase 2 harness's
                    load: football-data download switched off, network blocked, every loader
                    correction applied, COVID seasons excluded) with a stable row_id
  features.parquet  src.feature_engineering.build_features on that frame (point-in-time form)
  prices.parquet    real 1X2 prices joined to row_id, one row per (row_id, source, class):
                      FD_ENTRY   football-data pre-match columns (Avg, else B365, else PS) - the
                                 european leagues of Pro's fd_raw files; bettable B365 kept apart
                      FD_CLOSE   football-data closing columns (AvgC, else B365C, else PSC)
                      SHARP_OPEN / SHARP_CLOSE  v9 sharp tracker h2h: the first snapshot / the last
                                 snapshot strictly before kickoff
                    A price row exists only where all three odds are real (> 1); nothing is filled.
  extract.json      provenance: v9 commit, frame hash, row counts, join rates per source and league

Names are joined ONLY through v9's league-scoped resolver (src.team_names.resolve). An unresolved
name does not join and is counted; nothing is guessed.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
from pathlib import Path


def main(v9_root: str, out_dir: str, fd_raw: str) -> int:
    sys.path.insert(0, v9_root)
    import os
    os.chdir(v9_root)
    import pandas as pd
    from src.retrain_harness import protocol as P
    P._block_network()
    import config
    from src import data_loader as DL
    from src.feature_engineering import build_features
    from src.standard_repair import FD_CODES, frame_hash
    from src.team_names import resolve

    DL._ci_download_all = lambda have=None: []
    DL._report_training_coverage = lambda out: None
    raw = DL.load_all_matches(force=True)
    covid = config.covid_season_mask(raw)
    raw = raw[~covid].copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    raw = raw.dropna(subset=["home_goals", "away_goals"])
    raw["row_id"] = (raw["date"].dt.strftime("%Y-%m-%d") + "|" + raw["league"].astype(str) + "|"
                     + raw["home_team"].astype(str) + "|" + raw["away_team"].astype(str))
    dup = int(raw["row_id"].duplicated().sum())
    raw = raw.drop_duplicates("row_id", keep="first")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(out / "matches.parquet")
    feat = build_features(raw)
    feat["date"] = pd.to_datetime(feat["date"]).dt.normalize()
    feat["row_id"] = (feat["date"].dt.strftime("%Y-%m-%d") + "|" + feat["league"].astype(str) + "|"
                      + feat["home_team"].astype(str) + "|" + feat["away_team"].astype(str))
    feat = feat.drop_duplicates("row_id", keep="first")
    feat.to_parquet(out / "features.parquet")

    by_league = {lg: g for lg, g in raw.groupby("league")}
    pools = {lg: sorted(set(g["home_team"].astype(str)) | set(g["away_team"].astype(str)))
             for lg, g in by_league.items()}
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
    for lg, g in by_league.items():
        for d, h, a, rid in zip(g["date"], g["home_team"].astype(str), g["away_team"].astype(str),
                                g["row_id"]):
            index[(lg, d, h, a)] = rid

    def find(lg, day, h, a):
        """Same league, both names resolved, date equal or one day apart (late kickoffs filed by
        the next UK day are corrected in v9 to the provider date; the price files may still carry
        either). Exactly one candidate or nothing."""
        ch, ca = canon(lg, h), canon(lg, a)
        if ch is None or ca is None:
            return None, "name_unresolved"
        hits = [index[k] for k in ((lg, day + pd.Timedelta(days=o), ch, ca) for o in (0, -1, 1))
                if k in index]
        if len(hits) != 1:
            return None, ("no_match_on_date" if not hits else "ambiguous_date")
        return hits[0], "ok"

    from collections import Counter
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
        r["_d"] = pd.to_datetime(r["Date"], dayfirst=True, errors="coerce").dt.normalize()
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
            # The price a bettor could actually take: one real bookmaker's pre-match quote.
            o = [pd.to_numeric(x.get("B365" + s), errors="coerce") for s in ("H", "D", "A")]
            if all(pd.notna(v) and v > 1.0 for v in o):
                rows.append({"row_id": rid, "source": "football-data", "class": "FD_BET365_ENTRY",
                             "book": "B365", "o_home": o[0], "o_draw": o[1], "o_away": o[2],
                             "price_at": None, "file": Path(f).name})

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
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=v9_root, capture_output=True,
                         text=True).stdout.strip()
    meta = {"v9_commit": sha, "frame_hash": frame_hash(raw), "matches": int(len(raw)),
            "duplicate_row_ids_dropped": dup, "covid_rows_excluded": int(covid.sum()),
            "feature_rows": int(len(feat)),
            "prices_by_class": prices["class"].value_counts().to_dict() if len(prices) else {},
            "join": stats}
    (out / "extract.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k != "join"}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
