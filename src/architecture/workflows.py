"""Map every workflow across the three repos: when it runs, what it runs, what it writes.

    python -m src.architecture.workflows --write

The brief (section 2) asks a specific question that the file-level lineage cannot answer:

    Which workflow CREATES each data file, and which later workflow actually CONSUMES it?

A file with a producer and no consumer is a dead end. A file with a consumer whose producer runs
less often than the consumer does is a staleness bug waiting to happen. Neither is visible from
the files alone -- you have to know the schedules.

CRON IS PARSED, NOT TRUSTED. GitHub's dispatcher does not honour the minute field and drops most
high-frequency slots (measured across 1,367 runs: ~13% delivery at 57/day, ~100% at once-daily
but 4-5 hours late). So "declared cadence" here is exactly that -- declared. It is the right
number for reasoning about DEPENDENCY ORDER (a daily consumer of an hourly producer is fine; the
reverse is not) and the wrong number for reasoning about when anything actually happens.

PRODUCTION IMPACT is judged by what a failure COSTS, not by how the workflow is named:
    TIPS        sends Telegram, or writes a file the tipping path reads. A failure loses tips.
    COLLECT     captures data that cannot be recovered later. A failure loses it permanently.
    DERIVE      recomputes something from stored inputs. A failure is re-runnable, costs nothing.
    REPORT      produces numbers for humans. A failure costs visibility only.
The distinction matters because it decides which workflows may ever be consolidated, and the
answer for anything tagged COLLECT is essentially never -- a missed capture is gone (odds
history cannot be backfilled; established 2026-08-19 across six seasons and ~830 calls).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import yaml

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
REPOS = {"v9": "v9", "pro": "v10", "v11": "wowza-v11"}

SECRET_RE = re.compile(r"secrets\.([A-Z0-9_]+)")
SCRIPT_RE = re.compile(r"python\s+-m\s+([A-Za-z0-9_.]+)|python\s+([A-Za-z0-9_./\\-]+\.py)")
GITADD_RE = re.compile(r"git\s+add\s+(?:-f\s+)?([^\n&|;]+)")
PATH_RE = re.compile(r"((?:output|data|registry|models|scripts)/[A-Za-z0-9_./\-*]+"
                     r"|[a-z_]+_history\.parquet)")


def _root() -> Path:
    return cfg.BASE_DIR.parent


def _cadence_per_day(crons: list[str]) -> float:
    """Declared runs per day. Approximate by design -- see the module docstring."""
    total = 0.0
    for c in crons:
        parts = str(c).split()
        if len(parts) != 5:
            continue
        minute, hour, dom, mon, dow = parts
        def n(field: str, span: int) -> float:
            if field == "*":
                return span
            if field.startswith("*/"):
                try:
                    return span / int(field[2:])
                except ValueError:
                    return 1.0
            if "-" in field and "," not in field:
                try:
                    a, b = field.split("-")
                    return float(int(b) - int(a) + 1)
                except ValueError:
                    return 1.0
            return float(len([x for x in field.split(",") if x != ""]))
        per_day = n(minute, 60) * n(hour, 24)
        # Day restriction scales it down.
        if dow != "*":
            per_day *= n(dow, 7) / 7.0
        if dom != "*":
            per_day *= n(dom, 31) / 31.0
        total += per_day
    return round(total, 2)


def _impact(name: str, text: str, scripts: list[str]) -> str:
    """Judge by what a FAILURE costs, and test irrecoverability FIRST.

    Order matters, and the first version got it wrong. Testing for "telegram" before testing for
    "capture" tagged std_odds_capture and nf_odds_capture as REPORT -- because they happen to
    mention API usage -- when they are precisely the two workflows whose miss is PERMANENT: odds
    cannot be backfilled (API-Football's /odds is pre-match only, established across six seasons
    and ~830 calls). A workflow whose failure is unrecoverable outranks one that merely fails to
    send a message.
    """
    n = name.lower()
    t = text.lower()
    if any(k in n for k in ("capture", "collect", "snapshot", "extend", "history", "results")):
        return "COLLECT"
    if any(k in n for k in ("audit", "monitor", "usage", "summary", "health")):
        return "REPORT"
    if any(k in t for k in ("telegram", "notifier", "notify", "send_message", "bot_token")):
        return "TIPS"
    if any("predict" in s or "pipeline" in s for s in scripts):
        return "TIPS"
    return "DERIVE"


def scan() -> pd.DataFrame:
    root = _root()
    rows = []
    for repo, folder in REPOS.items():
        wd = root / folder / ".github" / "workflows"
        if not wd.exists():
            continue
        for p in sorted(wd.glob("*.yml")):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            try:
                y = yaml.safe_load(txt) or {}
            except Exception:
                y = {}
            on = y.get("on") or y.get(True) or {}
            crons = []
            if isinstance(on, dict):
                sch = on.get("schedule") or []
                crons = [s.get("cron") for s in sch if isinstance(s, dict) and s.get("cron")]
            scripts = sorted({m.group(1) or m.group(2) for m in SCRIPT_RE.finditer(txt)})
            staged = []
            for m in GITADD_RE.finditer(txt):
                for x in m.group(1).split():
                    x = x.strip().strip("\"'")
                    # Shell noise, not files. `git add -f "$f" 2>/dev/null` made "2>/dev/null"
                    # look like a path staged by 25 separate workflows, which then presented as
                    # the most contended file in the estate. A redirection is not a data store.
                    if not x or x[0] in "2><&|-$":
                        continue
                    if x in ("||", "&&", ";", "echo", "true", "exit", "then", "fi"):
                        continue
                    if "/" in x or x.endswith((".csv", ".json", ".parquet", ".md")):
                        staged.append(x)
            paths = sorted(set(PATH_RE.findall(txt)))
            secrets = sorted(set(SECRET_RE.findall(txt)))
            timeout = None
            for job in (y.get("jobs") or {}).values():
                if isinstance(job, dict) and job.get("timeout-minutes"):
                    timeout = job["timeout-minutes"]
                    break
            rows.append({
                "repo": repo, "workflow": p.name,
                "name": str(y.get("name", ""))[:60],
                "crons": "; ".join(crons), "n_crons": len(crons),
                "declared_runs_per_day": _cadence_per_day(crons),
                "manual_dispatch": "workflow_dispatch" in txt,
                "scripts": "; ".join(scripts[:6]), "n_scripts": len(scripts),
                "stages_files": "; ".join(sorted(set(staged))[:8]),
                "n_staged": len(set(staged)),
                "paths_mentioned": "; ".join(paths[:10]), "n_paths": len(paths),
                "api_secrets": "; ".join(s for s in secrets
                                         if any(k in s for k in ("KEY", "API", "TOKEN"))),
                "uses_external_api": bool([s for s in secrets
                                           if any(k in s for k in ("KEY", "API"))]),
                "timeout_minutes": timeout,
                "has_concurrency": "concurrency:" in txt,
                "production_impact": _impact(p.name, txt, scripts),
                "calc_version": CALC_VERSION,
            })
    return pd.DataFrame(rows)


def overlaps(wf: pd.DataFrame) -> pd.DataFrame:
    """Workflow pairs that stage the same file -- two paths writing one truth."""
    idx: dict[str, list[str]] = {}
    for _, r in wf.iterrows():
        for f in str(r["stages_files"]).split("; "):
            f = f.strip()
            if f and f != "nan":
                idx.setdefault(f, []).append(f"{r['repo']}:{r['workflow']}")
    rows = []
    for f, who in idx.items():
        if len(set(who)) > 1:
            rows.append({"file": f, "written_by": "; ".join(sorted(set(who))),
                         "n_writers": len(set(who))})
    return pd.DataFrame(rows).sort_values("n_writers", ascending=False) if rows \
        else pd.DataFrame(columns=["file", "written_by", "n_writers"])


def out_dir() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    wf = scan()
    print(f"[workflows] {len(wf)} workflows across {wf.repo.nunique()} repos")
    print(wf.groupby(["repo", "production_impact"]).size().to_string())
    print("\nDECLARED CADENCE (what the cron says, NOT what GitHub delivers)")
    top = wf.sort_values("declared_runs_per_day", ascending=False).head(14)
    print(top[["repo", "workflow", "declared_runs_per_day", "production_impact",
               "uses_external_api", "timeout_minutes"]].to_string(index=False))
    ov = overlaps(wf)
    print(f"\nFILES STAGED BY MORE THAN ONE WORKFLOW: {len(ov)}")
    if len(ov):
        print(ov.head(14).to_string(index=False))
    if a.write:
        wf.to_csv(out_dir() / "workflow_lineage.csv", index=False)
        ov.to_csv(out_dir() / "workflow_write_overlap.csv", index=False)
        print(f"\n[workflows] wrote workflow_lineage.csv + workflow_write_overlap.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
