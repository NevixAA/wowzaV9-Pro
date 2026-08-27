"""
output/system_registry.json — regenerated from the CANONICAL store, never from itself.
=====================================================================================
WHY THIS MODULE EXISTS (measured 2026-08-23)

The registry is supposed to be the single machine-readable answer to "what is live, on what
data, how healthy". It was written in exactly one place — the tail of `shadow.py` — which runs
after the *backfill*, not after *collect*. So the counts froze at whatever the last shadow run
saw and then drifted for four days without anything reporting a problem:

    table               registry      canonical     error
    market_snapshots      51,638         74,740      -31%
    model_snapshots       20,210         55,670      -64%
    settlements           24,114         43,555      -45%
    fixtures               4,316         11,753      -63%
    TOTAL                ~118,000        231,753

A stale registry is worse than a missing one. Every number in it looked plausible, so anyone
reading it to answer "how much data do we have" got an answer that was wrong by a factor of
two and had no way to notice — there was no `generated_at` freshness check anywhere, and the
file's own `generated_at` was correct (2026-08-19), which made the staleness look intentional.

THREE RULES, and the reason for each:

1. **Counts are ALWAYS derived from `season_store.stats()`, never carried forward.** `stats()`
   reads each parquet's footer metadata, so the count is exact and O(1) per file — there is no
   performance excuse for caching it. A registry that can fall back to its own previous value
   cannot distinguish "nothing changed" from "the refresh failed", and the second is the case
   that matters. If `stats()` raises, this function raises: no registry is written at all,
   which the audit reports as stale. Refusing to write beats writing a lie.

2. **Blocks that are NOT counts may be carried forward, but are NAMED when they are.**
   `feature_health` comes from the drift monitor and `live_models` from the model registry;
   neither is available during a collect run. Carrying them is correct — dropping them would
   make the registry less informative each time collect ran — but a reader must be able to
   tell a recomputed block from an inherited one, so `carried_forward` lists exactly which
   keys came from the previous file and `carried_from` records when it was generated.

3. **The write is atomic and validated.** Write to a sibling temp file, read it back, parse it,
   assert the table totals match what we just measured, and only then `os.replace`. A partial
   or truncated registry is indistinguishable from a real one to `json.load` if the truncation
   happens to land on a closing brace, and `os.replace` is atomic on both NTFS and ext4, so a
   crashed run leaves the previous good file rather than a half-written one.

`registry_age_hours` is written as a convenience for humans reading the raw file, but it is
computed at READ time by consumers (`age_hours()`), because a stored age is only correct at the
instant it was stored — which is precisely the failure this module exists to fix.
"""
from __future__ import annotations

import json
from src import schemas
import os
from datetime import datetime, timezone
from pathlib import Path

from config import pro_config as cfg

