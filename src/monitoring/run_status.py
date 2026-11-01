"""Research workflow run status -- so red/green is never read as a scientific verdict (R2 finding 27).

A research workflow can go red because GitHub could not install a package, because a unit test
broke, because the input data was missing or failed its integrity gate, or because an experiment
step crashed. None of those is a finding about football. The estate rule is "never report infra
failure as model failure", so every research workflow ends with this classifier:

    python -m src.monitoring.run_status --workflow pro_prediction_lab \
        --step infra:install=success --step test:tests=failure --step data:dataset=skipped ...

Classes, in precedence order (the FIRST failing class wins, because later steps are usually
skipped or poisoned by an earlier failure):

    INFRA_FAILURE  checkout / setup / install / cache / commit / push failed, or a step was
                   cancelled (timeout, runner loss)
    TEST_FAILURE   the unit / contract test gate failed -- code is wrong, nothing was measured
    DATA_FAILURE   input data missing, unreadable, or failed its integrity / leakage gate
    MODEL_FAILURE  an experiment / training / evaluation step CRASHED. Still not a verdict: a model
                   that runs and loses is SUCCESS here and its verdict lives in the study output
    SUCCESS        every classified step succeeded (skipped steps with no failure are fine)

The JSON written (default output/run_status/<workflow>.json) and the step summary both say
`is_scientific_verdict: false`, explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CLASSES = ("infra", "test", "data", "model")
STATUS_FOR = {"infra": "INFRA_FAILURE", "test": "TEST_FAILURE", "data": "DATA_FAILURE",
              "model": "MODEL_FAILURE"}
SUCCESS = "SUCCESS"
VERSION = "run-status/1.0"


def parse_step(spec: str) -> tuple[str, str, str]:
    """'class:name=outcome' -> (class, name, outcome). An empty outcome means 'did not run'."""
    left, _, outcome = spec.partition("=")
    cls, _, name = left.partition(":")
    cls = cls.strip().lower()
    if cls not in CLASSES:
        raise ValueError(f"unknown step class {cls!r} in {spec!r}; use one of {CLASSES}")
    return cls, (name.strip() or cls), (outcome.strip().lower() or "not_run")


def classify(steps: list[tuple[str, str, str]]) -> dict:
    failed = []
    for cls, name, outcome in steps:
        if outcome == "failure":
            failed.append({"class": cls, "step": name, "outcome": outcome})
        elif outcome == "cancelled":
            failed.append({"class": "infra", "step": name, "outcome": outcome})
    status = SUCCESS
    for cls in CLASSES:
        if any(f["class"] == cls for f in failed):
            status = STATUS_FOR[cls]
            break
    if status == SUCCESS and steps and all(o in ("skipped", "not_run") for _, _, o in steps):
        # Nothing ran at all: that is not a success, it is an infrastructure problem.
        status = "INFRA_FAILURE"
        failed.append({"class": "infra", "step": "all", "outcome": "nothing_ran"})
    return {"status": status, "failed_steps": failed,
            "steps": [{"class": c, "step": n, "outcome": o} for c, n, o in steps]}


NOTE = ("This is a RUN status, not a scientific verdict. A red run means the measurement did not "
        "complete; it says nothing about whether a model or hypothesis is good. Verdicts live in "
        "each study's own output files.")


def summary_markdown(rec: dict) -> str:
    lines = [f"## Run status: `{rec['status']}`  ({rec['workflow']})", "",
             f"> {NOTE}", "", "| class | step | outcome |", "|---|---|---|"]
    for s in rec["steps"]:
        lines.append(f"| {s['class']} | {s['step']} | {s['outcome']} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--step", action="append", default=[], help="class:name=outcome")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-fail", action="store_true", help="always exit 0")
    a = ap.parse_args(argv)
    rec = classify([parse_step(s) for s in a.step])
    rec.update({"workflow": a.workflow, "version": VERSION,
                "is_scientific_verdict": False, "note": NOTE,
                "run_id": os.getenv("GITHUB_RUN_ID"), "sha": os.getenv("GITHUB_SHA"),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    out = Path(a.out or f"output/run_status/{a.workflow}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    md = summary_markdown(rec)
    summ = os.getenv("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    if rec["status"] != SUCCESS:
        print(f"::error title=RUN {rec['status']} (not a scientific verdict)::"
              f"{', '.join(s['step'] for s in rec['failed_steps'])}")
    return 0 if (a.no_fail or rec["status"] == SUCCESS) else 1


if __name__ == "__main__":
    sys.exit(main())
