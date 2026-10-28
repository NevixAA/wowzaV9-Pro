"""STD-V9R-SHADOW-2026Q4 — Standard repair FORWARD SHADOW test (owner-approved 2026-10-28).

RESEARCH / SHADOW ONLY. Nothing here is read by v9 selection, tips, stakes, thresholds, models or
Telegram; v9 is only ever checked out read-only. Registration: registry/standard_repair/
forward_shadow_v1.json (frozen, hash-checked). Workflow: .github/workflows/pro_standard_repair_shadow.yml.

    python -m src.studies.standard_repair.shadow check
    python -m src.studies.standard_repair.shadow train  --v9-code DIR --fd-dir DIR --work DIR
    python -m src.studies.standard_repair.shadow ledger-append --entry FILE
    python -m src.studies.standard_repair.shadow active --field release_tag|v9_commit|model_version|sklearn
    python -m src.studies.standard_repair.shadow score  --v9-code DIR --v9-data DIR --models DIR --work DIR
    python -m src.studies.standard_repair.shadow settle --v9-code DIR --v9-data DIR --work DIR
    python -m src.studies.standard_repair.shadow report

ROWS. One FIRST-SIGHT row per (fixture, market): the first scoring run after registration at which
EVERY registered arm of that market is scorable on the same fixture at the same instant - board
fresh (< 24 h), kickoff strictly in the future, rolling form present (invariant 8), a genuine
two-sided market (>= 3 books). Written by plain APPEND (earlier bytes are never rewritten) to
output/standard_repair/forward_shadow.csv; a row id that exists is never written again. Every
later observation, and every incomplete one with its reason, goes to the day's sightings file
output/standard_repair/forward_shadow_sightings/<YYYY-MM-DD>.csv. Settlement (results + certified
closes) lives in a separate derived file, forward_shadow_settled.csv; once a row is SETTLED or VOID
it is carried forward unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data.entities import fixture_key
from src.studies.standard_repair import shadow_market as MK
from src.studies.standard_repair import shadow_models as SM
from src.studies.standard_repair import shadow_registry as R
from src.studies.standard_repair.evaluate import bh, block_boot, calib, ll, paired

OUT = cfg.OUTPUT_DIR / "standard_repair"
FS = OUT / "forward_shadow.csv"
SIGHT_DIR = OUT / "forward_shadow_sightings"
SETTLED = OUT / "forward_shadow_settled.csv"
REPORT_JSON = OUT / "forward_shadow_report.json"
REPORT_MD = OUT / "forward_shadow_report.md"
V9_SCRIPT = Path(__file__).resolve().parent / "shadow_v9.py"

TARGET = {"OU25": "over25", "BTTS": "btts", "OU15": "over15"}
BOARD_P = {"OU25": "p_over25", "BTTS": "p_btts", "OU15": "p_over15"}
BOARD_MV = {"OU25": "model_version", "BTTS": "model_version_btts", "OU15": "model_version_over15"}
ALL_ARMS = ("CURRENT_V9_SERVED", "V9_REPAIRED", "MKT_RESID_LR", "MKT_RESID_HGB", "MARKET")
MAX_BOARD_AGE_H = 24
FS_COLUMNS = ["experiment_id", "phase", "row_id", "fixture_key", "league", "match_date", "kickoff_utc", "home_team",
              "away_team", "history_home", "history_away", "market", "scored_at", "minutes_to_kickoff",
              "model_version", "v9_code_commit", "v9_data_commit", "v9_board_generated_at", "v9_served_model_version"] \
    + [f"p_{a}" for a in ALL_ARMS] + ["market_class", "price_is_real", "market_source", "n_books", "price_ts",
                                      "entry_odds_first", "entry_odds_other", "best_odds_first", "best_odds_other"]
SIGHT_COLUMNS = ["row_id", "fixture_key", "league", "market", "scored_at", "status", "model_version"] \
    + [f"p_{a}" for a in ALL_ARMS] + ["n_books", "market_class", "entry_odds_first", "entry_odds_other"]
FINAL = ("SETTLED", "VOID_NO_RESULT")


class Immutable(RuntimeError):
    """A first-sight row would be rewritten, back-dated or scored after kickoff."""


# ── helpers ────────────────────────────────────────────────────────────────────────────────
def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _git(path) -> str:
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def _run_v9(v9_code, *args) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(V9_SCRIPT), *map(str, args)], cwd=str(v9_code), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(r.stdout[-4000:])
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-8000:])
        raise RuntimeError(f"v9-side step {args[0]} failed (exit {r.returncode})")


def _libs() -> dict:
    import sklearn
    return {"python": sys.version.split()[0], "sklearn": sklearn.__version__, "pandas": pd.__version__,
            "numpy": np.__version__}


def arms_for(reg: dict, market: str) -> list[str]:
    return list(reg["markets"][market]["arms"])


def side_names(market: str) -> tuple[str, str]:
    return MK.FIRST_SIDE[market]


# ── TRAIN ──────────────────────────────────────────────────────────────────────────────────
def cmd_train(a) -> None:
    reg = R.load_registration()
    now = _now()
    cutoff = now.tz_convert(None).normalize()
    work = Path(a.work).resolve()
    v9out, rel = work / "v9", work / "release"
    rel.mkdir(parents=True, exist_ok=True)
    _run_v9(a.v9_code, "train", "--out", v9out, "--alias-map", R.ALIASES.resolve(), "--cutoff", cutoff.date())
    meta = json.loads((v9out / "meta.json").read_text(encoding="utf-8"))
    frozen = reg["frozen_inputs"]["recipe_versions"]
    if meta["versions"] != frozen:
        raise R.RegistrationError(f"v9 recipe versions {meta['versions']} != registered {frozen}; a changed "
                                  "recipe is a new experiment id")
    fr = pd.read_parquet(v9out / "frame_std.parquet")
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    if fr["date"].max() >= cutoff:
        raise R.RegistrationError("Standard frame contains a row on/after the training cutoff")
    amap = json.loads(R.ALIASES.read_text(encoding="utf-8"))["map"]
    from src.studies.standard_repair.data import FD_CODES
    fr = SM.attach_anchor(fr, SM.fd_anchor(a.fd_dir, FD_CODES, amap))
    fr["env_rate"] = SM.env_rate_history(fr, "y_OU25")
    fr = SM.add_derived(fr)
    cols = SM.feature_columns(fr)
    want = reg["frozen_inputs"]["feature_manifest"]["MKT_RESID"]["columns"]
    if cols != want:
        raise R.RegistrationError(f"MKT_RESID feature columns differ from the registration: "
                                  f"missing {sorted(set(want) - set(cols))}, extra {sorted(set(cols) - set(want))}")
    bet = fr[fr["league"].isin(reg["leagues"]) & (fr["date"] >= cutoff - pd.Timedelta(days=730))]
    cov = float(bet["pm_OU25"].notna().mean()) if len(bet) else 0.0
    if cov < reg["frozen_inputs"]["market_source"]["training_anchor_min_coverage"]:
        raise R.RegistrationError(f"training anchor coverage {cov:.3f} on the 7 leagues (last 2 years) is too low")
    tr = fr[fr["date"] < cutoff]
    assets = {}
    for arm in SM.RESID_ARMS:
        pay = SM.fit_resid(tr, arm, cols)
        pay.update(training_cutoff=str(cutoff.date()), experiment_id=R.EXPERIMENT_ID)
        p = rel / f"{arm}_OU25.pkl"
        with open(p, "wb") as f:
            pickle.dump(pay, f)
    for t in TARGET.values():
        src = v9out / f"V9_REPAIRED_standard_{t}.pkl"
        (rel / src.name).write_bytes(src.read_bytes())
    (rel / "aliases.json").write_bytes(R.ALIASES.read_bytes())
    for p in sorted(rel.iterdir()):
        assets[p.name] = {"sha256": R.sha256_file(p), "bytes": p.stat().st_size}
    digest = R.sha256_bytes(json.dumps(assets, sort_keys=True).encode())[:8]
    version = f"STDSHADOW-{cutoff:%Y%m%d}-{digest}"
    entry = {"model_version": version, "trained_at": now.isoformat(), "training_cutoff": str(cutoff.date()),
             "training_rule": "rows dated strictly before training_cutoff (UTC date of the TRAIN run)",
             "v9_commit": meta["v9_commit"], "pro_commit": _git(cfg.BASE_DIR), "release_tag": f"std-shadow-{version.lower()}",
             "assets": assets, "recipe_versions": meta["versions"], "v9_source_sha256": meta["source_sha256"],
             "feature_manifest": {"MKT_RESID": cols, "V9_REPAIRED": {t: v["feature_cols"] for t, v in meta["payloads"].items()}},
             "imputer": {"V9_REPAIRED": f"persisted train-only ({meta['versions']['imputer_version']}) inside each payload",
                         "MKT_RESID_LR": "train medians + standardisation persisted in payload", "MKT_RESID_HGB": "native NaN handling"},
             "rows": {"V9_REPAIRED": {t: v["rows"] for t, v in meta["payloads"].items()},
                      "MKT_RESID": int(tr["pm_OU25"].notna().sum()), "frame_std": int(len(fr))},
             "training_anchor_coverage_7_leagues_2y": round(cov, 4),
             "alias_map_sha256": R.sha256_text(R.ALIASES), "libs": _libs()}
    (work / "entry.json").write_text(json.dumps(entry, indent=1), encoding="utf-8")
    print(json.dumps({k: entry[k] for k in ("model_version", "release_tag", "training_cutoff", "rows",
                                            "training_anchor_coverage_7_leagues_2y")}, indent=1))


def cmd_ledger_append(a) -> None:
    R.load_registration()
    e = R.append_version(json.loads(Path(a.entry).read_text(encoding="utf-8")))
    print(f"ledger: appended {e['model_version']}")


def cmd_active(a) -> None:
    v = R.active_version()
    if v is None:
        raise R.RegistrationError("no model version in the ledger - dispatch the TRAIN job first")
    print(v["libs"]["sklearn"] if a.field == "sklearn" else v[a.field])


# ── SCORE ──────────────────────────────────────────────────────────────────────────────────
def board_rows(pred: pd.DataFrame, leagues, now: pd.Timestamp) -> pd.DataFrame:
    """The 7 Standard bet leagues, kickoff strictly in the future, one row per fixture."""
    b = pred[pred["league"].isin(set(leagues))].copy()
    b["kickoff"] = pd.to_datetime(b["kickoff_utc"], errors="coerce", utc=True)
    b = b[b["kickoff"].notna() & (b["kickoff"] > now)]
    b["date"] = b["date"].astype(str).str[:10]
    b["row_key"] = [fixture_key(l, d, h, w) for l, d, h, w in zip(b["league"], b["date"], b["home_team"], b["away_team"])]
    return b.drop_duplicates("row_key", keep="last").reset_index(drop=True)


def build_candidates(board: pd.DataFrame, feats: pd.DataFrame, mkt: dict, reg: dict, now: pd.Timestamp,
                     ctx: dict) -> pd.DataFrame:
    """One candidate per (fixture, market) with every arm probability and a status: COMPLETE or
    INCOMPLETE:<reason>. `feats` is aligned to `board` by row_key and carries p_V9_REPAIRED_*,
    p_MKT_RESID_* (OU25) and history_home/away. `mkt[(row_key, market)]` = consensus dict."""
    if "generated_at" in board:
        gen = pd.to_datetime(board["generated_at"], errors="coerce", utc=True)
    else:
        gen = pd.Series(pd.NaT, index=board.index, dtype="datetime64[ns, UTC]")
    f = feats.set_index("row_key")
    rows = []
    for i, b in board.iterrows():
        x = f.loc[b["row_key"]]
        for m in reg["markets"]:
            c = mkt.get((b["row_key"], m)) or MK.consensus(pd.DataFrame(columns=MK.COLS), m, now)
            p = {"CURRENT_V9_SERVED": pd.to_numeric(b.get(BOARD_P[m]), errors="coerce"),
                 "V9_REPAIRED": x.get(f"p_V9_REPAIRED_{TARGET[m]}", np.nan),
                 "MKT_RESID_LR": x.get("p_MKT_RESID_LR", np.nan) if m == "OU25" else np.nan,
                 "MKT_RESID_HGB": x.get("p_MKT_RESID_HGB", np.nan) if m == "OU25" else np.nan,
                 "MARKET": c["p_market"] if c["price_is_real"] else np.nan}
            p = {k: (float(v) if pd.notna(v) else np.nan) for k, v in p.items()}
            age_h = (now - gen.iloc[i]).total_seconds() / 3600 if pd.notna(gen.iloc[i]) else np.inf
            reason = None
            if b["kickoff"] <= now:
                reason = "POST_KICKOFF"
            elif age_h > MAX_BOARD_AGE_H:
                reason = "STALE_BOARD"
            elif bool(x.get("no_form_data", True)):
                reason = "NO_FORM_DATA"
            elif not c["price_is_real"]:
                reason = "NO_GENUINE_PRICE"
            else:
                miss = [a for a in arms_for(reg, m) if not np.isfinite(p[a])]
                reason = f"ARM_MISSING:{'+'.join(miss)}" if miss else None
            rows.append({"experiment_id": R.EXPERIMENT_ID, "phase": R.PHASE,
                         "row_id": f"{b['row_key']}|{m}", "fixture_key": b["row_key"], "league": b["league"],
                         "match_date": b["date"], "kickoff_utc": b["kickoff"].isoformat(),
                         "home_team": b["home_team"], "away_team": b["away_team"],
                         "history_home": x.get("history_team_home"), "history_away": x.get("history_team_away"),
                         "market": m, "scored_at": now.isoformat(),
                         "minutes_to_kickoff": round((b["kickoff"] - now).total_seconds() / 60, 1),
                         "model_version": ctx["model_version"], "v9_code_commit": ctx["v9_code_commit"],
                         "v9_data_commit": ctx["v9_data_commit"],
                         "v9_board_generated_at": None if pd.isna(gen.iloc[i]) else gen.iloc[i].isoformat(),
                         "v9_served_model_version": b.get(BOARD_MV[m]),
                         **{f"p_{a}": p[a] for a in ALL_ARMS},
                         "market_class": c["market_class"], "price_is_real": bool(c["price_is_real"]),
                         "market_source": c["sources"], "n_books": c["n_books"], "price_ts": c["price_ts"],
                         "entry_odds_first": c["odds_first_median"], "entry_odds_other": c["odds_other_median"],
                         "best_odds_first": c["odds_first_best"], "best_odds_other": c["odds_other_best"],
                         "status": "COMPLETE" if reason is None else f"INCOMPLETE:{reason}"})
    return pd.DataFrame(rows)


def append_first_sight(cands: pd.DataFrame, reg: dict, path: Path = FS) -> pd.DataFrame:
    """APPEND the complete candidates whose row_id has never been written. Returns the new rows."""
    c = cands[cands["status"] == "COMPLETE"].copy() if len(cands) else cands
    if c.empty:
        return c
    seen = pd.to_datetime(c["scored_at"], utc=True)
    if (seen <= R.registered_at(reg)).any():
        raise Immutable("rows scored at/before registration are retrospective; they never count")
    if (pd.to_datetime(c["kickoff_utc"], utc=True) <= seen).any():
        raise Immutable("a first-sight row at/after kickoff - predict is pre-match only")
    if (c["phase"] != R.PHASE).any():
        raise Immutable("every forward-shadow row is POST_REPAIR_FORWARD")
    for m, g in c.groupby("market"):
        need = [f"p_{a}" for a in arms_for(reg, m)]
        if g[need].isna().any().any():
            raise Immutable(f"{m}: a COMPLETE row lacks a registered arm (rows must be identical across arms)")
    old_ids = set()
    if path.exists():
        old = pd.read_csv(path, usecols=["row_id"], dtype=str)
        if old["row_id"].duplicated().any():
            raise Immutable(f"{path.name} already holds a duplicated row_id - investigate before writing")
        old_ids = set(old["row_id"])
    new = c[~c["row_id"].isin(old_ids)].drop_duplicates("row_id", keep="first")
    if new.empty:
        return new
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as fh:
        new[FS_COLUMNS].to_csv(fh, header=header, index=False, lineterminator="\n")
    return new


def write_sightings(cands: pd.DataFrame, first_ids: set, now: pd.Timestamp, folder: Path = SIGHT_DIR) -> Path | None:
    if cands.empty:
        return None
    s = cands.copy()
    s["status"] = np.where(s["row_id"].isin(first_ids), "FIRST_SIGHT",
                           np.where(s["status"] == "COMPLETE", "LATER_SIGHTING", s["status"]))
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{now:%Y-%m-%d}.csv"
    header = not p.exists()
    with open(p, "a", encoding="utf-8", newline="") as fh:
        s[SIGHT_COLUMNS].to_csv(fh, header=header, index=False, lineterminator="\n")
    return p


def cmd_score(a) -> None:
    reg = R.load_registration()
    now = _now()
    if now <= R.registered_at(reg):
        raise Immutable("scoring before the registration time")
    ver = R.active_version(now)
    if ver is None:
        raise R.RegistrationError("no model version in the ledger - dispatch the TRAIN job first")
    assets = R.verify_assets(ver, Path(a.models))
    if R.sha256_text(assets["aliases.json"]) != reg["frozen_inputs"]["alias_map"]["sha256"]:
        raise R.RegistrationError("the model version's alias map is not the registered one")
    if _libs()["sklearn"] != ver["libs"]["sklearn"]:
        raise R.RegistrationError(f"sklearn {_libs()['sklearn']} != training {ver['libs']['sklearn']} (pickles)")
    if _git(a.v9_code) != ver["v9_commit"]:
        raise R.RegistrationError("v9 code checkout is not the commit the model version was trained from")
    work = Path(a.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    pred = pd.read_csv(Path(a.v9_data) / "output" / "predictions.csv", low_memory=False)
    board = board_rows(pred, reg["leagues"], now)
    board[["row_key", "date", "league", "home_team", "away_team"]].to_csv(work / "board.csv", index=False)
    _run_v9(a.v9_code, "features", "--board", work / "board.csv", "--payloads", Path(a.models).resolve(),
            "--alias-map", assets["aliases.json"].resolve(), "--out", work / "v9")
    meta = json.loads((work / "v9" / "meta.json").read_text(encoding="utf-8"))
    if meta["source_sha256"] != ver["v9_source_sha256"] or meta["versions"] != ver["recipe_versions"]:
        raise R.RegistrationError("serve-time v9 feature code differs from the code the model was trained with")
    feats = pd.read_parquet(work / "v9" / "upcoming.parquet")
    ctx = {"model_version": ver["model_version"], "v9_code_commit": ver["v9_commit"], "v9_data_commit": _git(a.v9_data)}
    if board.empty:
        print("no upcoming Standard fixtures on the board")
        return
    played = pd.read_parquet(work / "v9" / "played.parquet")
    feats["env_rate"] = SM.env_rate_asof(played, feats, "y_OU25")
    q = MK.load_quotes(a.v9_data, reg["leagues"], now - pd.Timedelta(days=14), now)
    q = MK.attach_fixtures(q, board[["row_key", "league", "kickoff_utc", "home_team", "away_team"]])
    kick = board.set_index("row_key")["kickoff"]
    mkt = {}
    for (rk, m), g in q.dropna(subset=["row_key"]).groupby(["row_key", "market"]):
        mkt[(rk, m)] = MK.consensus(g[g["ts"] < kick[rk]], m, now)
    pm = {rk: c["p_market"] for (rk, m), c in mkt.items() if m == "OU25" and c["price_is_real"]}
    feats["pm_OU25"] = feats["row_key"].map(pm)
    feats = SM.add_derived(feats)
    for arm in SM.RESID_ARMS:
        with open(assets[f"{arm}_OU25.pkl"], "rb") as fh:
            pay = pickle.load(fh)
        if pay["cols"] != reg["frozen_inputs"]["feature_manifest"]["MKT_RESID"]["columns"]:
            raise R.RegistrationError(f"{arm} payload feature list differs from the registration")
        feats[f"p_{arm}"] = SM.predict_resid(pay, feats)
    cands = build_candidates(board, feats, mkt, reg, now, ctx)
    new = append_first_sight(cands, reg)
    sp = write_sightings(cands, set(new["row_id"]) if len(new) else set(), now)
    print(f"scored {len(board)} fixtures x {len(reg['markets'])} markets; first sights +{len(new)}; "
          f"status {cands['status'].value_counts().to_dict()}; sightings {sp.name if sp else '-'}")


# ── SETTLE ─────────────────────────────────────────────────────────────────────────────────
def y_of(market: str, hg, ag):
    t = hg + ag
    return {"OU25": t > 2.5, "OU15": t > 1.5, "BTTS": (hg > 0) & (ag > 0)}[market]


def attach_results(todo: pd.DataFrame, res: pd.DataFrame, tol_days: int = 3) -> pd.DataFrame:
    """Join on league + the HISTORY club names recorded at first sight (same canonicalisation as
    the result source) with |date - match_date| <= tol_days; ambiguous -> no result."""
    r = res.copy()
    r["date"] = pd.to_datetime(r["date"]).dt.normalize()
    by = {k: g for k, g in r.groupby(["league", "home_team", "away_team"])}
    hg, ag = [], []
    for t in todo.itertuples(index=False):
        g = by.get((t.league, t.history_home, t.history_away))
        if g is not None:
            g = g[(g["date"] - pd.Timestamp(t.match_date)).abs() <= pd.Timedelta(days=tol_days)]
        if g is not None and len(g) == 1:
            hg.append(float(g["home_goals"].iloc[0]))
            ag.append(float(g["away_goals"].iloc[0]))
        else:
            hg.append(np.nan)
            ag.append(np.nan)
    out = todo.copy()
    out["home_goals"], out["away_goals"] = hg, ag
    return out


def settle_rows(fs: pd.DataFrame, old: pd.DataFrame, res: pd.DataFrame, quotes: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    keep = old[old["settle_status"].isin(FINAL)] if len(old) else pd.DataFrame()
    todo = fs[~fs["row_id"].isin(set(keep.get("row_id", [])))].copy()
    if todo.empty:
        return keep
    todo = attach_results(todo, res)
    ko = pd.to_datetime(todo["kickoff_utc"], utc=True)
    todo["y"] = [float(y_of(m, h, a)) if np.isfinite(h) and np.isfinite(a) else np.nan
                 for m, h, a in zip(todo["market"], todo["home_goals"], todo["away_goals"])]
    groups = {k: g for k, g in quotes.dropna(subset=["row_key"]).groupby(["row_key", "market"])} if len(quotes) else {}
    closes = []
    for t, k in zip(todo.itertuples(index=False), ko):
        if k > now:
            closes.append({"close_status": "NOT_YET"})
            continue
        g = groups.get((t.fixture_key, t.market), pd.DataFrame(columns=MK.COLS))
        closes.append(MK.closing(g, t.market, k))
    todo = pd.concat([todo.reset_index(drop=True), pd.DataFrame(closes)], axis=1)
    past = (ko < now).to_numpy()
    stale = (ko < now - pd.Timedelta(days=14)).to_numpy()
    todo["settle_status"] = np.where(todo["y"].notna().to_numpy() & past, "SETTLED",
                                     np.where(stale, "VOID_NO_RESULT", "PENDING"))
    todo["result_source"] = np.where(todo["y"].notna(), "FOOTBALL_DATA_VIA_V9_LOADER", None)
    todo["settled_at"] = now.isoformat()
    cols = ["row_id", "fixture_key", "market", "home_goals", "away_goals", "y", "result_source", "p_close",
            "n_books_close", "close_odds_first", "close_odds_other", "close_last_obs_min_before_ko", "close_status",
            "settle_status", "settled_at"]
    todo = todo.reindex(columns=cols)
    return pd.concat([keep, todo], ignore_index=True) if len(keep) else todo


def cmd_settle(a) -> None:
    R.load_registration()
    now = _now()
    if not FS.exists():
        print("no first-sight rows yet")
        return
    fs = pd.read_csv(FS)
    old = pd.read_csv(SETTLED) if SETTLED.exists() else pd.DataFrame()
    pending = fs[~fs["row_id"].isin(set(old.loc[old["settle_status"].isin(FINAL), "row_id"]) if len(old) else set())]
    if pending.empty:
        print("nothing to settle")
        return
    work = Path(a.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    since = (pd.to_datetime(pending["match_date"]).min() - pd.Timedelta(days=4)).date()
    _run_v9(a.v9_code, "results", "--since", since, "--alias-map", R.ALIASES.resolve(), "--out", work / "results.csv")
    res = pd.read_csv(work / "results.csv")
    ko = pd.to_datetime(pending["kickoff_utc"], utc=True)
    q = MK.load_quotes(a.v9_data, pending["league"].unique(), ko.min() - pd.Timedelta(days=10),
                       min(ko.max(), now) + pd.Timedelta(days=1), archive=True)
    fx = pending.drop_duplicates("fixture_key").rename(columns={"fixture_key": "row_key"})
    q = MK.attach_fixtures(q, fx[["row_key", "league", "kickoff_utc", "home_team", "away_team"]])
    out = settle_rows(fs, old, res, q, now)
    SETTLED.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(SETTLED, index=False, lineterminator="\n")
    print(f"settled file: {out['settle_status'].value_counts().to_dict()}; "
          f"certified closes {int((out['close_status'] == 'CERTIFIED_T30').sum())}")


# ── REPORT ─────────────────────────────────────────────────────────────────────────────────
def money(g: pd.DataFrame, arm: str, market: str) -> dict:
    """Flat 1u on the side the arm leans to vs MARKET, at the FIRST-LOGGED median entry price.
    Only genuine prices count; CLV only against CERTIFIED_T30 closes. Synthetic prices never enter."""
    first, _ = side_names(market)
    real = g[g["price_is_real"].astype(str).str.lower().isin(["true", "1"]) & (g["market_class"] == "GENUINE_FORWARD_TWO_SIDED")]
    if real.empty:
        return {"roi": None, "roi_n": 0, "clv_pp": None, "clv_n": 0}
    over = (real[f"p_{arm}"] > real["p_MARKET"]).to_numpy()
    odds = np.where(over, real["entry_odds_first"], real["entry_odds_other"]).astype(float)
    won = np.where(over, real["y"] == 1, real["y"] == 0)
    ok = np.isfinite(odds) & (odds > 1)
    pnl = np.where(won, odds - 1, -1.0)[ok]
    out = {"roi": round(float(pnl.mean()), 4) if len(pnl) else None, "roi_n": int(ok.sum())}
    if len(pnl) >= 20:
        bs = block_boot(pnl, real["week"].to_numpy()[ok])
        out["roi_ci95"] = None if bs is None else [round(float(x), 4) for x in np.quantile(bs, [0.025, 0.975])]
    cert = (real["close_status"] == "CERTIFIED_T30").to_numpy()
    pe = np.where(over, real["p_MARKET"], 1 - real["p_MARKET"])
    pc = np.where(over, real["p_close"], 1 - real["p_close"])
    clv = (pc - pe)[cert & np.isfinite(pc)]
    out.update(clv_pp=round(float(clv.mean()) * 100, 3) if len(clv) else None, clv_n=int(len(clv)))
    return out


def metrics(g: pd.DataFrame, arm: str, market: str, base: str = "MARKET") -> dict:
    if g.empty:
        return {"n": 0, "matchdays": 0}
    y, p, pb = g["y"].to_numpy(float), g[f"p_{arm}"].to_numpy(float), g[f"p_{base}"].to_numpy(float)
    out = {"n": int(len(g)), "matchdays": int(g["week"].nunique()), "log_loss": round(float(ll(p, y).mean()), 5),
           "brier": round(float(((p - y) ** 2).mean()), 5)}
    if len(g) >= 30:
        out["calibration"] = calib(p, y)
    d = paired(ll(p, y) - ll(pb, y), g["week"])
    out.update({f"dLL_vs_{base}": d["delta"], f"dLL_vs_{base}_ci95": d["ci95"], f"p_one_sided_vs_{base}": d["p_one_sided"],
                f"dBrier_vs_{base}": round(float((((p - y) ** 2) - ((pb - y) ** 2)).mean()), 6)})
    return out


def _holm(p: dict) -> dict:
    keys = sorted([k for k, v in p.items() if v is not None], key=lambda k: p[k])
    out, run, m = {}, 0.0, len(keys)
    for i, k in enumerate(keys):
        run = max(run, min(1.0, p[k] * (m - i)))
        out[k] = round(run, 5)
    return out


def build_report(fs: pd.DataFrame, st: pd.DataFrame, reg: dict, prior: dict | None = None, now=None) -> dict:
    now = now or _now()
    dec = reg["decision_rules"]
    rep = {"experiment_id": R.EXPERIMENT_ID, "phase": R.PHASE, "generated_at": now.isoformat(),
           "registration_sha256": reg["content_sha256"], "registered_at": reg["registered_at"],
           "pro_commit": _git(cfg.BASE_DIR), "status": "COLLECTING",
           "note": "RESEARCH / SHADOW ONLY - no effect on v9 selection, tips, stakes, thresholds, models or Telegram.",
           "coverage": {}, "primary": {}, "secondary": {}, "cells": [], "by_model_version": {}}
    if fs.empty:
        return rep
    d = fs.merge(st[[c for c in st.columns if c not in fs.columns or c == "row_id"]], on="row_id", how="left") if len(st) else fs.assign(settle_status="PENDING")
    d["week"] = pd.to_datetime(d["match_date"]).dt.strftime("%G-W%V")
    rep["coverage"] = {
        "first_sight_rows": int(len(d)), "fixtures": int(d["fixture_key"].nunique()),
        "by_league_market": {lg: {m: int(v) for m, v in r.items()} for lg, r in
                             d.groupby(["league", "market"]).size().unstack(fill_value=0).to_dict(orient="index").items()},
        "settled": int((d["settle_status"] == "SETTLED").sum()), "pending": int((d["settle_status"] == "PENDING").sum()),
        "void": int((d["settle_status"] == "VOID_NO_RESULT").sum()),
        "certified_closes": int((d.get("close_status") == "CERTIFIED_T30").sum()) if "close_status" in d else 0,
        "model_versions": sorted(d["model_version"].dropna().unique().tolist()),
        "first_scored_at": str(d["scored_at"].min()), "last_scored_at": str(d["scored_at"].max())}
    s = d[d["settle_status"] == "SETTLED"].copy()
    prior_dec = (prior or {}).get("primary", {})
    pvals = {}
    for h in reg["hypotheses"]["CONFIRMATORY"]:
        g = s[s["market"] == h["market"]].dropna(subset=[f"p_{h['arm']}", f"p_{h['baseline']}", "y"])
        r = {"hypothesis": h["text"], **(metrics(g, h["arm"], h["market"], h["baseline"]) if len(g) else {"n": 0, "matchdays": 0})}
        r["min_n"], r["min_matchdays"] = dec["primary"]["min_n"], dec["primary"]["min_matchdays"]
        r["ready"] = r["n"] >= r["min_n"] and r["matchdays"] >= r["min_matchdays"]
        rep["primary"][h["id"]] = r
        if r["ready"]:
            pvals[h["id"]] = r.get(f"p_one_sided_vs_{h['baseline']}")
    adj = _holm(pvals)
    for hid, r in rep["primary"].items():
        old = prior_dec.get(hid, {})
        if old.get("decision") in ("CONFIRMED", "NOT_CONFIRMED"):          # decided once, then frozen
            r["decision"], r["decision_at"], r["decision_snapshot"] = old["decision"], old["decision_at"], old.get("decision_snapshot")
            continue
        if not r["ready"]:
            r["decision"] = "COLLECTING"
            continue
        base = next(h["baseline"] for h in reg["hypotheses"]["CONFIRMATORY"] if h["id"] == hid)
        ci = r.get(f"dLL_vs_{base}_ci95") or [0, 0]
        ok = r[f"dLL_vs_{base}"] < 0 and ci[1] < 0 and adj.get(hid, 1) <= dec["primary"]["alpha_one_sided"]
        r["holm_p"] = adj.get(hid)
        r["decision"] = "CONFIRMED" if ok else "NOT_CONFIRMED"
        r["decision_at"] = now.isoformat()
        r["decision_snapshot"] = {"n": r["n"], "matchdays": r["matchdays"], "dLL": r[f"dLL_vs_{base}"], "ci95": ci}
    for m in reg["markets"]:
        g0 = s[s["market"] == m]
        sec = {}
        for arm in [x for x in arms_for(reg, m) if x != "MARKET"]:
            g = g0.dropna(subset=[f"p_{arm}", "p_MARKET", "y"])
            if g.empty:
                continue
            sec[arm] = {"vs_MARKET": metrics(g, arm, m, "MARKET"), "money": money(g, arm, m)}
            if arm != "CURRENT_V9_SERVED":
                sec[arm]["vs_CURRENT_V9_SERVED"] = metrics(g.dropna(subset=["p_CURRENT_V9_SERVED"]), arm, m, "CURRENT_V9_SERVED")
        rep["secondary"][m] = {"role": reg["markets"][m]["role"], "arms": sec,
                               "market_price_class": "GENUINE_FORWARD_TWO_SIDED only (no synthetic proxy rows in v1)"}
        for arm in [x for x in arms_for(reg, m) if x != "MARKET"]:
            g1 = g0.dropna(subset=[f"p_{arm}", "p_MARKET", "y"])
            for lg, gl in g1.groupby("league"):
                lean_first = gl[f"p_{arm}"] > gl["p_MARKET"]
                for side, gs in ((side_names(m)[0], gl[lean_first]), (side_names(m)[1], gl[~lean_first])):
                    if gs.empty:
                        continue
                    c = {"market": m, "league": lg, "side": side, "arm": arm, **metrics(gs, arm, m, "MARKET"),
                         **money(gs, arm, m)}
                    if arm != "CURRENT_V9_SERVED":
                        c["dLL_vs_CURRENT_V9_SERVED"] = round(float((ll(gs[f"p_{arm}"], gs["y"]) - ll(gs["p_CURRENT_V9_SERVED"], gs["y"])).mean()), 6)
                    c["eligible"] = c["n"] >= dec["cells"]["min_n"] and c["matchdays"] >= dec["cells"]["min_matchdays"]
                    rep["cells"].append(c)
    fam = {}
    for i, c in enumerate(rep["cells"]):
        if c["eligible"]:
            fam.setdefault((c["market"], c["arm"]), {})[i] = c.get("p_one_sided_vs_MARKET")
    for _, pv in fam.items():
        for i, q in bh(pv).items():
            rep["cells"][i]["bh_q"] = q
    for c in rep["cells"]:
        q = c.get("bh_q")
        c["label"] = ("DISCOVERY_CANDIDATE" if (q is not None and q <= dec["cells"]["bh_q"] and c["dLL_vs_MARKET"] < 0)
                      else "DISCOVERY_NULL" if c["eligible"] else "COLLECTING")
    for v, gv in s.groupby("model_version"):
        rep["by_model_version"][v] = {"n": int(len(gv)), "markets": {k: int(x) for k, x in gv["market"].value_counts().items()}}
    decided = [r.get("decision") for r in rep["primary"].values()]
    rep["status"] = "DECIDED" if decided and all(x in ("CONFIRMED", "NOT_CONFIRMED") for x in decided) else \
        "PARTLY_DECIDED" if any(x in ("CONFIRMED", "NOT_CONFIRMED") for x in decided) else "COLLECTING"
    return rep


def _md(rep: dict) -> str:
    L = [f"# Standard repair forward shadow - {rep['experiment_id']}", "",
         f"Generated {rep['generated_at']}. Phase **{rep['phase']}**. Status **{rep['status']}**.", "",
         rep["note"], "", "## Coverage", ""]
    cv = rep.get("coverage") or {}
    L.append(f"First-sight rows {cv.get('first_sight_rows', 0)} ({cv.get('fixtures', 0)} fixtures); settled "
             f"{cv.get('settled', 0)}, pending {cv.get('pending', 0)}, void {cv.get('void', 0)}; certified closes "
             f"{cv.get('certified_closes', 0)}; model versions {', '.join(cv.get('model_versions', [])) or '-'}.")
    L += ["", "## Pre-registered hypotheses (OU25, pooled 7 leagues)", "",
          "| id | hypothesis | n | matchdays | dLL | 95% CI | decision |", "|---|---|---|---|---|---|---|"]
    for hid, r in (rep.get("primary") or {}).items():
        k = next((x for x in r if x.startswith("dLL_vs_") and not x.endswith("ci95")), None)
        L.append(f"| {hid} | {r['hypothesis']} | {r.get('n', 0)} | {r.get('matchdays', 0)} | "
                 f"{r.get(k) if k else '-'} | {r.get(k + '_ci95') if k else '-'} | {r.get('decision')} |")
    L += ["", "Negative dLL = the arm's log loss is lower (better) than the baseline on the same rows. "
          "CI = matchday-week block bootstrap. Decisions are taken once, when the minimum N and matchdays "
          "are reached, then frozen. League x side cells are DISCOVERY only (BH within arm x market); a "
          "discovered cell needs its own new registration before it can mean anything.", ""]
    return "\n".join(L) + "\n"


def cmd_report(a) -> None:
    reg = R.load_registration()
    fs = pd.read_csv(FS) if FS.exists() else pd.DataFrame()
    st = pd.read_csv(SETTLED) if SETTLED.exists() else pd.DataFrame()
    prior = json.loads(REPORT_JSON.read_text(encoding="utf-8")) if REPORT_JSON.exists() else None
    rep = build_report(fs, st, reg, prior)
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    REPORT_MD.write_text(_md(rep), encoding="utf-8")
    print(f"report: status {rep['status']}; rows {rep['coverage'].get('first_sight_rows', 0)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.studies.standard_repair.shadow")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    t = sub.add_parser("train")
    t.add_argument("--v9-code", required=True)
    t.add_argument("--fd-dir", required=True)
    t.add_argument("--work", required=True)
    e = sub.add_parser("ledger-append")
    e.add_argument("--entry", required=True)
    ac = sub.add_parser("active")
    ac.add_argument("--field", required=True, choices=["release_tag", "v9_commit", "model_version", "sklearn"])
    for name in ("score", "settle"):
        s = sub.add_parser(name)
        s.add_argument("--v9-code", required=True)
        s.add_argument("--v9-data", required=True)
        s.add_argument("--work", required=True)
        if name == "score":
            s.add_argument("--models", required=True)
    sub.add_parser("report")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        reg = R.load_registration()
        print(f"{reg['experiment_id']} OK ({reg['content_sha256'][:12]}); versions {len(R.load_ledger()['versions'])}")
        return 0
    {"train": cmd_train, "ledger-append": cmd_ledger_append, "active": cmd_active, "score": cmd_score,
     "settle": cmd_settle, "report": cmd_report}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