# Blocks that describe health/deployment rather than data volume. Safe to inherit; always
# reported as inherited. Anything holding a ROW COUNT must never appear here.
_CARRYABLE = ("feature_health", "live_models", "n_live_models", "collect_health")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_previous(p: Path) -> dict:
    """Previous registry, or {} — a corrupt previous file must not block a refresh."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def age_hours(path: Path | None = None) -> float | None:
    """Hours since the registry's own `generated_at`. None if absent/unparseable.

    Computed from the recorded timestamp rather than the file mtime: a `git checkout` on a CI
    runner sets mtime to checkout time, so every freshly cloned repo would look seconds old.
    """
    p = path or (cfg.OUTPUT_DIR / "system_registry.json")
    d = _read_previous(p)
    ts = d.get("generated_at")
    if not ts:
        return None
    try:
        t = datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return round((datetime.now(timezone.utc) - t).total_seconds() / 3600.0, 2)


def refresh(*, season: str | None = None, path: Path | None = None,
            drift_health: dict | None = None, collect_health: dict | None = None,
            registry_table=None, quiet: bool = False) -> dict:
    """Regenerate the registry from the canonical store. Returns the payload written.

    Raises on a store read failure or a post-write validation mismatch — see rule 1. Callers
    that must not fail their whole job should catch, but must NOT substitute cached counts.
    """
    from src.data import season_store as store
    from src.pipelines.experiment import git_sha

    p = path or (cfg.OUTPUT_DIR / "system_registry.json")
    season = season or cfg.season_label()
    prev = _read_previous(p)

    # ---- counts: always measured, never inherited -------------------------------------
    stats = store.stats(season)
    tables = {}
    for table, s in stats.items():
        tables[table] = {
            "table": table,
            "rows": int(s.get("rows") or 0),
            "partitions": int(s.get("partitions") or 0),
            "runs": int(s.get("runs") or 0),
            "first_dt": s.get("first_dt"),
            "last_dt": s.get("last_dt"),
            # Lifecycle status, so an EXPECTED empty table stops reading as an outage. Two
            # canonical tables (team_news, team_match_stats) are declared PLANNED_OPTIONAL in
            # src/schemas.py: their schemas are agreed, their collectors are not built, and
            # empty is the correct state. Without this the "N/M tables populated" line reports a
            # permanent two-table shortfall, and a health signal that is always slightly red is
            # one nobody reads — which is exactly how the genuinely-empty data_quality table went
            # unnoticed for months.
            "lifecycle": schemas.status(table),
        }
    total = sum(t["rows"] for t in tables.values())
    _expected_empty = sorted(t for t, v in tables.items()
                             if v["rows"] == 0 and schemas.is_planned(t))
    _unexpected_empty = sorted(t for t, v in tables.items()
                               if v["rows"] == 0 and not schemas.is_planned(t))

    # ---- non-count blocks: inherit, and say so ----------------------------------------
    carried = []
    payload = {
        "generated_at": _now(),
        "source_commit_sha": git_sha(),
        "git_sha": git_sha(),          # kept: existing consumers read this key
        "season": season,
        "season_store": tables,
        "total_rows": total,
        "n_tables": len(tables),
        "n_tables_populated": sum(1 for t in tables.values() if t["rows"] > 0),
        # Populated OR legitimately planned-empty. This is the number to alarm on; the raw
        # populated count is kept because existing consumers read it.
        "n_tables_accounted": sum(1 for t, v in tables.items()
                                  if v["rows"] > 0 or schemas.is_planned(t)),
        "tables_expected_empty": _expected_empty,
        "tables_unexpected_empty": _unexpected_empty,
        "registry_age_hours": 0.0,     # true at write time only; consumers use age_hours()
        "pro_may_notify": cfg.PRO_MAY_NOTIFY,
        "pro_may_stake": False,
        "deployment_note": (
            "Season 2026/27 is a data-collection and shadow season. Pro does not stake and "
            "does not notify. Signal tier and deployment mode are independent: a SNIPER may be "
            "PAPER."
        ),
    }

    if drift_health is not None:
        payload["feature_health"] = drift_health
    if collect_health is not None:
        payload["collect_health"] = collect_health
    if registry_table is not None and hasattr(registry_table, "empty") \
            and not registry_table.empty and "status" in registry_table:
        live = registry_table.loc[registry_table["status"] == "LIVE"].to_dict("records")
        payload["live_models"] = live
        payload["n_live_models"] = len(live)

    for k in _CARRYABLE:
        if k not in payload and k in prev:
            payload[k] = prev[k]
            carried.append(k)
    payload["carried_forward"] = sorted(carried)
    payload["carried_from"] = prev.get("generated_at") if carried else None

    # ---- atomic write + read-back validation ------------------------------------------
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    back = json.loads(tmp.read_text(encoding="utf-8"))       # parses? else raises, tmp discarded
    if int(back.get("total_rows", -1)) != total:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"registry validation failed: wrote total_rows="
                         f"{back.get('total_rows')} expected {total}")
    os.replace(tmp, p)                                        # atomic on NTFS and ext4

    if not quiet:
        print(f"[registry] {p.name} refreshed from canonical store "
              f"({payload['n_tables_populated']}/{len(tables)} tables populated, "
              f"{payload['n_tables_accounted']}/{len(tables)} accounted, "
              f"{total:,} rows, sha {payload['source_commit_sha']})")
        if _expected_empty:
            print(f"[registry]   empty BY DESIGN (PLANNED_OPTIONAL): {', '.join(_expected_empty)}")
        if _unexpected_empty:
            print(f"[registry]   empty UNEXPECTEDLY: {', '.join(_unexpected_empty)}  <- "
                  f"these are the ones worth looking at")
        for k, v in sorted(tables.items(), key=lambda kv: -kv[1]["rows"]):
            before = (prev.get("season_store") or {}).get(k)
            was = before.get("rows") if isinstance(before, dict) else before
            delta = ""
            if isinstance(was, (int, float)) and was != v["rows"]:
                delta = f"  (was {int(was):,})"
            print(f"    {k:22} {v['rows']:>8,} rows  {v['partitions']:>4} part  "
                  f"{v['first_dt'] or '-'}..{v['last_dt'] or '-'}{delta}")
        if carried:
            print(f"    carried forward (not recomputed): {', '.join(carried)} "
                  f"from {payload['carried_from']}")
    return payload


def reconcile(path: Path | None = None, season: str | None = None) -> dict:
    """Compare the registry's stated counts to the canonical store, per table.

    This is what the weekly audit asserts. It is deliberately separate from `refresh()`: a
    refresh that silently corrected a discrepancy would hide the fact that something had gone
    out of sync in the first place.
    """
    from src.data import season_store as store
    p = path or (cfg.OUTPUT_DIR / "system_registry.json")
    d = _read_previous(p)
    stated = d.get("season_store") or {}
    try:
        actual = store.stats(season or d.get("season") or cfg.season_label())
    except Exception as e:
        return {"ok": False, "error": f"store unreadable: {e}", "mismatches": []}

    mism = []
    for table, s in actual.items():
        got = stated.get(table)
        got_rows = got.get("rows") if isinstance(got, dict) else got
        if got is None:
            mism.append({"table": table, "registry": None, "canonical": int(s["rows"]),
                         "why": "absent from registry"})
        elif int(got_rows or 0) != int(s["rows"]):
            mism.append({"table": table, "registry": int(got_rows or 0),
                         "canonical": int(s["rows"]),
                         "why": "count differs"})
    return {
        "ok": not mism,
        "age_hours": age_hours(p),
        "generated_at": d.get("generated_at"),
        "n_tables": len(actual),
        "registry_total": sum(int((v.get("rows") if isinstance(v, dict) else v) or 0)
                              for v in stated.values()),
        "canonical_total": sum(int(v["rows"]) for v in actual.values()),
        "mismatches": mism,
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Regenerate output/system_registry.json from the "
                                             "canonical season store")
    ap.add_argument("--check", action="store_true",
                    help="reconcile only; exit 1 on mismatch, write nothing")
    a = ap.parse_args()
    if a.check:
        r = reconcile()
        print(json.dumps(r, indent=2, default=str))
        return 0 if r["ok"] else 1
    refresh()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
