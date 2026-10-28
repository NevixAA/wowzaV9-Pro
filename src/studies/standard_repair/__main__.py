"""python -m src.studies.standard_repair {build|run|forward|scorecard|weekly|monthly|all|forensic ...|freeze-pre-repair}

build/run/scorecard are the PRE_REPAIR benchmark (2026-10-26) — kept auditable, NOT FINAL (see pre_repair.py).

build / run need the local v9 frame (experiments/standard_repair_2026_10/, see data.py) and are run on
a workstation. weekly / monthly need only Pro's store, fd_raw and the committed results.json — they
are what the pro_standard_repair workflow runs.
"""
from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "all"
    if cmd == "forensic":                       # Phase 1 of the 2026-10-28 forensic repair
        from src.studies.standard_repair import forensic
        return forensic.main(argv[1:])
    if cmd == "benchmark":                      # Phase 2 (requires a PASS, CURRENT data_quality.json)
        from src.studies.standard_repair import benchmark_out
        return benchmark_out.main(argv[1:])
    if cmd == "freeze-pre-repair":
        from src.studies.standard_repair import pre_repair
        print(json.dumps(pre_repair.freeze(), indent=1))
        return 0
    from src.studies.standard_repair import data, evaluate, forward, registry, report, scorecard
    if cmd in ("build", "all"):
        _, audit = data.build()
        print(json.dumps(audit, indent=1))
    if cmd in ("run", "all"):
        res = evaluate.run()
        print(json.dumps(res["verdict"], indent=1))
    if cmd in ("forward", "all"):
        print(len(forward.build()), "first-sight rows")
    if cmd in ("scorecard", "all"):
        res = json.loads((evaluate.OUT / "results.json").read_text(encoding="utf-8"))
        sc = scorecard.build(res=res, fwd=forward.load())
        registry.experiments(res, sc)
        print("journey lines added:", registry.journey(sc, res))
        print(json.dumps(registry.maybe_register(res), indent=1))
    if cmd == "weekly":
        print(json.dumps(report.weekly()["model_vs_market_forward"], indent=1, default=str))
    if cmd == "monthly":
        print(json.dumps(report.monthly(), indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
