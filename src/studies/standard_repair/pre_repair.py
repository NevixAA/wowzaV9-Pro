"""FREEZE the pre-repair Standard results as PRE_REPAIR / NOT FINAL (owner brief 2026-10-28, P0).

The 2026-10-26 Standard repair study (results.json, ablation.json, scorecard, registry) concluded "no
robust edge over market". The forensic audit found defects in the data and pipeline it ran on, so
that conclusion is NOT FINAL and is not proof of no edge. It is also not deleted or edited: this copies
every pre-repair output, byte for byte, to output/standard_repair/pre_repair/ and writes MANIFEST.json
with each file's sha256, the Pro commit it was taken from, and its status. The originals stay where
they are (the weekly loop keeps refreshing the PRE_REPAIR_FORWARD scorecard there), so the frozen copy
is the auditable record; tests/test_standard_forensic_repair.py proves it has not changed.

v9's output/backtest_by_league_standard.csv is recorded here as LEGACY_BACKTEST_UNVERIFIED with its
hash and content (v9 is read-only to Pro): neither its positive nor its negative leagues are truth.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "standard_repair"
REG = cfg.REGISTRY_DIR / "standard_repair"
FROZEN = OUT / "pre_repair"
FILES = [OUT / n for n in ("results.json", "results.csv", "ablation.json", "scorecard.json", "scorecard.csv",
                           "scorecard_history.jsonl", "forward_first_sight.csv", "WEEKLY.md",
                           "monthly_2026-10.json", "monthly_2026-10.md")] + \
        [REG / "experiments.json", REG / "journey.jsonl"]
STATUS = "PRE_REPAIR"
NOTE = ("NOT FINAL. Produced before the 2026-10-28 forensic repair (batch-median imputation, closing-price "
        "feature, train/serve skew, residual club aliases, pooled side models, meta-evaluation leakage). "
        "Not proof of no edge; not proof of edge.")


def _sha(p: Path) -> str:
    # newline-normalised so a CRLF checkout of the same bytes verifies identically
    return hashlib.sha256(p.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def freeze(force: bool = False) -> dict:
    man_p = FROZEN / "MANIFEST.json"
    if man_p.exists() and not force:
        return json.loads(man_p.read_text(encoding="utf-8"))          # write-once
    FROZEN.mkdir(parents=True, exist_ok=True)
    pro_sha = subprocess.run(["git", "-C", str(cfg.BASE_DIR), "rev-parse", "HEAD"], capture_output=True,
                             text=True).stdout.strip()
    entries = []
    for p in FILES:
        if not p.exists():
            continue
        dst = FROZEN / (("registry__" if p.parent == REG else "") + p.name)
        shutil.copyfile(p, dst)
        entries.append({"original": str(p.relative_to(cfg.BASE_DIR)).replace("\\", "/"),
                        "frozen_copy": str(dst.relative_to(cfg.BASE_DIR)).replace("\\", "/"),
                        "sha256": _sha(dst), "status": STATUS})
    legacy = {}
    lp = Path(cfg.V9_LOCAL) / "output" / "backtest_by_league_standard.csv"
    if lp.exists():
        legacy = {"path": "v9:output/backtest_by_league_standard.csv", "sha256": _sha(lp),
                  "status": "LEGACY_BACKTEST_UNVERIFIED",
                  "note": "closing-price entries, batch-median features, threshold-selected; use neither sign as truth",
                  "content": pd.read_csv(lp).to_dict("records")}
    man = {"frozen_at": pd.Timestamp.now(tz="UTC").isoformat(), "pro_commit": pro_sha, "status": STATUS,
           "note": NOTE, "files": entries, "legacy_v9_backtest": legacy}
    man_p.write_text(json.dumps(man, indent=1, default=str), encoding="utf-8")
    return man


def verify() -> list[str]:
    """Names of frozen files whose bytes no longer match the manifest (empty = intact)."""
    man = json.loads((FROZEN / "MANIFEST.json").read_text(encoding="utf-8"))
    bad = []
    for e in man["files"]:
        p = cfg.BASE_DIR / e["frozen_copy"]
        if not p.exists() or _sha(p) != e["sha256"]:
            bad.append(e["frozen_copy"])
    return bad
