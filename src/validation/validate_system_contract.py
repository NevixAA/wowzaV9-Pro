"""READ-ONLY validator for the Wowza system contract. Reports staleness; changes nothing.

    python -m src.validation.validate_system_contract            # from mixed/v10
    python -m src.validation.validate_system_contract --json     # machine-readable

PLACEMENT. The brief proposed scripts/validate_system_contract.py. Pro has no tracked
`scripts/` directory -- its .gitignore is a WHITELIST (`/*` at line 13, then `!` re-admissions
for .github, README.md, docs, config, src, registry, experiments, tests, data, models, output),
so a file under scripts/ would be silently ignored and never committed. It lives in
src/validation/ instead, beside the other validators.

WHAT IT MAY DO. Read files. Run `git rev-parse`. Print. Nothing else. It never writes, never
fetches, never regenerates the contract and never touches v9 or v11 beyond reading their HEAD.

WHY IT MUST NOT GATE PRODUCTION. A stale architecture document is a documentation problem. It
must never stop v9 sending tips, so this exits 0 on staleness by default. `--strict` makes
staleness a non-zero exit for anyone who deliberately wants that in CI, and even then the right
place for it is a reporting workflow, not the predict path.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PRO = Path(__file__).resolve().parents[2]          # mixed/v10
ROOT = PRO.parent                                   # mixed/
CONTRACT = PRO / "registry" / "WOWZA_SYSTEM_CONTRACT.json"
SCHEMA = PRO / "registry" / "WOWZA_SYSTEM_CONTRACT.schema.json"
REPO_PATHS = {"v9": ROOT / "v9", "pro": PRO, "v11": ROOT / "wowza-v11"}


def _head(path: Path) -> str | None:
    """Current HEAD sha, or None if the path is not a readable git repo."""
    if not (path / ".git").exists():
        return None
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def run() -> dict:
    report: dict = {"checks": [], "stale": False, "errors": 0, "warnings": 0}

    def ck(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
        level = "OK" if ok else ("WARN" if warn_only else "ERROR")
        report["checks"].append({"check": name, "level": level, "detail": detail})
        if not ok:
            report["warnings" if warn_only else "errors"] += 1
        return ok

    if not ck("contract file exists", CONTRACT.exists(), str(CONTRACT)):
        return report
    try:
        c = json.loads(CONTRACT.read_text(encoding="utf-8"))
        ck("contract parses as JSON", True)
    except Exception as e:
        ck("contract parses as JSON", False, str(e))
        return report

    if ck("schema file exists", SCHEMA.exists(), str(SCHEMA)):
        try:
            json.loads(SCHEMA.read_text(encoding="utf-8"))
            ck("schema parses as JSON", True)
        except Exception as e:
            ck("schema parses as JSON", False, str(e))
    # jsonschema is optional -- absence must not fail the validator
    try:
        import jsonschema  # type: ignore
        try:
            jsonschema.validate(c, json.loads(SCHEMA.read_text(encoding="utf-8")))
            ck("contract validates against schema", True)
        except Exception as e:
            ck("contract validates against schema", False, str(e)[:300])
    except ImportError:
        ck("jsonschema installed", False, "not installed — schema validation skipped", warn_only=True)

    # ── staleness: the whole point ────────────────────────────────────────────
    va = c.get("verified_against", {})
    for key, repo in (("v9_commit", "v9"), ("pro_commit", "pro"), ("v11_commit", "v11")):
        recorded = va.get(key)
        actual = _head(REPO_PATHS[repo])
        if actual is None:
            ck(f"{repo}: repo readable", False, f"{REPO_PATHS[repo]} is not a git repo here",
               warn_only=True)
            continue
        same = recorded == actual
        if not same:
            report["stale"] = True
        ck(f"{repo}: HEAD matches contract", same,
           f"contract {str(recorded)[:12]} vs HEAD {actual[:12]}", warn_only=True)

    # ── referenced paths still exist ──────────────────────────────────────────
    for r, meta in (c.get("repos") or {}).items():
        p = REPO_PATHS.get(r)
        if p:
            ck(f"{r}: local path exists", p.exists(), str(p))

    for m in (c.get("models", {}).get("match_models") or []):
        art = m.get("artifact")
        if art:
            ck(f"model artifact: {m['model_id']}", (REPO_PATHS['v9'] / art).exists(), art,
               warn_only=True)

    for wf_repo, folder in (("v9", REPO_PATHS["v9"]), ("pro", PRO), ("v11", REPO_PATHS["v11"])):
        d = folder / ".github" / "workflows"
        n = len(list(d.glob("*.yml"))) if d.exists() else 0
        recorded = (c.get("repos", {}).get(wf_repo) or {}).get("workflow_count")
        if recorded is not None:
            ck(f"{wf_repo}: workflow count", n == recorded,
               f"contract {recorded} vs on disk {n}", warn_only=True)

    # ── boundaries that must never drift ──────────────────────────────────────
    pb = c.get("product_boundary", {})
    for k in ("may_write_v9", "may_write_pro", "may_write_v11"):
        ck(f"product boundary: {k} is false", pb.get(k) is False, repr(pb.get(k)))
    ck("ai_change_policy: v9 is READ_ONLY_BY_DEFAULT",
       (c.get("ai_change_policy") or {}).get("v9") == "READ_ONLY_BY_DEFAULT")
    rm = c.get("real_money", {})
    ck("real money: no automated placement recorded",
       rm.get("automated_placement_exists") is False, repr(rm.get("automated_placement_exists")))

    # ── critical shared files ─────────────────────────────────────────────────
    ck("odds_history_v9.json present at v9 root",
       (REPO_PATHS["v9"] / "odds_history_v9.json").exists(), warn_only=True)

    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when the contract is stale (default: staleness is a warning)")
    a = ap.parse_args()
    rep = run()

    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        for c in rep["checks"]:
            mark = {"OK": "  ok  ", "WARN": " warn ", "ERROR": "ERROR "}[c["level"]]
            print(f"{mark} {c['check']}" + (f"  — {c['detail']}" if c["detail"] else ""))
        print()
        print(f"CONTRACT_STALE={'YES' if rep['stale'] else 'NO'}  "
              f"errors={rep['errors']}  warnings={rep['warnings']}")
        if rep["stale"]:
            print("A stale contract is a documentation problem, not a production incident. "
                  "Regenerate it deliberately; never let it block v9.")

    if rep["errors"]:
        return 1
    if a.strict and rep["stale"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
