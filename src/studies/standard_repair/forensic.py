"""STANDARD v9 FORENSIC REPAIR — Phase 1: data before models (owner brief 2026-10-28).

    python -m src.studies.standard_repair forensic rebuild   # frame (legacy + canonical) from a v9 checkout
    python -m src.studies.standard_repair forensic audit     # identity, provenance, prices -> data_quality.json
    python -m src.studies.standard_repair forensic all       # both; exits NON-ZERO on any integrity failure

Rule: NO MODEL RESEARCH STARTS UNTIL output/standard_repair/data_quality.json EXISTS AND IS CURRENT.
Phase-2 code calls `require_data_quality()` first.

REBUILD (reproducible from a clean checkout; nothing from a workstation):
  1. LEGACY frame   v9's own loader + feature builder, exactly as v9 trains (frame_build.py, run in a v9
                    checkout with the v9 interpreter); rows tagged with their source.
  2. ALIASES        identity.derive_aliases on the legacy frame: evidence-only club aliases v9 missed.
  3. CANONICAL frame the same build with the alias map applied after v9's canonicaliser, so rolling
                    features are recomputed over each club's WHOLE history.
  4. BENCHMARK frame canonical minus quarantined fixtures (identity not provable) -> frame_benchmark.parquet.
Inputs: V9_LOCAL (v9 checkout), the football-data raw files (FD_DIR, default Pro's committed fd_raw,
refreshed for the live season by the workflow), V9_PYTHON (default: this interpreter).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import fingerprint as FP
from src.studies.standard_repair import identity as ID
from src.studies.standard_repair import prices as PR
from src.studies.standard_repair import provenance as PV
from src.studies.standard_repair import trusted as TR
from src.studies.standard_repair.data import FD_CODES, FD_RAW

OUT = cfg.OUTPUT_DIR / "standard_repair"
REBUILD = FP.REBUILD
LEGACY, CANON = REBUILD / "legacy", REBUILD / "canonical"
ALIASES = OUT / "identity_aliases.json"
DQ = OUT / "data_quality.json"
HEALTH = OUT / "repair_health.json"
BET_LEAGUES = ("Championship", "League One", "League Two", "Bundesliga 2", "La Liga 2", "Ligue 2", "Serie B")
#: the rolling-form inputs without which a Standard row is a median-imputed guess (invariant 8)
REQUIRED = ["home_scored_last5", "away_scored_last5", "home_conceded_last5", "away_conceded_last5",
            "home_over25_last5", "away_over25_last5", "home_attack_str", "away_attack_str",
            "home_defense_str", "away_defense_str", "league_avg_goals"]


class IntegrityError(RuntimeError):
    """A Phase-1 check failed. The workflow must fail; never write a result over it."""


def _fd_dir() -> Path:
    return Path(os.getenv("FD_DIR") or FD_RAW)


def _run_build(out: Path, alias_map: Path | None = None, extra: list | None = None, v9: Path | None = None) -> dict:
    v9 = v9 or Path(os.getenv("V9_LOCAL") or cfg.V9_LOCAL)
    py = os.getenv("V9_PYTHON") or sys.executable
    script = Path(__file__).resolve().parent / "frame_build.py"
    cmd = [py, str(script), "--out", str(out), "--fd-dir", str(_fd_dir())]
    sha = os.getenv("V9_SHA", "")
    if sha:
        cmd += ["--v9-sha", sha]
    if alias_map:
        cmd += ["--alias-map", str(alias_map)]
    cmd += list(extra or [])
    env = dict(os.environ, PYTHONIOENCODING="utf-8", APIFOOTBALL_KEY="")
    r = subprocess.run(cmd, cwd=str(v9), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-4000:] + "\n" + r.stderr[-8000:])
        raise IntegrityError(f"frame build failed (exit {r.returncode}) in {v9}")
    return json.loads((out / "frame_manifest.json").read_text(encoding="utf-8"))


def rebuild() -> dict:
    LEGACY.mkdir(parents=True, exist_ok=True)
    CANON.mkdir(parents=True, exist_ok=True)
    m_leg = _run_build(LEGACY)
    leg = pd.read_parquet(LEGACY / "frame.parquet")
    al = ID.derive_aliases(leg)                      # all leagues (NF side models need it in Phase 2)
    ID.write_aliases(al, ALIASES)
    m_can = _run_build(CANON, ALIASES)
    can = pd.read_parquet(CANON / "frame.parquet")
    clean, q = ID.quarantine(can)
    clean.to_parquet(CANON / "frame_benchmark.parquet", index=False)
    OUT.mkdir(parents=True, exist_ok=True)
    qs = q[q["track"].astype(str) == "standard"] if "track" in q else q
    qs[["date", "league", "season", "home_team", "away_team", "home_goals", "away_goals", "row_source"]] \
        .assign(reason="identity collision or duplicate key — not provable") \
        .to_csv(OUT / "identity_quarantine.csv", index=False)
    # the benchmark manifest IS the canonical manifest (+ the quarantine)
    m_can["quarantined_standard_rows"] = int(len(qs))
    (CANON / "frame_manifest.json").write_text(json.dumps(m_can, indent=1, default=str), encoding="utf-8")
    return {"legacy": {k: m_leg.get(k) for k in ("rows_standard", "standard_frame_key_hash", "mode")},
            "canonical": {k: m_can.get(k) for k in ("rows_standard", "standard_frame_key_hash", "alias_rows_removed")},
            "aliases": sum(len(v) for v in al["map"].values()), "quarantined_standard_rows": int(len(qs))}


def rebuild_repaired() -> dict:
    """Frames for the V9_REPAIRED arms, built INSIDE the repaired v9 checkout (V9_REPAIRED_LOCAL =
    R1's recipe branch) with the same loader inputs, Pro's alias map handed to R1's identity repair,
    and each market-feature mode. Skipped (and reported) when no repaired checkout is configured."""
    rl = os.getenv("V9_REPAIRED_LOCAL")
    if not rl or not (Path(rl) / "src" / "standard_repair.py").exists():
        return {"status": "SKIPPED_NO_REPAIRED_CHECKOUT"}
    out = {}
    for pm in ("none", "asof", "closing"):
        m = _run_build(REBUILD / f"repaired_{pm}", None,
                       ["--recipe", "v9_repaired", "--price-mode", pm, "--identity-map", str(ALIASES),
                        "--v9-sha", os.getenv("V9_REPAIRED_SHA", "")], v9=Path(rl))
        out[pm] = {k: m.get(k) for k in ("rows_standard", "standard_frame_key_hash")}
    return out


def load_benchmark_frame() -> tuple[pd.DataFrame, dict]:
    p = CANON / "frame_benchmark.parquet"
    if not p.exists():
        raise IntegrityError("benchmark frame missing — run `forensic rebuild` (never a workstation copy)")
    return pd.read_parquet(p), json.loads((CANON / "frame_manifest.json").read_text(encoding="utf-8"))


def require_data_quality() -> dict:
    """Gate for Phase 2: data_quality.json must exist, pass, and match the current benchmark frame."""
    if not DQ.exists():
        raise IntegrityError("NO MODEL RESEARCH: output/standard_repair/data_quality.json does not exist")
    dq = json.loads(DQ.read_text(encoding="utf-8"))
    if dq.get("status") != "PASS":
        raise IntegrityError(f"NO MODEL RESEARCH: data_quality status {dq.get('status')}")
    fr, man = load_benchmark_frame()
    now = FP.current(fr, man, data_cutoff=dq.get("data_cutoff"))
    cmp = FP.compare(dq.get("fingerprint"), now)
    if cmp["status"] == "STALE":
        raise IntegrityError(f"NO MODEL RESEARCH: data_quality is STALE ({cmp['mismatched']})")
    return dq


# ── audit ────────────────────────────────────────────────────────────────────────────────────────
FD_SEASONS = ("2223", "2324", "2425", "2526", "2627")


def _fd_missing() -> list[str]:
    """football-data season files the price audit needs and does not have (each one is a league-season
    whose OU2.5 rows cannot be labelled pre-match vs closing). E2_2324 (League One 2023/24) was missing
    from Pro's committed fd_raw on 2026-10-28; the workflow downloads it."""
    d = _fd_dir()
    return [f"{c}_{s}.csv" for c in FD_CODES.values() for s in FD_SEASONS if not (d / f"{c}_{s}.csv").exists()]


def _v9_file(rel: str) -> Path:
    return Path(os.getenv("V9_LOCAL") or cfg.V9_LOCAL) / rel


def _first_sight(leagues) -> pd.DataFrame:
    from src.data import season_store as store
    ms = store.read("model_snapshots")
    if ms.empty:
        return ms
    ms = ms[(ms["model_type"] == "standard") & ms["market"].isin(["OU25", "BTTS", "OU15"]) & ms["league"].isin(leagues)]
    fx = store.read("fixtures").sort_values("observed_at").drop_duplicates("fixture_key", keep="last")[["fixture_key", "kickoff_utc"]]
    ms = ms.merge(fx, on="fixture_key", how="inner")
    ms["ts"] = pd.to_datetime(ms["observed_at"], utc=True, errors="coerce")
    ms["ko"] = pd.to_datetime(ms["kickoff_utc"], utc=True, errors="coerce")
    ms = ms[ms["ts"] < ms["ko"]].sort_values("ts")
    return ms.drop_duplicates(["fixture_key", "market"], keep="first")


def audit(strict: bool = True) -> dict:
    fails: list[str] = []
    leg = pd.read_parquet(LEGACY / "frame.parquet")
    pre = pd.read_parquet(LEGACY / "raw_precanon_standard.parquet")
    can, man = load_benchmark_frame()
    can_full = pd.read_parquet(CANON / "frame.parquet")
    al = json.loads(ALIASES.read_text(encoding="utf-8"))
    serving = list(man.get("serving_feature_cols") or [])
    if not serving:
        fails.append("serving feature list unreadable from models/model_v9_standard.pkl")
    std = can[can["track"].astype(str) == "standard"].copy()
    std["date"] = pd.to_datetime(std["date"]).dt.normalize()
    leagues = sorted(std["league"].unique())

    # identity
    id_leg = ID.audit(leg, pre)
    id_can_full = ID.audit(can_full)
    id_bench = ID.audit(can)
    leak_leg = ID.rolling_order_leak(leg)
    leak_can = ID.rolling_order_leak(can_full)
    leak_rows = set(leak_can.pop("future_rows_index"))
    leak_leg.pop("future_rows_index")
    if id_bench["exact_duplicate_fixtures"] or id_bench["same_day_collision_fixtures"]:
        fails.append(f"benchmark frame still has identity collisions: {id_bench['exact_duplicate_fixtures']} dup, "
                     f"{id_bench['same_day_collision_fixtures']} same-day")

    # provenance
    cov = PV.coverage(std, serving)
    pred = PV.source_predictability(std, serving)

    # prices
    fd = PR.fd_ou25_rows(_fd_dir(), FD_CODES)
    lab = PR.label_frame_ou25(std, fd, al.get("map"))
    if (lab["entry_class"].dropna() != "FD_PREMATCH_APPROX").any():
        fails.append("an entry price is not FD_PREMATCH_APPROX")
    from src.data import season_store as store
    bo = store.read("book_odds_snapshots")
    fwd, fwd_meta = PR.forward_coverage(bo, set(leagues)) if not bo.empty else (pd.DataFrame(), {})
    capp = _v9_file("output/standard_sidemarket_odds_history.csv")
    cap, cap_meta = PR.v9_capture_coverage(capp, set(leagues)) if capp.exists() else (pd.DataFrame(), {})
    fb = PR.legacy_backtest_fallbacks(_v9_file("output"), set(leagues))
    fh_p = _v9_file("output/feature_health.json")
    fh = json.loads(fh_p.read_text(encoding="utf-8")) if fh_p.exists() else {}

    # forward first sight
    fs = _first_sight(leagues)
    t_set = pd.Timestamp(TR.trusted_from("STANDARD_LIVE_SETTLEMENT_AND_ENTRY_PRICE"))
    t_inp = pd.Timestamp(TR.trusted_from("STANDARD_SERVED_MODEL_INPUTS"))

    fp = FP.current(can, man)
    data_cutoff = fp["data_cutoff"]

    per = {}
    for lg in leagues:
        g = std[std["league"] == lg]
        lb = lab[lab["league"] == lg]
        serv = [c for c in serving if c in g.columns]
        req_missing = g[REQUIRED].isna().any(axis=1)
        fcov = fwd[fwd["league"] == lg].set_index("market").to_dict("index") if len(fwd) else {}
        ccov = cap[cap["league"] == lg] if len(cap) else pd.DataFrame()
        fsl = fs[fs["league"] == lg] if len(fs) else pd.DataFrame()
        il, ib = id_leg["per_league"].get(lg, {}), id_bench["per_league"].get(lg, {})

        def cap_n(mk, timing=None, col="two_sided"):
            if ccov.empty:
                return 0
            x = ccov[ccov["mkt"] == mk]
            if timing:
                x = x[x["timing"] == timing]
            return int(x[col].sum())
        per[lg] = {
            "bet_league": lg in BET_LEAGUES,
            "rows": int(len(g)),
            "date_range": [str(g["date"].min().date()), str(g["date"].max().date())],
            "rows_by_source": g["row_source"].value_counts().to_dict(),
            "fixture_duplicates_legacy": il.get("exact_duplicate_fixtures", 0),
            "alias_collision_fixtures_legacy": il.get("same_day_collision_fixtures", 0),
            "alias_collision_share_legacy": il.get("same_day_collision_rows_share", 0),
            "aliases_resolved": len(al["map"].get(lg, {})),
            "alias_map": al["map"].get(lg, {}),
            "alias_conflicts_unresolved": [r for r in al.get("rejected_pairs", []) if r["league"] == lg],
            "score_conflicts_legacy": il.get("score_conflicts", 0),
            "fixture_duplicates_benchmark": ib.get("exact_duplicate_fixtures", 0),
            "alias_collision_fixtures_benchmark": ib.get("same_day_collision_fixtures", 0),
            "quarantined_rows": int(id_can_full["per_league"].get(lg, {}).get("same_day_collision_fixtures", 0)),
            "rolling_window_future_leak_sides_legacy": leak_leg["per_league"].get(lg, {}).get("future", 0),
            "rolling_window_future_leak_sides_canonical": leak_can["per_league"].get(lg, {}).get("future", 0),
            "target_completeness": {t: round(float(g[t].notna().mean()), 4) for t in ("over25", "btts", "over15")},
            "serving_feature_completeness": round(float(g[serv].notna().mean().mean()), 4) if serv else None,
            "serving_feature_min_completeness": (lambda s: {"feature": s.idxmin(), "share": round(float(s.min()), 4)})(g[serv].notna().mean()) if serv else None,
            "degraded_feature_rows": int(req_missing.sum()),
            "degraded_feature_share": round(float(req_missing.mean()), 4),
            "parity": {"status": "PENDING_R1_feature_parity_csv",
                       "live_constant_features_v9": (fh.get("models", {}).get("standard", {}) or {}).get("constant", []),
                       "live_feature_health_ts": fh.get("ts")},
            "price_coverage": {
                "OU25_entry_real_FD_PREMATCH_APPROX": round(float(lb["entry_over25"].notna().mean()), 4),
                "OU25_close_FD_CLOSING": round(float(lb["close_over25"].notna().mean()), 4),
                "OU25_frame_price_class": lb["frame_price_class"].value_counts().to_dict(),
                "BTTS_real_historical_two_sided_fixtures_backfill_date_only": cap_n("BTTS", "BACKFILL_DATE_ONLY"),
                "BTTS_real_forward_two_sided_fixtures_v9_capture": cap_n("BTTS", "TIMESTAMPED"),
                "OU15_real_forward_two_sided_fixtures_v9_capture": cap_n("OU15", "TIMESTAMPED"),
                "OU35_real_forward_two_sided_fixtures_v9_capture": cap_n("OU35", "TIMESTAMPED"),
                "frame_side_price_share": {m: round(float(g[c].notna().mean()), 4) for m, c in PR.FRAME_SIDE_COLS.items()},
                "forward_pro_snapshots": {m: {k: (int(v) if isinstance(v, (int, np.integer)) else v) for k, v in d.items()}
                                          for m, d in fcov.items()},
            },
            "price_source": {"OU25_entry": "football-data Avg>2.5 (else B365>2.5) — FD_PREMATCH_APPROX",
                             "OU25_close": "football-data AvgC>2.5 — FD_CLOSING (evaluation only)",
                             "OU25_frame_feature_price": "v9 _pick_odds prefers AvgC>2.5 -> CLOSING (P0 #5)",
                             "BTTS_OU15": "no football-data column for these leagues; real prices only from v9 captures / Pro snapshots"},
            "timing_class": {"historical_OU25": "FD_PREMATCH_APPROX (entry) / FD_CLOSING (close)",
                             "historical_side_markets": "BACKFILL_DATE_ONLY (midnight stamp, timing unknown) — not certifiable",
                             "forward": "timestamped snapshots (Pro book_odds_snapshots, v9 captures)"},
            "certified_t30_close": {m: {"fixtures": int(d.get("fixtures", 0)), "certified": int(d.get("certified_t30_close", 0)),
                                        "share": float(d.get("certified_t30_close_share", 0.0))} for m, d in fcov.items()},
            "post_fix_first_sight_rows": {
                "since_settlement_trusted": {m: int(((fsl["market"] == m) & (fsl["ts"] >= t_set)).sum()) for m in ("OU25", "BTTS", "OU15")} if len(fsl) else {},
                "since_model_inputs_trusted": {m: int(((fsl["market"] == m) & (fsl["ts"] >= t_inp)).sum()) for m in ("OU25", "BTTS", "OU15")} if len(fsl) else {},
                "forward_phase": "PRE_REPAIR_FORWARD (no STD-V9R registration yet)"},
            "btts_1h_rows_removed": {"pro_snapshots": fwd_meta.get("btts_1h_rows_removed", {}).get(lg, 0),
                                     "v9_captures": cap_meta.get("btts_1h_rows_removed", {}).get(lg, 0)},
            "legacy_backtest_fallback_rows": {m: v["by_league_fallback"].get(lg, 0) for m, v in fb.items()},
        }

    status = "PASS" if not fails else "FAIL"
    dq = {
        "title": "Standard v9 forensic repair — data quality (Phase 1)",
        "status": status, "failures": fails,
        "rule": "no model research starts until this file exists with status PASS and a CURRENT fingerprint",
        "data_cutoff": data_cutoff,
        "frame": {"build": man.get("frame_build_version"), "mode": man.get("mode"), "v9_commit": man.get("v9_commit"),
                  "legacy_rows_standard": int((leg["track"].astype(str) == "standard").sum()),
                  "canonical_rows_standard": int((can_full["track"].astype(str) == "standard").sum()),
                  "benchmark_rows_standard": int(len(std)),
                  "alias_rows_removed": man.get("alias_rows_removed"),
                  "quarantined_standard_rows": man.get("quarantined_standard_rows"),
                  "fd_files_missing": man.get("fd_files_missing", []),
                  "fd_raw_files_missing_for_price_audit": _fd_missing()},
        "identity": {"legacy_v9_frame": {k: v for k, v in id_leg.items() if k not in ("per_league", "thin_club_seasons")},
                     "canonical_before_quarantine": {k: id_can_full[k] for k in ("exact_duplicate_fixtures", "same_day_collision_fixtures", "score_conflicts")},
                     "benchmark": {k: id_bench[k] for k in ("exact_duplicate_fixtures", "same_day_collision_fixtures", "score_conflicts")},
                     "aliases_resolved_total": sum(len(v) for v in al["map"].values()),
                     "alias_pairs_rejected": al.get("rejected_pairs", []),
                     "post_fix_canonical_proof": ("benchmark frame = v9 loader at v9_commit (includes v9's 6c80672f club "
                                                  "canonicaliser) + Pro evidence-based alias map + quarantine; exact "
                                                  "duplicates and same-day club collisions in the benchmark are both 0"
                                                  if not fails else "FAILED"),
                     "rolling_order_leak_legacy": leak_leg, "rolling_order_leak_canonical": leak_can},
        "provenance": {"source_predictability": pred,
                       "rows_by_source": std["row_source"].value_counts().to_dict(),
                       "season_label_conventions": sorted(std["season"].astype(str).unique().tolist()),
                       "decay_weight_by_season": std.groupby(std["season"].astype(str))["decay_weight"].first().to_dict()
                       if "decay_weight" in std else {}},
        "prices": {"fallback_constants": PR.FALLBACK_CONSTANTS,
                   "legacy_backtest_fallbacks": fb,
                   "btts_1h_filter": {"rule": f"BTTS YES > {PR.BTTS_YES_1H_MAX} removed on read",
                                      "pro_snapshots": fwd_meta, "v9_captures": cap_meta},
                   "ou25_frame_price_class_all": lab["frame_price_class"].value_counts().to_dict(),
                   "ou25_frame_price_equals_closing_share_where_both_known":
                       round(float((lab["frame_price_class"].isin(["FD_CLOSING"])).sum() /
                                   max(1, lab["frame_price_class"].isin(["FD_CLOSING", "FD_PREMATCH_APPROX", "FD_CLOSING_EQ_PREMATCH"]).sum())), 4),
                   "entry_ne_closing_fields": True,
                   "min_books_certified_close": PR.MIN_BOOKS},
        "trusted_from": TR.table(),
        "per_league": per,
    }
    dq = FP.stamp_obj(dq, fp)
    OUT.mkdir(parents=True, exist_ok=True)
    DQ.write_text(json.dumps(dq, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    FP.stamp_csv(cov, fp).to_csv(OUT / "source_coverage.csv", index=False)
    pc = lab.groupby("league").agg(rows=("league", "size"), fd_matched=("fd_matched", "mean"),
                                   entry_real=("entry_over25", lambda x: x.notna().mean()),
                                   close_real=("close_over25", lambda x: x.notna().mean())).round(4).reset_index()
    if len(fwd):
        pc = pc.merge(fwd.pivot_table(index="league", columns="market", values="certified_t30_close_share").add_prefix("fwd_t30_cert_").reset_index(), on="league", how="left")
    FP.stamp_csv(pc, fp).to_csv(OUT / "price_coverage.csv", index=False)
    write_health(fp)
    if fails and strict:
        raise IntegrityError("; ".join(fails))
    return dq


# ── health ──────────────────────────────────────────────────────────────────────────────────────
def write_health(now: dict | None = None) -> dict:
    """repair_health.json: freshness of every Standard repair output vs the current fingerprint."""
    if now is None:
        try:
            fr, man = load_benchmark_frame()
        except IntegrityError as e:
            # the rebuild itself failed: nothing on disk can be called current
            h = {"STANDARD_REPAIR_BENCHMARK": "STALE", "DATA_QUALITY": "STALE",
                 "reason": f"benchmark frame could not be rebuilt in this run: {e}",
                 "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                 "rule": "STALE or MISSING must never be shown as current; the dashboard shows the status verbatim"}
            OUT.mkdir(parents=True, exist_ok=True)
            HEALTH.write_text(json.dumps(h, indent=1, default=str), encoding="utf-8")
            return h
        now = FP.current(fr, man)
    arts = {}
    for name in ("data_quality.json", "repaired_benchmark.json"):
        p = OUT / name
        if not p.exists():
            arts[name] = {"status": "MISSING"}
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        # compare at the output's own cutoff
        fr, man = load_benchmark_frame()
        # the declared imputer / recipe NAME comes from the output; its code hash is recomputed now
        sfp = obj.get("fingerprint") or {}
        nowc = FP.current(fr, man, data_cutoff=obj.get("data_cutoff"),
                          imputer_version=sfp.get("imputer_version"), model_recipe_version=sfp.get("model_recipe_version"))
        arts[name] = {**FP.compare(obj.get("fingerprint"), nowc), "generated_at": obj.get("generated_at"),
                      "data_cutoff": obj.get("data_cutoff"), "output_status": obj.get("status")}
    pre = OUT / "pre_repair" / "MANIFEST.json"
    bench = arts.get("repaired_benchmark.json", {})
    overall = ("STALE" if bench.get("status") in ("STALE", "MISSING") else bench.get("status"))
    job = os.getenv("JOB_STATUS", "success").lower()
    if job != "success":
        # this run failed somewhere: whatever is on disk was NOT produced by a passing run
        overall = "STALE"
        for a in arts.values():
            if a.get("status") in ("CURRENT", "BEHIND"):
                a["status"], a["reason"] = "STALE", f"the run that should have refreshed it ended {job}"
    h = {"STANDARD_REPAIR_BENCHMARK": overall, "run_status": job,
         "DATA_QUALITY": arts.get("data_quality.json", {}).get("status"),
         "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
         "artifacts": arts, "current_fingerprint": now,
         "pre_repair_outputs": "FROZEN (see output/standard_repair/pre_repair/MANIFEST.json)" if pre.exists() else "NOT_FROZEN",
         "rule": "STALE or MISSING must never be shown as current; the dashboard shows the status verbatim"}
    OUT.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(json.dumps(h, indent=1, default=str), encoding="utf-8")
    return h


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "all"
    if cmd in ("rebuild", "all"):
        print(json.dumps(rebuild(), indent=1, default=str))
    if cmd in ("audit", "all"):
        dq = audit(strict=True)
        print(json.dumps({"status": dq["status"], "data_cutoff": dq["data_cutoff"],
                          "identity": dq["identity"]["benchmark"]}, indent=1, default=str))
    if cmd in ("rebuild-repaired", "all"):
        print(json.dumps(rebuild_repaired(), indent=1, default=str))
    if cmd == "health":
        print(json.dumps(write_health()["STANDARD_REPAIR_BENCHMARK"]))
    return 0
