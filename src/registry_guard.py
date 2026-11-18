"""
Registry guard - frozen registrations are hash-checked, live registries are append-only.
=====================================================================================
Data Truth round 3 (2026-11-02). Pro's `registry/` holds two kinds of file, and code could rewrite
both freely:

  FROZEN   pre-registrations, locks, amendments, frozen vocabularies (registration_v*.json,
           LOCK_v*.json, edge2_hypotheses_v1.json, candidate_forward_tests.json, ...). They define a
           forward test BEFORE its data exists; editing one after the forward window opened is how a
           test is quietly re-fitted to its results. Pinned by content SHA-256 (CRLF -> LF) in
           registry/FROZEN_HASHES.json. `verify()` reports any drift, research_integrity FAILS on it,
           and `write_json` refuses to write a pinned file at all. A change is a NEW version file.

  LIVE     registries a pipeline legitimately updates every run (scout_hypotheses.json,
           league_lifecycle.json, r2/r2b_repaired_challengers.json). They may grow and they may
           record new results, but an entry once registered can never disappear, its defining
           fields can never change, and its history can only be appended to. `write_json` with an
           `AppendOnly` spec enforces that against the file on disk before writing.

One writer for both, so no module keeps a private `path.write_text(json.dumps(...))` for a registry.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from config import pro_config as cfg

MANIFEST = cfg.REGISTRY_DIR / "FROZEN_HASHES.json"


class RegistryViolation(RuntimeError):
    """A write that would edit a frozen registration or rewrite an append-only one."""


def sha256_lf(path: Path) -> str:
    """Content hash a Windows (CRLF) and a CI (LF) checkout agree on."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _rel(path: Path) -> str:
    return Path(path).resolve().relative_to(cfg.BASE_DIR.resolve()).as_posix()


def frozen() -> dict:
    """{repo-relative path: sha256_lf} of every pinned registration."""
    if not MANIFEST.exists():
        return {}
    return dict(json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", {}))


def verify() -> list[dict]:
    """Every pinned file whose content differs from its pin (or is missing). Empty = intact."""
    out = []
    for rel, sha in sorted(frozen().items()):
        p = cfg.BASE_DIR / rel
        got = sha256_lf(p) if p.exists() else None
        if got != sha:
            out.append({"path": rel, "pinned": sha, "actual": got})
    return out


@dataclass(frozen=True)
class AppendOnly:
    """How a live registry may change.

    entries        "list:<key>" for a list of records under `key`, or "dict" for a top-level
                   {id: record} mapping.
    id_key         record id field (list form only).
    immutable      record fields that may never change once written.
    write_once     record fields that may go from null to a value once, then never change.
    history        record fields that are lists which may only be appended to.
    top_immutable  top-level fields that may never change once written.
    """
    entries: str
    id_key: str = "id"
    immutable: tuple = ()
    write_once: tuple = ()
    history: tuple = ()
    top_immutable: tuple = field(default_factory=tuple)


def _records(obj: dict, spec: AppendOnly) -> dict:
    if spec.entries == "dict":
        return {str(k): v for k, v in obj.items() if isinstance(v, dict)}
    key = spec.entries.split(":", 1)[1]
    return {str(r.get(spec.id_key)): r for r in obj.get(key, []) or []}


def check_append_only(old: dict, new: dict, spec: AppendOnly) -> list[str]:
    """Violations of `spec` going from `old` to `new` (empty = allowed)."""
    errs = []
    for k in spec.top_immutable:
        if k in old and old.get(k) != new.get(k):
            errs.append(f"top-level '{k}' changed")
    a, b = _records(old, spec), _records(new, spec)
    for rid, ra in a.items():
        rb = b.get(rid)
        if rb is None:
            errs.append(f"{rid}: entry removed")
            continue
        for f in spec.immutable:
            if f in ra and ra.get(f) != rb.get(f):
                errs.append(f"{rid}: '{f}' changed {ra.get(f)!r} -> {rb.get(f)!r}")
        for f in spec.write_once:
            if ra.get(f) is not None and ra.get(f) != rb.get(f):
                errs.append(f"{rid}: write-once '{f}' changed {ra.get(f)!r} -> {rb.get(f)!r}")
        for f in spec.history:
            ha, hb = ra.get(f) or [], rb.get(f) or []
            if hb[:len(ha)] != ha:
                errs.append(f"{rid}: history '{f}' rewritten (only appends are allowed)")
    return errs


def write_json(path: Path, obj, *, spec: AppendOnly | None = None, **dump_kw) -> None:
    """The one writer for registry files. Refuses a pinned file; enforces `spec` when given."""
    path = Path(path)
    try:
        rel = _rel(path)
    except ValueError:
        rel = None
    if rel is not None and rel in frozen():
        raise RegistryViolation(f"{rel} is a frozen registration (registry/FROZEN_HASHES.json); "
                                f"write a new version file instead of editing it")
    if spec is not None and path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        errs = check_append_only(old, obj, spec)
        if errs:
            raise RegistryViolation(f"{path.name}: append-only violated - " + "; ".join(errs[:10])
                                    + (f" (+{len(errs) - 10} more)" if len(errs) > 10 else ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_kw.setdefault("indent", 1)
    path.write_text(json.dumps(obj, **dump_kw), encoding="utf-8")


# ── the specs of Pro's live registries (one place) ──────────────────────────────────────────────
SCOUT_HYPOTHESES = AppendOnly(
    entries="list:hypotheses", id_key="id",
    immutable=("id", "league_id", "league", "market", "registered_at"),
    write_once=("confirmation_start",), history=("history",),
    top_immutable=("registry", "version", "criteria", "criteria_sha256", "created_at"))

LEAGUE_LIFECYCLE = AppendOnly(entries="dict", history=("history",))

R2_CHALLENGERS = AppendOnly(
    entries="list:experiments", id_key="id",
    immutable=("id", "market", "track", "recipe", "task", "hypothesis"),
    top_immutable=("version", "common", "pooled_variants", "ablations"))


def build_manifest(paths) -> dict:
    """{"files": {rel: sha}} for `paths` - used once to pin, then the file is committed."""
    return {"about": "Frozen registrations pinned by content SHA-256 (CRLF->LF). src/registry_guard.py "
                     "refuses to write these files and research_integrity FAILS on any drift. A change "
                     "is a NEW version file with its own pin, never an edit.",
            "files": {_rel(p): sha256_lf(p) for p in sorted(paths)}}
