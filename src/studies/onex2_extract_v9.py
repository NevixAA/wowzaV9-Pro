"""
Extract the inputs of the 1X2 review (src/studies/onex2_review.py) from v9, inside v9's environment.

    python src/studies/onex2_extract_v9.py <v9_root> <out_dir> <pro_fd_raw_dir>

Kept for reproducing reports/P5_1X2_REVIEW.md. The logic lives in ONE place since 2026-11-09:
src/pipelines/onex2_v9_bridge.py (history mode), which the served model's monthly retrain uses too.
This shim runs that mode; the outputs (matches / features / prices parquet, extract.json) are the
same files the review read.
"""
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    bridge = Path(__file__).resolve().parents[1] / "pipelines" / "onex2_v9_bridge.py"
    sys.argv = [str(bridge), "history", *sys.argv[1:4]]
    runpy.run_path(str(bridge), run_name="__main__")
