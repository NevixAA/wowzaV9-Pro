"""
Archive v11's market-movement research observations into the canonical store.
============================================================================
Movement brief section 18. The division of labour is deliberate and one-directional:

    v11   COMPUTES experimental movement observations
    Pro   PRESERVES, version-controls and AUDITS them

So this importer **stores v11's numbers verbatim and recomputes nothing**. The brief says "do
not duplicate conflicting calculations", and a second implementation of `signed_market_move`
living here would eventually disagree with v11's by a sign convention or a bucket boundary, at
which point there would be two answers to one question and no way to tell which the research
was based on. That is the failure mode `model_type_for_league` is duplicated verbatim to avoid.

Pro's contribution is provenance and immutability, not arithmetic:

    source_repo           which repository produced the row
    calculation_sha       the exact v11 commit that computed it (NOT source_sha — see below)
    calculation_version   v11's movement CALC_VERSION — bump it there when the formula changes
    generated_at          when v11 wrote the file
    ingested_at           when Pro archived it

`calculation_version` is the field that makes the archive trustworthy over a season. Movement
figures computed under different definitions must never be pooled, and without a version stamp
they silently would be — a later reader would average a v1 and a v2 residual and get a number
that means nothing. Rows are partitioned by ingest date and run id like every other table, so
re-ingesting after a v11 fix ADDS a new version rather than overwriting the old one. Nothing is
ever deleted.
"""
from __future__ import annotations

import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store

# The columns v11 guarantees. A missing one is recorded as NULL rather than causing the import to
# fail — a schema addition on v11's side must not stop the archive from advancing.
DETAIL_COLS = [
    "fixture_id", "snapshot_id", "entry_ts", "kickoff_ts", "minutes_to_kickoff",
    "league", "model_type",
    "p_model", "p_market_entry", "residual", "abs_residual_pp", "entry_odds", "bet_side",
    "n_books", "market_prob_std", "market_prob_range", "previous_market_move_pp",
    "close_ts", "p_market_close", "close_odds",
    "market_move_pp", "signed_market_move_pp", "toward_wowza",
    "entry_fair_probability", "close_fair_probability",
    "clv_pct", "clv_quality", "quality_not_assessed",
    "residual_band", "abs_residual_band", "time_band",
    "result", "pnl_flat",
]

_NUMERIC = ("minutes_to_kickoff", "p_model", "p_market_entry", "residual", "abs_residual_pp",
            "entry_odds", "n_books", "market_prob_std", "market_prob_range",
            "previous_market_move_pp", "p_market_close", "close_odds", "market_move_pp",
            "signed_market_move_pp", "toward_wowza", "entry_fair_probability",
            "close_fair_probability", "clv_pct", "pnl_flat")

_SRC = "output/v11_market_movement_detail.csv"


