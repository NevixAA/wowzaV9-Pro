"""
Import watermarks — incremental capture for v9's append-only artifacts.
======================================================================
v9's artifacts come in two flavours and they need opposite treatment:

* **Current-state files** (`predictions.csv`) are overwritten every 5 minutes. Pro must
  re-capture the WHOLE file every run — each capture is one point on the model's path toward
  kickoff, and Prompt 2 section 7 requires all of them.

* **Append-only histories** (`standard_odds_history.csv`, `newformat_odds_*.csv`) only ever
  grow. Re-importing them wholesale each run duplicates everything: 39,685 rows per run at 12
  runs/day is ~170M rows over a season, all of it redundant.

So the histories are imported past a watermark. The watermark is the max source timestamp
already stored, kept in a small committed JSON so it survives across CI runs.

Deliberately conservative: the filter is `>` on the recorded high-water mark, and the mark
only advances after a successful write. A crash re-imports a little, never skips.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg

_FILE = cfg.OUTPUT_DIR / "import_watermarks.json"


def load() -> dict[str, str]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(source: str) -> str:
    return load().get(source, "")


def advance(source: str, value: str) -> None:
    """Move the mark forward only. Never backwards, so a partial read cannot rewind it."""
    if not value:
        return
    marks = load()
    if value > marks.get(source, ""):
        marks[source] = value
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(marks, indent=2, sort_keys=True), encoding="utf-8")
