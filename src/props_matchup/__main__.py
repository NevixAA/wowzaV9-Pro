"""CLI for the props matchup track.

    python -m src.props_matchup --check-readiness [--json PATH]   gate on the real committed data; exit 1 unless READY
    python -m src.props_matchup --inventory                       real-input counts with provenance

There is deliberately no fit / backtest / edge command (owner rule: no training or backtests until the
data is 100% real). When the gate is READY and the owner approves, the first real step is added here
in its own reviewed commit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.props_matchup import readiness as R  # noqa: E402


def _print_gate(res: dict) -> None:
    print(f"PROPS MATCHUP DATA READINESS: {'READY' if res['ready'] else 'NOT READY'}")
    for name, c in res["checks"].items():
        th = "unset (owner decision)" if c["threshold"] is None else f"{'<=' if c['direction'] == 'max' else '>='} {c['threshold']}"
        print(f"  {c['status']:<24} {name:<30} measured={c['measured']}  threshold {th}")
        if c.get("detail"):
            print(f"  {'':<24} {'':<30} {c['detail']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.props_matchup")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check-readiness", action="store_true")
    g.add_argument("--inventory", action="store_true")
    ap.add_argument("--json", help="also write the full result (gate + inventory) to this path")
    a = ap.parse_args(argv)
    res = R.check()
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    if a.inventory:
        print(json.dumps(res["inventory"], indent=1, default=str))
        return 0
    _print_gate(res)
    return 0 if res["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