def _v11_sha() -> str:
    """v11's HEAD sha from a local clone, else 'unknown'.

    Never guessed and never taken from Pro's own HEAD — a wrong sha is worse than no sha,
    because it points a future investigation at code that did not produce the row.
    """
    if not cfg.V11_LOCAL.exists():
        return "unknown"
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=cfg.V11_LOCAL,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _calc_version() -> str:
    """v11's declared movement calculation version, or 'unversioned'.

    LOCAL CLONE FIRST, THEN RAW HTTP — the same fallback chain `_fetch` uses.
    ==================================================================
    This read `cfg.V11_LOCAL` ONLY, and Pro's workflow does not check out v11. So in CI the path
    did not exist, the read raised, and every row was stamped `unversioned` — while the
    observations themselves arrived fine, because `_fetch` right below DOES fall back to HTTP.

    The effect was invisible until the archive held rows from both environments:

        gh32701766518-1   25,052 rows   calculation_version = 'unversioned'   <- CI
        local...          59,595 rows   calculation_version = '1.0.0'         <- local runs

    `calculation_version` is the field that decides whether rows may be POOLED, so a mixed
    archive silently invalidates every aggregate over it — and the audit's
    "single calculation version" check fires on exactly this, which is how it surfaced.
    """
    for line in _read_v11_text("src/movement.py").splitlines():
        if line.startswith("CALC_VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unversioned"


def _read_v11_json(rel: str) -> dict:
    """A v11 JSON artifact, local clone first then raw HTTP. {} if unavailable.

    Same fallback chain as _read_v11_text, for the same reason: Pro's workflow does not check out
    v11, so a local-only read silently returns nothing in CI — which is exactly how
    calculation_version ended up stamped 'unversioned' on 25,052 rows.
    """
    import json
    p = cfg.V11_LOCAL / rel
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        import urllib.request
        with urllib.request.urlopen(f"{cfg.V11_RAW_BASE}/{rel}", timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}


def _read_v11_text(rel: str) -> str:
    """v11 source file, local clone first then raw HTTP. Empty string if neither works."""
    p = cfg.V11_LOCAL / rel.replace("/", "\\") if "\\" in str(cfg.V11_LOCAL) else \
        cfg.V11_LOCAL / rel
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    try:
        import urllib.request
        with urllib.request.urlopen(f"{cfg.V11_RAW_BASE}/{rel}", timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _fetch() -> pd.DataFrame:
    """v11's detail CSV: local clone first, then raw HTTP."""
    local = cfg.V11_LOCAL / _SRC
    if local.exists():
        return pd.read_csv(local, dtype=str, keep_default_na=False, na_values=[""])
    import time
    import urllib.request
    url = f"{cfg.V11_RAW_BASE}/{_SRC}"
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                import io
                return pd.read_csv(io.BytesIO(r.read()), dtype=str,
                                   keep_default_na=False, na_values=[""])
        except Exception as e:                                    # noqa: BLE001
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"could not read v11 {_SRC} ({last}). Set V11_LOCAL to a wowza_v11 "
                       f"checkout.")


def from_v11_movement() -> list[tuple[str, pd.DataFrame]]:
    """Archive v11's movement detail rows.

    Signature matches the importer contract in current_wowza: no arguments, returns
    [(table, frame)], and pro_collect performs the append with its own run id.

    THE PROVENANCE COLUMN IS `calculation_sha`, NOT `source_sha`. season_store.append does
    `out["source_sha"] = source_sha or ""` unconditionally, and pro_collect passes the collect
    run's V9 sha because every other importer reads v9. So a `source_sha` column set here is
    silently OVERWRITTEN — the first ingest of this table recorded v11 sha 5dcb7030db9e in the
    importer's log and v9's d61fbaf099dd in the stored row, which is provenance that points a
    future investigation at the wrong repository entirely.

    `calculation_sha` cannot collide, and it pairs naturally with `calculation_version`:
    together they say exactly which code computed the number. `source_sha` retains the store's
    meaning — which v9 the archiving run was made against.
    """
    try:
        raw = _fetch()
    except Exception as e:                                        # noqa: BLE001
        print(f"[v11_research] skipped: {e}")
        return []
    if raw.empty:
        print("[v11_research] skipped: v11 detail file is empty")
        return []

    # ── STALENESS GATE (brief section 14) ────────────────────────────────────────────────
    #
    # Pro must not present an old v11 summary as current merely because the file exists. On
    # 2026-08-25 v11's six movement files were TWO DAYS behind their own source — CI recomputed
    # them every 30 minutes and never staged them — while the raw archive was current to the
    # minute. Pro ingested them all the way through without a murmur, because "the file is there
    # and it parses" was the entire check.
    #
    # The rows are still ARCHIVED when stale: they are a real observation of what v11 published,
    # and dropping them would lose history. They are TAGGED instead, so any aggregate can exclude
    # them and no reader can mistake a stale ingest for a current one.
    stale_reason = ""
    health = _read_v11_json("output/v11_research_health.json")
    if not health:
        stale_reason = "V11_RESEARCH_HEALTH_MISSING"
    else:
        verdict = str(health.get("overall", "")).upper()
        mv = health.get("movement") or {}
        if verdict == "FAIL":
            stale_reason = "V11_RESEARCH_STALE"
        elif str(mv.get("freshness_status", "")).upper() in ("WARN", "FAIL"):
            stale_reason = "V11_MOVEMENT_STALE"
        cv = str(health.get("calculation_version", ""))
        if cv and cv != _calc_version():
            stale_reason = stale_reason or "V11_CALC_VERSION_MISMATCH"
    if stale_reason:
        lag = ((health.get("movement") or {}).get("lag_hours") if health else None)
        print(f"[v11_research] WARNING {stale_reason}"
              f"{f' (movement lag {lag}h)' if lag is not None else ''} — rows are archived but "
              f"TAGGED; exclude them from any current-state aggregate")

    d = pd.DataFrame({c: raw[c] if c in raw.columns else pd.NA for c in DETAIL_COLS})
    for c in _NUMERIC:
        d[c] = pd.to_numeric(d[c], errors="coerce")

    now = pd.Timestamp.now(tz="UTC")
    d["source_repo"] = cfg.V11_REPO
    d["calculation_sha"] = _v11_sha()
    d["calculation_version"] = _calc_version()
    # The file's own mtime is when v11 wrote it. Not Pro's clock: those differ by however long
    # the archive lagged, and conflating them would misdate the research.
    src = cfg.V11_LOCAL / _SRC
    d["generated_at"] = (pd.Timestamp(src.stat().st_mtime, unit="s", tz="UTC")
                         .strftime("%Y-%m-%dT%H:%M:%SZ") if src.exists() else pd.NA)
    d["ingested_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Tag every row of a stale ingest. Empty string when fresh, so a filter is trivial
    # and the column is self-describing without a lookup.
    d["research_staleness"] = stale_reason

    missing = [c for c in DETAIL_COLS if c not in raw.columns]
    print(f"[v11_research] {len(d):,} observations over {d['fixture_id'].nunique()} fixtures | "
          f"v11 sha {d['calculation_sha'].iloc[0]} | calc v{d['calculation_version'].iloc[0]} | "
          f"eligible {int((d['clv_quality'] == 'OK').sum()):,}"
          + (f" | MISSING COLUMNS: {missing}" if missing else ""))
    return [("movement_observations", d)]


IMPORTERS = {"movement_observations": from_v11_movement}
