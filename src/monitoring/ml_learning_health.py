"""Is the ML system LEARNING? — a separate question from whether it is predicting.

    python -m src.monitoring.ml_learning_health [--write] [--strict]

WHY THIS EXISTS, stated plainly because it is the whole point. Every monitoring artifact in this
estate so far answers "did the pipeline run". None answers "did the models learn". Those come
apart completely, and the gap has been large:

  * v9's models last changed 2026-08-30. For 23 days predict ran every few minutes, tips went
    out, the dashboard updated, ledgers grew — and not one new match reached a model.
  * player_history.parquet's newest match is 2026-08-17. The collector ran daily, committed
    daily and reported success daily for 35 days while adding zero rows.
  * v11's movement study re-ran daily for four weeks on a frozen 9-day sample, producing
    byte-identical output, and therefore never even showed up as a change in git.

In all three the inference side was healthy and visibly so. A 30-day-old model makes confident
predictions every single day. INFERENCE HEALTH IS NOT LEARNING HEALTH, and conflating them is
what let each of these run for weeks.

THE STATES ARE DELIBERATELY NOT BINARY. "Broken" and "fine" cannot express the case that
actually matters — a pipeline that is working correctly and learning nothing because no football
has been played. So:

    PASS          new data arrived, training consumed it, a decision was recorded
    NO_NEW_DATA   nothing new to learn from. Correct and healthy — an international break
                  looks exactly like this and must not page anyone.
    TRAINING_DUE  new settled matches exist that the incumbent has never seen
    STALE         the training INPUT stopped advancing — collection is the problem
    FAILED        training ran and errored
    BLOCKED       training cannot run at all (missing artifact, missing gate, no record)

The distinction between NO_NEW_DATA and STALE is the one that would have caught every incident
above: both look like "nothing changed", and only one of them is fine.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import subprocess
from datetime import datetime, timezone, date
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

# A model older than this with new data available is not merely "due", it is a finding.
INCUMBENT_STALE_DAYS = 10
# Below this many new settled matches, retraining cannot be expected to change anything.
MIN_NEW_FOR_TRAINING = 25


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception:
        return ""


def _last_change(repo: Path, rel: str) -> str | None:
    """ISO date a tracked file's CONTENT last changed. None when unknown.

    Deliberately git, not mtime: `git checkout` resets mtime on every CI run, which has produced
    four separate silent failures in this estate. Callers must treat None as "unknown", never as
    "fresh" — the FPL cache bug was exactly that substitution.
    """
    out = _git(repo, "log", "-1", "--format=%cI", "--", rel)
    return out or None


def _age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (_utc() - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 86400
    except Exception:
        return None


def _fingerprint(d: pd.DataFrame) -> dict:
    """Dataset identity (§19). Answers 'what exact data trained model X'."""
    if d is None or d.empty:
        return {"rows": 0}
    dc = next((c for c in ("match_date", "date") if c in d.columns), None)
    dates = pd.to_datetime(d[dc], errors="coerce") if dc else None
    h = hashlib.sha256()
    h.update(str(len(d)).encode())
    if dates is not None and dates.notna().any():
        h.update(str(dates.max()).encode())
        h.update(str(dates.min()).encode())
    if "league" in d.columns:
        h.update(",".join(sorted(map(str, d["league"].dropna().unique()))).encode())
    return {
        "rows": int(len(d)),
        "latest_match": str(dates.max().date()) if dates is not None and dates.notna().any() else None,
        "earliest_match": str(dates.min().date()) if dates is not None and dates.notna().any() else None,
        "leagues": int(d["league"].nunique()) if "league" in d.columns else None,
        "fingerprint": h.hexdigest()[:16],
    }


def _settlements() -> pd.DataFrame:
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "settlements" / "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    return d[d["result"].isin(["WIN", "LOSS"]) & d["match_date"].notna()]


def assess(v9: Path) -> dict:
    """One verdict per model track, plus an estate roll-up."""
    now = _utc()
    settle = _settlements()
    checks: list[dict] = []

    # ── What the models are, and when each last actually changed ────────────────────────
    MODELS = {
        "standard":   "models/model_v9_standard.pkl",
        "new_format": "models/model_v9_newformat.pkl",
        "btts":       "models/model_v9_btts.pkl",
        "over15":     "models/model_v9_over15.pkl",
        "over35":     "models/model_v9_over35.pkl",
        "ht_over05":  "models/model_ht_over05.pkl",
        "props":      "models/model_player_goals.pkl",
    }
    # Training INPUTS, so STALE (collection stopped) is distinguishable from NO_NEW_DATA.
    INPUTS = {
        "standard":   "output/fd_history.parquet",
        "new_format": "output/fd_history.parquet",
        "btts":       "output/fd_history.parquet",
        "over15":     "output/fd_history.parquet",
        "over35":     "output/fd_history.parquet",
        "ht_over05":  "output/fd_history.parquet",
        "props":      "player_history.parquet",
    }

    # The learning record written by pipeline._train_one, if it has ever run.
    retrain_log = {}
    rl = v9 / "output" / "retrain_log.json"
    if rl.exists():
        try:
            retrain_log = json.loads(rl.read_text(encoding="utf-8"))
        except Exception:
            pass

    for name, rel in MODELS.items():
        model_iso = _last_change(v9, rel)
        model_age = _age_days(model_iso)
        exists = (v9 / rel).exists()

        # Training input freshness — the signal that separates STALE from NO_NEW_DATA.
        inp_rel = INPUTS[name]
        inp = v9 / inp_rel
        latest_input_match, input_age = None, None
        if inp.exists():
            try:
                col = "date"
                dd = pd.read_parquet(inp, columns=[col])
                md = pd.to_datetime(dd[col], errors="coerce").max()
                if pd.notna(md):
                    latest_input_match = str(md.date())
                    input_age = (date.today() - md.date()).days
            except Exception:
                pass

        # New settled matches the incumbent cannot have seen.
        new_since = None
        if not settle.empty and model_iso:
            try:
                cut = datetime.fromisoformat(model_iso.replace("Z", "+00:00"))
                sub = settle[settle["match_date"].dt.tz_localize("UTC") > cut] \
                    if settle["match_date"].dt.tz is None else settle[settle["match_date"] > cut]
                if name in ("standard", "new_format"):
                    sub = sub[sub["model_type"].astype(str) == name]
                new_since = int(sub["fixture_key"].nunique())
            except Exception:
                new_since = None

        # Did the last retrain record a DECISION for this track?
        latest_run = retrain_log.get("latest_run")
        entry = (retrain_log.get("runs", {}).get(latest_run) or {}).get(name) if latest_run else None

        # ── the verdict ────────────────────────────────────────────────────────────────
        if not exists:
            status, why = "BLOCKED", f"{rel} does not exist — nothing to compare a challenger to"
        elif input_age is not None and input_age > 14:
            status, why = ("STALE",
                           f"training INPUT stopped advancing: newest match in {inp_rel} is "
                           f"{latest_input_match}, {input_age}d ago. Collection is the problem, "
                           f"not training.")
        elif entry and entry.get("promoted") is False:
            status, why = ("PASS",
                           f"challenger trained and REJECTED — {entry.get('why', '')}. "
                           f"A rejection is a healthy learning outcome, not a failure.")
        elif entry and entry.get("promoted") is True:
            status, why = "PASS", f"challenger trained and promoted — {entry.get('why', '')}"
        elif new_since is not None and new_since < MIN_NEW_FOR_TRAINING:
            status, why = ("NO_NEW_DATA",
                           f"only {new_since} new settled fixture(s) since the incumbent was "
                           f"built — too few to learn from. Healthy.")
        elif model_age is not None and model_age > INCUMBENT_STALE_DAYS:
            status, why = ("TRAINING_DUE",
                           f"incumbent is {model_age:.0f}d old and "
                           f"{new_since if new_since is not None else '?'} new settled fixture(s) "
                           f"exist that it has never seen, with no decision recorded")
        else:
            status, why = "TRAINING_DUE", "new data available, no training decision on record"

        checks.append({
            "model": name, "status": status, "why": why,
            "model_artifact": rel,
            "incumbent_changed_at": model_iso,
            "incumbent_age_days": round(model_age, 1) if model_age is not None else None,
            "training_input": inp_rel,
            "training_input_latest_match": latest_input_match,
            "training_input_age_days": input_age,
            "new_settled_since_incumbent": new_since,
            "last_decision": entry,
        })

    order = ["BLOCKED", "FAILED", "STALE", "TRAINING_DUE", "NO_NEW_DATA", "PASS"]
    worst = next((s for s in order if any(c["status"] == s for c in checks)), "PASS")

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calc_version": CALC_VERSION,
        "worst": worst,
        "counts": {s: sum(1 for c in checks if c["status"] == s) for s in order
                   if any(c["status"] == s for c in checks)},
        "settlements_fingerprint": _fingerprint(settle),
        "last_genuine_learning_event": _last_learning_event(retrain_log),
        "checks": checks,
        # Stated in the artifact itself so no reader can mistake one for the other.
        "note": ("Learning health is NOT inference health. A 30-day-old model predicts "
                 "confidently every day. PASS here requires a recorded train/compare/decide "
                 "cycle, not a green workflow."),
    }


def _last_learning_event(retrain_log: dict) -> dict:
    """The §2 answer: when did a challenger last get trained, compared and decided on?"""
    runs = retrain_log.get("runs") or {}
    if not runs:
        return {"date": None,
                "evidence": "output/retrain_log.json has no runs — no challenger has ever been "
                            "trained, compared against an incumbent and had a decision recorded "
                            "in the production path."}
    latest = max(runs)
    decided = [m for m, v in runs[latest].items() if isinstance(v, dict) and "promoted" in v]
    return {"date": latest, "models_decided": sorted(decided),
            "evidence": f"{len(decided)} model(s) recorded a promote/reject decision on {latest}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", default=str(getattr(cfg, "V9_LOCAL", "../v9")))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when the worst state is STALE/FAILED/BLOCKED")
    a = ap.parse_args()

    rep = assess(Path(a.v9))
    print("=" * 100)
    print(f"ML LEARNING HEALTH — worst: {rep['worst']}   {rep['counts']}")
    print("=" * 100)
    ev = rep["last_genuine_learning_event"]
    print(f"  LAST GENUINE LEARNING EVENT: {ev.get('date') or 'NONE'}")
    print(f"    {ev.get('evidence')}")
    print()
    print(f"  {'model':<12}{'status':<14}{'incumbent':>11}{'input age':>11}{'new settled':>13}")
    for c in rep["checks"]:
        ia = "?" if c["incumbent_age_days"] is None else f"{c['incumbent_age_days']:.0f}d"
        ta = "?" if c["training_input_age_days"] is None else f"{c['training_input_age_days']}d"
        ns = "?" if c["new_settled_since_incumbent"] is None else c["new_settled_since_incumbent"]
        print(f"  {c['model']:<12}{c['status']:<14}{ia:>11}{ta:>11}{str(ns):>13}")
    print()
    for c in rep["checks"]:
        if c["status"] in ("STALE", "FAILED", "BLOCKED", "TRAINING_DUE"):
            print(f"  [{c['status']}] {c['model']}: {c['why']}")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = cfg.OUTPUT_DIR / "ml_learning_health.json"
        p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        print(f"\n[ml_health] wrote {p.name}")

    if a.strict and rep["worst"] in ("STALE", "FAILED", "BLOCKED"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
