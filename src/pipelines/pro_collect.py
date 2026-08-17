"""
Pro collector: snapshot v9's current state into the canonical season store.
==========================================================================
    python -m src.pipelines.pro_collect [--dry-run]

Design rule, learned from v9 twice in one week: **a collector that produces no rows is a
FAILURE, not a success.** v9's `player_props.yml` marks every functional step
`continue-on-error`, so a crash left its outputs untouched, staged nothing, and reported green
~40 consecutive times over two days while `player_tips.csv` stayed frozen. A health step was
emitting `::warning title=Stale player history` the whole time; nobody reads annotations.

So this process exits non-zero when it collected nothing, and it writes a machine-readable
health file either way.

It never writes to v9 and never sends a notification.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.data import season_store as store
from src.data.v9_source import v9_head_sha
from src.importers.current_wowza import IMPORTERS, commit_watermarks


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot v9 into the Pro season store")
    ap.add_argument("--dry-run", action="store_true",
                    help="read and report, write nothing")
    ap.add_argument("--only", default="", help="comma-separated importer names")
    args = ap.parse_args()

    if cfg.PRO_MAY_NOTIFY:
        print("[pro_collect] FATAL: PRO_MAY_NOTIFY is set. Pro must never notify.")
        return 2

    rid = cfg.run_id()
    v9_sha = v9_head_sha()
    season = cfg.season_label()
    wanted = [w.strip() for w in args.only.split(",") if w.strip()] or list(IMPORTERS)

    print(f"[pro_collect] season={season} run_id={rid} v9_sha={v9_sha} "
          f"pro_sha={store.pro_git_sha()}")
    print(f"[pro_collect] importers: {', '.join(wanted)}")

    per_importer: dict[str, dict] = {}
    failures: list[str] = []
    total_rows = 0

    for name in wanted:
        fn = IMPORTERS.get(name)
        if fn is None:
            failures.append(f"{name}: unknown importer")
            continue
        try:
            blocks = fn()
        except Exception as e:
            failures.append(f"{name}: {type(e).__name__}: {e}")
            print(f"[pro_collect] {name} FAILED: {e}")
            traceback.print_exc()
            continue

        rows = 0
        tables: dict[str, int] = {}
        for i, (table, df) in enumerate(blocks):
            n = 0 if df is None else len(df)
            tables[table] = tables.get(table, 0) + n
            rows += n
            if n and not args.dry_run:
                try:
                    # run_id must be unique per WRITE, not per importer: from_ledgers yields
                    # two blocks for `settlements` (main + side), and sharing one run_id made
                    # the second collide with the first. The append-only guard caught it,
                    # which is what it is for — but the fix belongs here.
                    store.append(table, df, source=f"v9:{name}#{i}",
                                 source_sha=v9_sha, rid=f"{rid}-{name}{i}")
                except Exception as e:
                    failures.append(f"{name}->{table}: {type(e).__name__}: {e}")
                    print(f"[pro_collect] write FAILED {name}->{table}: {e}")
        per_importer[name] = {"rows": rows, "tables": tables}
        total_rows += rows
        print(f"[pro_collect]   {name:16} {rows:>7} rows  {tables}")

    # Only now that every row is on disk. Advancing earlier would let a failed write skip
    # source rows permanently.
    advanced = {} if (args.dry_run or failures) else commit_watermarks()
    if advanced:
        print(f"[pro_collect] watermarks advanced: {advanced}")

    health = {
        "checked_at": cfg.utc_now_iso(),
        "watermarks_advanced": advanced,
        "season": season,
        "run_id": rid,
        "v9_sha": v9_sha,
        "pro_git_sha": store.pro_git_sha(),
        "dry_run": bool(args.dry_run),
        "total_rows": total_rows,
        "per_importer": per_importer,
        "failures": failures,
        "store": {} if args.dry_run else store.stats(),
    }
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (cfg.OUTPUT_DIR / "collect_health.json").write_text(
        json.dumps(health, indent=2, default=str), encoding="utf-8")

    print(f"\n[pro_collect] total {total_rows} rows | failures: {len(failures)}")
    for f in failures:
        print(f"  !! {f}")

    if failures:
        print("[pro_collect] EXIT 1 — an importer failed. This must not be swallowed.")
        return 1
    if total_rows == 0:
        print("[pro_collect] EXIT 1 — collected ZERO rows. A silent no-op is a failure.")
        return 1
    print("[pro_collect] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
