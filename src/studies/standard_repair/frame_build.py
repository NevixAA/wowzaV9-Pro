"""Rebuild v9's training frame FROM A CLEAN v9 CHECKOUT, with row provenance — runs inside v9.

    cd <v9 checkout> && python <pro>/src/studies/standard_repair/frame_build.py --out DIR [--online]

WHY (owner brief 2026-10-28, P0 #10). The pre-repair benchmark read a frame that existed only on one
workstation (experiments/ou_info_inputs_2026_10/v9_frame_dedup.parquet, built 2026-10-19 by hand). A
benchmark nobody can rebuild cannot be checked and silently goes stale. This script rebuilds the frame
with v9's OWN loader and feature builder (`load_all_matches` + `build_features`) from nothing but a v9
checkout, so CI can do it on every run and the result is a pure function of the v9 commit.

DETERMINISM. By default the loader runs OFFLINE: `_ci_download_all` is replaced by a no-op, so the
football-data rows come from v9's committed `output/fd_history.parquet` cache (which v9's predict job
refreshes and commits). The frame is then a function of the v9 SHA alone. `--online` lets the loader
download the live season as v9's retrain would; the manifest records which mode ran.

PROVENANCE. v9's loader concatenates four sources without tagging them. The wrappers below tag each
row BEFORE club canonicalisation and record, per surviving fixture, every source that carried it:
    FOOTBALL_DATA_CURRENT   football-data row (committed cache or download) in the live season
    FOOTBALL_DATA_ARCHIVE   football-data row in a finished season
    BACKTEST_ARCHIVE        output/backtest_all_leagues.csv (v9's monthly backtest output, ~2020+)
    API_FOOTBALL            API-Football-only leagues (needs APIFOOTBALL_KEY; absent offline)
    OTHER                   anything else
Price provenance for odds_over25/odds_btts/odds_over15/odds_over35 is recorded the same way:
which enrichment step filled the value (football-data, archive, v9 forward captures).

READ-ONLY against v9 in effect: the only writes v9's loader makes (training_coverage.json, the
fd_history cache refresh) are disabled here; everything goes to --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

FRAME_BUILD_VERSION = "frame_build/1.0"
SOURCE_FILES = ("output/fd_history.parquet", "output/backtest_all_leagues.csv",
                "output/standard_sidemarket_odds_history.csv", "output/standard_odds_history.csv",
                "output/newformat_odds_history.csv", "output/af_history.parquet",
                "src/data_loader.py", "src/feature_engineering.py", "src/team_names.py", "config.py", "src/model.py",
                "models/model_v9_standard.pkl")
PRICE_COLS = ("odds_over25", "odds_under25", "odds_btts", "odds_over15", "odds_over35")


def sha256_file(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def live_season_start(now) -> int:
    return now.year if now.month >= 7 else now.year - 1


def season_start_from_date(dates):
    import pandas as pd
    d = pd.to_datetime(dates, errors="coerce")
    return d.dt.year.where(d.dt.month >= 7, d.dt.year - 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--online", action="store_true", help="let v9's loader download the live season")
    ap.add_argument("--v9-sha", default="", help="v9 commit when cwd is not a git checkout")
    ap.add_argument("--fd-dir", default="", help="serve v9's football-data download from these files")
    ap.add_argument("--recipe", default="legacy_v9", help="legacy_v9 (v9 build_features) or v9_repaired (R1)")
    ap.add_argument("--price-mode", default="closing", help="v9_repaired market-feature mode: none|asof|closing")
    ap.add_argument("--identity-map", default="", help="v9_repaired: alias map passed to R1's prepare_history")
    ap.add_argument("--keep-covid", action="store_true", help="do NOT drop v9's COVID seasons before features")
    ap.add_argument("--alias-map", default="", help="identity.py alias map applied after v9's canonicaliser")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import pandas as pd
    import config
    from src import data_loader as dl
    from src.feature_engineering import build_features

    t0 = time.time()
    captured: dict = {}

    # ── provenance wrappers ──────────────────────────────────────────────────────────────────
    orig_dl = dl._ci_download_all
    served: dict = {"served": [], "missing": []}
    if a.fd_dir:
        # v9's OWN download/parse code, fed from a directory of football-data files instead of the
        # network: mmz4281/{season}/{code}.csv -> {code}_{season}.csv, new/{code}.csv -> new_{code}.csv.
        import requests

        class _Resp:
            def __init__(self, status, text=""):
                self.status_code, self.text = status, text
                self.content = text.encode("utf-8")

        fd_dir = Path(a.fd_dir)

        def _get(url, *args, **kw):
            parts = url.rstrip("/").split("/")
            name = (f"new_{parts[-1]}" if parts[-2] == "new"
                    else f"{parts[-1].removesuffix('.csv')}_{parts[-2]}.csv")
            f = fd_dir / name
            if not f.exists():
                served["missing"].append(name)
                return _Resp(404)
            served["served"].append(name)
            raw_b = f.read_bytes()
            try:
                txt = raw_b.decode("utf-8-sig")
            except UnicodeDecodeError:
                txt = raw_b.decode("latin-1")
            return _Resp(200, txt)
        requests.get = _get

        def _dl(have=None):
            fr = orig_dl(have)
            for f in fr:
                f["_src_raw"] = "FOOTBALL_DATA"
            return fr
    elif a.online:
        def _dl(have=None):
            fr = orig_dl(have)
            for f in fr:
                f["_src_raw"] = "FOOTBALL_DATA"
            return fr
    else:
        def _dl(have=None):                       # offline: the committed cache is the source
            return []
    dl._ci_download_all = _dl

    orig_arch = dl._load_backtest_archive

    def _arch():
        d = orig_arch()
        if len(d):
            d = d.copy()
            d["_src_raw"] = "BACKTEST_ARCHIVE"
            # the archive's own price: odds timing unknown (written by v9's backtest from
            # whatever the frame carried at the time)
            d["_ou25_src"] = np.where(pd.to_numeric(d.get("odds_over25"), errors="coerce").notna(),
                                      "BACKTEST_ARCHIVE", None)
        return d
    dl._load_backtest_archive = _arch

    orig_af = dl._load_api_football_only_leagues

    def _af():
        fr = orig_af()
        for f in fr:
            f["_src_raw"] = "API_FOOTBALL"
        return fr
    dl._load_api_football_only_leagues = _af

    orig_canon = dl._canonicalise_clubs
    amap = json.loads(Path(a.alias_map).read_text(encoding="utf-8"))["map"] if a.alias_map else {}

    def _canon(df):
        df = df.copy()
        df["_src_raw"] = df["_src_raw"].fillna("FOOTBALL_DATA") if "_src_raw" in df else "FOOTBALL_DATA"
        if "_ou25_src" not in df:
            df["_ou25_src"] = None
        fd = df["_src_raw"] == "FOOTBALL_DATA"
        df.loc[fd & pd.to_numeric(df["odds_over25"], errors="coerce").notna(), "_ou25_src"] = "FOOTBALL_DATA"
        for c in ("odds_btts", "odds_over15", "odds_over35"):
            if c in df:
                df[f"_{c}_src"] = np.where(pd.to_numeric(df[c], errors="coerce").notna(), df["_src_raw"], None)
        df["_rowid"] = np.arange(len(df))
        # the canonical spelling each input row WILL get — same rule as _canonicalise_clubs
        # (most recently seen spelling of a within-league normalised key), so the identity audit
        # can see which raw rows merged into which fixture.
        pc = df.copy()
        for c in ("home_team", "away_team"):
            pc[c] = pc[c].astype(str).str.strip()
        long = pd.concat([pc[["league", "home_team", "date"]].rename(columns={"home_team": "t"}),
                          pc[["league", "away_team", "date"]].rename(columns={"away_team": "t"})])
        long["k"] = long["t"].map(dl._norm_club)
        long["date"] = pd.to_datetime(long["date"], errors="coerce")
        agg = (long.groupby(["league", "k", "t"]).agg(last=("date", "max"), n=("t", "size")).reset_index()
               .sort_values(["league", "k", "last", "n"], ascending=[True, True, False, False]))
        win = agg.drop_duplicates(["league", "k"], keep="first")
        mp = {(lg, k): t for lg, k, t in zip(win["league"], win["k"], win["t"])}
        for c in ("home_team", "away_team"):
            pc[f"_canon_{c}"] = [mp.get((lg, dl._norm_club(t)), t) for lg, t in zip(pc["league"].astype(str), pc[c])]
            pc[f"_normkey_{c}"] = pc[c].map(dl._norm_club)
        captured["precanon"] = pc
        res = orig_canon(df)
        if amap:
            # Pro's evidence-based alias map (identity.py), applied AFTER v9's own canonicaliser and
            # followed by v9's canonicaliser again, so duplicate removal and score-conflict
            # quarantine use v9's exact rules ("richest row wins", conflicting scores dropped).
            n0 = len(res)
            for c in ("home_team", "away_team"):
                res[c] = [amap.get(str(lg), {}).get(str(t), t) for lg, t in zip(res["league"], res[c])]
            res = orig_canon(res)
            captured["alias_rows_removed"] = int(n0 - len(res))
        captured["postcanon_rowids"] = res["_rowid"].to_numpy()
        return res
    dl._canonicalise_clubs = _canon

    def _wrap_fill(fn, cols, tag):
        def w(df):
            before = {c: pd.to_numeric(df[c], errors="coerce").notna().to_numpy() if c in df else None for c in cols}
            res = fn(df)
            for c in cols:
                if c not in res:
                    continue
                now = pd.to_numeric(res[c], errors="coerce").notna().to_numpy()
                b = before[c] if before[c] is not None else np.zeros(len(res), bool)
                filled = now & ~b
                scol = "_ou25_src" if c in ("odds_over25", "odds_under25") else f"_{c}_src"
                if scol not in res:
                    res[scol] = None
                res.loc[filled, scol] = tag
            return res
        return w
    dl._enrich_with_standard_sidemarket_odds = _wrap_fill(
        dl._enrich_with_standard_sidemarket_odds, ("odds_btts", "odds_over15", "odds_over35"), "V9_SIDEMARKET_CAPTURE")
    dl._enrich_ou25_from_captures = _wrap_fill(dl._enrich_ou25_from_captures, ("odds_over25",), "V9_OU25_CAPTURE_LAST")
    dl._report_training_coverage = lambda out: None          # no write into the v9 checkout

    # force CI mode even on a workstation that has the local workbook
    config.SUMMARY_XLSX = Path(out / "__no_workbook__.xlsx")
    # READ-ONLY against the v9 checkout: v9's loader refreshes output/fd_history.parquet whenever it
    # "downloaded" something; never let it write inside the checkout.
    _orig_to_parquet = pd.DataFrame.to_parquet
    cwd = Path.cwd().resolve()
    blocked: list = []

    def _guarded(self, path, *args, **kw):
        try:
            inside = Path(path).resolve().is_relative_to(cwd)
        except Exception:                                                     # noqa: BLE001
            inside = False
        if inside:
            blocked.append(str(path))
            return None
        return _orig_to_parquet(self, path, *args, **kw)
    pd.DataFrame.to_parquet = _guarded
    try:
        raw = dl.load_all_matches(force=True)
    finally:
        pd.DataFrame.to_parquet = _orig_to_parquet
    captured["blocked_writes"] = blocked
    t_load = time.time() - t0

    # ── source classification (current vs archive season) ────────────────────────────────────
    now = pd.Timestamp.now(tz='UTC')
    live = live_season_start(now)
    ss = season_start_from_date(raw["date"])
    src = raw["_src_raw"].fillna("OTHER").astype(str)
    raw["row_source"] = np.select(
        [src.eq("FOOTBALL_DATA") & ss.eq(live), src.eq("FOOTBALL_DATA"), src.eq("BACKTEST_ARCHIVE"),
         src.eq("API_FOOTBALL")],
        ["FOOTBALL_DATA_CURRENT", "FOOTBALL_DATA_ARCHIVE", "BACKTEST_ARCHIVE", "API_FOOTBALL"], "OTHER")

    # every source that carried each surviving fixture (identity audit + provenance)
    pre = captured["precanon"]
    pre_std = pre[pre["league"].isin(config.STANDARD_FORMAT_LEAGUES)].copy()
    keep = [c for c in pre_std.columns if not c.startswith("_") or c in
            ("_src_raw", "_rowid", "_ou25_src", "_canon_home_team", "_canon_away_team",
             "_normkey_home_team", "_normkey_away_team")]
    pre_std = pre_std[keep]
    for c in pre_std.columns:
        if pre_std[c].dtype == object:
            pre_std[c] = pre_std[c].astype("string")
    pre_std.to_parquet(out / "raw_precanon_standard.parquet", index=False)

    # v9's mode_train drops the COVID seasons from the RAW matches BEFORE building features, so the
    # first post-COVID rolling windows never see 2019/20-2020/21 matches. Reproduce that exactly.
    n_covid = 0
    if config.EXCLUDE_COVID_SEASONS and not a.keep_covid:
        m = raw["season"].astype(str).isin(set(map(str, config.COVID_SEASONS)))
        n_covid = int(m.sum())
        raw = raw[~m]
    rep_identity = None
    if a.recipe == "v9_repaired":
        # R1's repaired recipe (v9 worktree with src/standard_repair.py): identity canonicalised and
        # de-duplicated BEFORE features, league-scoped canonical as-of features, price mode explicit.
        from src import standard_repair as SR
        raw2, rep_identity = SR.prepare_history(raw, "v9_repaired", alias_map=a.identity_map or None)
        fdp = SR.load_fd_entry_prices(a.fd_dir) if a.price_mode == "asof" else None
        feat = SR.feature_frame(raw2, "v9_repaired", price_mode=a.price_mode, fd_prices=fdp)
        rep_identity = {k: v for k, v in (rep_identity or {}).items() if k != "quarantine_rows"} |             {"quarantine_rows": len((rep_identity or {}).get("quarantine_rows", []))}
    else:
        feat = build_features(raw)
    feat["track"] = np.where(feat["league"].isin(config.STANDARD_FORMAT_LEAGUES), "standard",
                             np.where(feat["league"].isin(config.NEW_FORMAT_LEAGUES), "new_format", "other"))
    feat["covid_excluded"] = feat["season"].astype(str).isin(set(map(str, config.COVID_SEASONS))) \
        if config.EXCLUDE_COVID_SEASONS else False
    feat["v9_train_eligible"] = (~feat["covid_excluded"]) & feat["over25"].notna() & feat["home_scored_last5"].notna()
    feat["decay_weight"] = feat["season"].map(
        lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)).fillna(config.DEFAULT_DECAY_WEIGHT)
    for c in ("_src_raw",):
        feat = feat.drop(columns=[c], errors="ignore")
    obj = [c for c in feat.columns if feat[c].dtype == object and c not in ("date",)]
    for c in obj:
        feat[c] = feat[c].astype("string")
    feat.to_parquet(out / "frame.parquet", index=False)

    std = feat[feat["track"] == "standard"].sort_values(["date", "league", "home_team", "away_team"])
    key_cols = ["date", "league", "home_team", "away_team", "home_goals", "away_goals"]
    frame_hash = hashlib.sha256(pd.util.hash_pandas_object(std[key_cols].astype(str), index=False)
                                .to_numpy().tobytes()).hexdigest()
    full_hash = hashlib.sha256(pd.util.hash_pandas_object(
        std.drop(columns=[c for c in std.columns if c.startswith("_")]).astype(str), index=False)
        .to_numpy().tobytes()).hexdigest()

    v9_sha = a.v9_sha
    if not v9_sha:
        try:
            v9_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                    timeout=30).stdout.strip()
        except Exception:                                                     # noqa: BLE001
            v9_sha = ""
    import pickle
    try:
        serving_feats = list(pickle.load(open("models/model_v9_standard.pkl", "rb"))["feature_cols"])
    except Exception:                                                         # noqa: BLE001
        serving_feats = []
    manifest = {
        "frame_build_version": FRAME_BUILD_VERSION, "built_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "mode": ("fd_dir" if a.fd_dir else "online" if a.online else "offline_committed_cache"),
        "fd_files_served": sorted(set(served["served"])), "fd_files_missing": sorted(set(served["missing"])),
        "fd_dir_sha256": ({f.name: sha256_file(f) for f in sorted(Path(a.fd_dir).glob("*.csv"))} if a.fd_dir else {}),
        "v9_commit": v9_sha, "live_season_start": live,
        "inputs_sha256": {p: sha256_file(Path(p)) for p in SOURCE_FILES},
        "standard_frame_key_hash": frame_hash, "standard_frame_full_hash": full_hash,
        "alias_map_sha256": sha256_file(Path(a.alias_map)) if a.alias_map else None,
        "alias_rows_removed": captured.get("alias_rows_removed", 0),
        "covid_rows_dropped_before_features": n_covid,
        "recipe": a.recipe, "price_mode": a.price_mode, "r1_identity_report": rep_identity,
        "rows_total": int(len(feat)), "rows_standard": int(len(std)),
        "standard_date_range": [str(pd.to_datetime(std["date"]).min().date()),
                                str(pd.to_datetime(std["date"]).max().date())],
        "rows_by_source_standard": std["row_source"].value_counts().to_dict(),
        "serving_feature_cols": serving_feats,
        "seconds_load": round(t_load, 1), "seconds_total": round(time.time() - t0, 1),
    }
    (out / "frame_manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("inputs_sha256", "serving_feature_cols",
                                                                      "fd_dir_sha256", "fd_files_served")},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
