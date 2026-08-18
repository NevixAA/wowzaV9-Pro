"""
Experiment provenance and the canonical system registry.
=======================================================
Prompt 1 sections 12 and 20.

Section 12 exists because of a specific class of unfalsifiable claim: a number in a chat
message or a CSV filename, with no record of which code produced it, on which rows, under which
odds policy, or with which thresholds. v9's backtest outputs are exactly that — a
`backtest_results_standard.csv` whose provenance is "whatever main looked like when someone ran
it". You cannot re-derive it, and you cannot tell whether a later run differs because the model
changed or because the data did.

Every experiment therefore gets a directory whose contents fully determine the result:

    experiments/<experiment_id>/
        manifest.json      what was run: git_sha, model_sha, date ranges, row counts,
                           validation type, odds policy, feature/config/threshold hashes
        metrics.json       what came out, market-relative first
        by_league.csv      per-segment, always with n
        calibration.csv    reliability table
        bets.parquet       the row-level bets, so every aggregate can be recomputed

Section 20's output/system_registry.json is the single machine-readable statement of what is
true in production right now — the file a dashboard, the notifier, the deployment gate and the
health monitor should all read instead of each deriving their own answer and disagreeing.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import pro_config as cfg


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_sha() -> str:
    import os
    env = os.getenv("GITHUB_SHA")
    if env:
        return env[:12]
    try:
        r = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=cfg.BASE_DIR,
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "unknown"


def experiment_id(*, name: str, git: str, config_hash: str, when: str | None = None) -> str:
    """Deterministic given its inputs, so the SAME experiment re-run produces the SAME id and a
    genuinely different one cannot collide. The timestamp is an input rather than being read
    here, so a caller can reproduce an id exactly."""
    stamp = when or _now()
    raw = f"{name}|{git}|{config_hash}|{stamp}"
    return f"{name}-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


@dataclass
class ExperimentManifest:
    experiment_id: str
    name: str
    created_at: str = field(default_factory=_now)
    git_sha: str = field(default_factory=git_sha)
    model_sha: str = ""
    model_id: str = ""
    market: str = ""
    scope: str = ""

    validation_type: str = ""            # chronological_4block | oof_stacking | ...
    odds_policy: str = "REAL_ONLY"
    train_start: str = ""
    train_end: str = ""
    calibration_start: str = ""
    calibration_end: str = ""
    meta_start: str = ""
    meta_end: str = ""
    holdout_start: str = ""
    holdout_end: str = ""
    rows: dict[str, int] = field(default_factory=dict)

    feature_manifest_hash: str = ""
    config_hash: str = ""
    threshold_hash: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Experiment:
    """Writes one immutable experiment directory.

    Immutable on purpose: `save()` refuses to overwrite an existing manifest. An experiment
    whose contents can be edited after the fact is not evidence, and quietly re-running one
    under the same id is how a number loses its meaning.
    """

    def __init__(self, manifest: ExperimentManifest, *, root: Path | None = None) -> None:
        self.manifest = manifest
        self.dir = (root or (cfg.BASE_DIR / "experiments")) / manifest.experiment_id

    def save(
        self,
        *,
        metrics: dict,
        by_league: pd.DataFrame | None = None,
        calibration: pd.DataFrame | None = None,
        bets: pd.DataFrame | None = None,
        overwrite: bool = False,
    ) -> Path:
        mf = self.dir / "manifest.json"
        if mf.exists() and not overwrite:
            raise FileExistsError(
                f"{mf} already exists. Experiments are immutable — re-running under the same id "
                f"would silently change what a recorded number means. Create a new experiment."
            )
        self.dir.mkdir(parents=True, exist_ok=True)
        mf.write_text(json.dumps(self.manifest.to_dict(), indent=2, sort_keys=True,
                                 default=str), encoding="utf-8")
        (self.dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True, default=str), encoding="utf-8")
        if by_league is not None and not by_league.empty:
            by_league.to_csv(self.dir / "by_league.csv", index=False)
        if calibration is not None and not calibration.empty:
            calibration.to_csv(self.dir / "calibration.csv", index=False)
        if bets is not None and not bets.empty:
            # Parquet, not CSV: these are the rows every aggregate is recomputed from, so dtype
            # fidelity matters more than being readable in a text editor.
            bets.to_parquet(self.dir / "bets.parquet", index=False)
        return self.dir

    @staticmethod
    def load(path: Path) -> tuple[ExperimentManifest, dict]:
        p = Path(path)
        mf = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((p / "metrics.json").read_text(encoding="utf-8"))
        return ExperimentManifest(**mf), metrics

    @staticmethod
    def index(root: Path | None = None) -> pd.DataFrame:
        """Every recorded experiment, newest first."""
        r = root or (cfg.BASE_DIR / "experiments")
        rows = []
        for d in sorted(Path(r).glob("*/manifest.json")):
            try:
                mf = json.loads(d.read_text(encoding="utf-8"))
                met = {}
                mp = d.parent / "metrics.json"
                if mp.exists():
                    met = json.loads(mp.read_text(encoding="utf-8"))
                rows.append({**mf, **{f"metric_{k}": v for k, v in met.items()
                                      if not isinstance(v, (dict, list))}})
            except Exception:
                continue
        return (pd.DataFrame(rows).sort_values("created_at", ascending=False)
                .reset_index(drop=True) if rows else pd.DataFrame())


def write_system_registry(
    *,
    registry_table: pd.DataFrame | None = None,
    store_stats: dict | None = None,
    drift_health: dict | None = None,
    collect_health: dict | None = None,
    path: Path | None = None,
) -> Path:
    """output/system_registry.json — Prompt 1 section 20.

    The point is that there is ONE answer to "what is live, on what data, how healthy". v9 has
    the same question answered separately by the dashboard, the notifier and the summaries, and
    they have disagreed. Consumers should read this rather than re-deriving.
    """
    p = path or (cfg.OUTPUT_DIR / "system_registry.json")
    live = []
    if registry_table is not None and not registry_table.empty and "status" in registry_table:
        live = (registry_table.loc[registry_table["status"] == "LIVE"]
                .to_dict("records"))

    payload = {
        "generated_at": _now(),
        "git_sha": git_sha(),
        "season": cfg.season_label(),
        "pro_may_notify": cfg.PRO_MAY_NOTIFY,
        "pro_may_stake": False,
        "live_models": live,
        "n_live_models": len(live),
        "season_store": store_stats or {},
        "feature_health": drift_health or {},
        "collect_health": collect_health or {},
        # Stated explicitly so no consumer has to infer it from the absence of something.
        "deployment_note": (
            "Season 2026/27 is a data-collection and shadow season. Pro does not stake and "
            "does not notify. Signal tier and deployment mode are independent: a SNIPER may be "
            "PAPER."
        ),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return p
