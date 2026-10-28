"""STD-V9R-SHADOW-2026Q4 — the frozen registration and the append-only model-version ledger.

registry/standard_repair/forward_shadow_v1.json
    Written ONCE (2026-10-28, owner-approved). Carries `content_sha256` over every other field;
    `load_registration()` recomputes it and refuses to run on any mismatch, so an edited
    registration can never silently change what a forward row means. A changed hypothesis is a
    new experiment id (…-V2) in a new file.
registry/standard_repair/forward_shadow_v1_aliases.json
    Frozen copy of the identity alias map (Pro output/standard_repair/identity_aliases.json as of
    registration); its sha256 is in the registration. Re-running the benchmark cannot move it.
registry/standard_repair/forward_shadow_models.json
    Append-only ledger. Every TRAIN run appends ONE new immutable model version (payload sha256s,
    the release that stores the payloads, v9 commit the recipe ran from, training cutoff, feature
    manifest, library versions). An existing version is never edited or replaced; `append_version`
    refuses a duplicate id or a changed earlier entry. Scoring picks the newest version trained
    strictly before the scoring time and every forward row records which version scored it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

REG_DIR = cfg.REGISTRY_DIR / "standard_repair"
REGISTRATION = REG_DIR / "forward_shadow_v1.json"
ALIASES = REG_DIR / "forward_shadow_v1_aliases.json"
LEDGER = REG_DIR / "forward_shadow_models.json"
EXPERIMENT_ID = "STD-V9R-SHADOW-2026Q4"
PHASE = "POST_REPAIR_FORWARD"


class RegistrationError(RuntimeError):
    """The frozen registration or the model ledger failed an integrity check. Never swallowed."""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(path) -> str:
    """sha256 of a TEXT file with line endings normalised to LF: a Windows checkout (autocrlf) and
    the Linux runner then agree on the alias map's identity."""
    return sha256_bytes(Path(path).read_bytes().replace(bytes([13, 10]), bytes([10])))


def content_hash(spec: dict) -> str:
    body = {k: v for k, v in spec.items() if k != "content_sha256"}
    return sha256_bytes(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))


def load_registration(path: Path = REGISTRATION, aliases: Path = ALIASES) -> dict:
    if not path.exists():
        raise RegistrationError(f"registration missing: {path}")
    reg = json.loads(path.read_text(encoding="utf-8"))
    if reg.get("content_sha256") != content_hash(reg):
        raise RegistrationError(f"{path.name}: content_sha256 mismatch - the frozen registration was edited")
    if reg.get("experiment_id") != EXPERIMENT_ID or reg.get("phase") != PHASE:
        raise RegistrationError("registration id / phase changed")
    want = reg["frozen_inputs"]["alias_map"]["sha256"]
    if aliases is not None and (not aliases.exists() or sha256_text(aliases) != want):
        raise RegistrationError("frozen alias map missing or its sha256 differs from the registration")
    return reg


def registered_at(reg: dict) -> pd.Timestamp:
    return pd.Timestamp(reg["registered_at"]).tz_convert("UTC")


# ── model-version ledger ─────────────────────────────────────────────────────────────────────
def load_ledger(path: Path = LEDGER) -> dict:
    if not path.exists():
        return {"experiment_id": EXPERIMENT_ID, "versions": []}
    led = json.loads(path.read_text(encoding="utf-8"))
    for v in led.get("versions", []):
        if v.get("entry_sha256") != content_hash({k: x for k, x in v.items() if k != "entry_sha256"}):
            raise RegistrationError(f"ledger entry {v.get('model_version')} was edited after it was written")
    return led


def append_version(entry: dict, path: Path = LEDGER) -> dict:
    """Append one new immutable model version. Refuses duplicates; earlier entries are verified."""
    need = ("model_version", "trained_at", "training_cutoff", "v9_commit", "release_tag", "assets",
            "feature_manifest", "libs", "recipe_versions")
    miss = [k for k in need if k not in entry]
    if miss:
        raise RegistrationError(f"model version missing {miss}")
    led = load_ledger(path)
    if any(v["model_version"] == entry["model_version"] for v in led["versions"]):
        raise RegistrationError(f"model version {entry['model_version']} already exists; versions are immutable")
    e = dict(entry, experiment_id=EXPERIMENT_ID)
    e["entry_sha256"] = content_hash(e)
    led["versions"].append(e)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(led, indent=1, ensure_ascii=False), encoding="utf-8")
    return e


def active_version(at=None, path: Path = LEDGER) -> dict | None:
    """Newest version trained strictly before `at` (default now)."""
    at = pd.Timestamp(at or pd.Timestamp.now(tz="UTC"))
    at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
    vs = [v for v in load_ledger(path)["versions"] if pd.Timestamp(v["trained_at"]) < at]
    return max(vs, key=lambda v: pd.Timestamp(v["trained_at"])) if vs else None


def verify_assets(version: dict, folder: Path) -> dict[str, Path]:
    """sha256 of every downloaded payload must equal the ledger; returns {asset_name: path}."""
    out = {}
    for name, meta in version["assets"].items():
        p = Path(folder) / name
        if not p.exists():
            raise RegistrationError(f"payload {name} of {version['model_version']} not downloaded")
        got = sha256_file(p)
        if got != meta["sha256"]:
            raise RegistrationError(f"payload {name}: sha256 {got[:12]} != ledger {meta['sha256'][:12]}")
        out[name] = p
    return out
