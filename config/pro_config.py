"""
wowzaV9-Pro configuration.
==========================
No season literals anywhere (WORKFLOW_MAP.md section 4: the same rot was found three times in
v9 — COLLECT_SEASONS, af_history seasons, PROP_SEASONS). Everything season-keyed is derived
from the date.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
REGISTRY_DIR = BASE_DIR / "registry"

# ── v9 baseline: read-only, over HTTP ─────────────────────────────────────────
# Pro NEVER writes to v9. Same access pattern wowza-v11 already uses, and like v11 it needs
# no credential: wowza-betting's output is public.
V9_REPO = "NevixAA/wowza-betting"
V9_RAW_BASE = f"https://raw.githubusercontent.com/{V9_REPO}/main"

# Local checkout, strongly preferred over HTTP.
#
# raw.githubusercontent.com RATE-LIMITS unauthenticated requests. Pro's first live CI run
# (2026-08-17, run gh32040766347) died on `HTTP 429 for .../output/predictions.csv` — the same
# failure that had already been diagnosed and fixed in wowza-v11 and should have been applied
# here at the same time. CI now checks out wowza-betting and points V9_LOCAL at it, so the
# hot path never touches raw HTTP; HTTP remains only as a last-resort fallback with backoff.
V9_LOCAL = Path(os.getenv("V9_LOCAL") or (BASE_DIR.parent / "v9"))


# ── season derivation ─────────────────────────────────────────────────────────
def season_start_year(today: date | None = None) -> int:
    """European football seasons start in July/August; label by START year."""
    d = today or datetime.now(timezone.utc).date()
    return d.year if d.month >= 7 else d.year - 1


def season_label(today: date | None = None) -> str:
    """e.g. 'season_2026_27' — the season store partition root."""
    y = season_start_year(today)
    return f"season_{y}_{str(y + 1)[-2:]}"


def season_dir(today: date | None = None) -> Path:
    return DATA_DIR / season_label(today)


# ── run identity ──────────────────────────────────────────────────────────────
def run_id() -> str:
    """Unique per execution. Run-partitioned writes are what make concurrent collectors
    safe: two runs can never target the same file, so there is no conflict surface and
    nothing can be resolved away by `-X ours` (WORKFLOW_MAP.md section 2)."""
    gh = os.getenv("GITHUB_RUN_ID")
    if gh:
        return f"gh{gh}-{os.getenv('GITHUB_RUN_ATTEMPT', '1')}"
    return "local" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── season store tables (Prompt 2 section 4) ──────────────────────────────────
TABLES = (
    "fixtures",
    "model_snapshots",
    "market_snapshots",
    "feature_snapshots",
    "signals",
    "settlements",
    "clv",
    "player_props",
    "live_signals",
    "data_quality",
)

# Columns every row carries, added by the store itself — never by an importer.
PROVENANCE_COLS = (
    "ingested_at",     # when Pro wrote the row
    "observed_at",     # when the fact was TRUE in the world (commit ts for backfill)
    "run_id",          # which Pro execution
    "source",          # which v9 artifact it came from
    "source_sha",      # v9 git sha, when known
    "pro_git_sha",     # Pro code version that produced the row
)

# ── data-quality flags (Prompt 2 section 16) ─────────────────────────────────
# Rows are FLAGGED and KEPT. Never silently dropped (Prompt 2 section 3).
QUALITY_FLAGS = (
    "MARKET_MAPPING_INVALID",
    "ODDS_ORDER_INVALID",
    "MISSING_OPPOSITE_SIDE",
    "STALE_PRICE",
    "LOW_BOOK_COUNT",
    "ENTITY_UNRESOLVED",
    "FEATURE_DEGRADED",
    "MODEL_VERSION_UNKNOWN",
    "SYNTHETIC_ODDS",
    "SETTLEMENT_UNCERTAIN",
)

# ── odds provenance (Prompt 1 section 8) ─────────────────────────────────────
ODDS_SOURCES = ("REAL", "SYNTHETIC", "IMPUTED", "UNKNOWN")

# ── control groups (Prompt 2 section 9) ──────────────────────────────────────
# Recorded at write time so E[CLV | residual] is computable later without re-deriving.
RESIDUAL_BANDS = ((-1e9, 0.0), (0.0, 0.02), (0.02, 0.04), (0.04, 0.06),
                  (0.06, 0.08), (0.08, 0.10), (0.10, 1e9))
ODDS_BANDS = ((1.20, 1.50), (1.50, 1.75), (1.75, 2.00),
              (2.00, 2.50), (2.50, 3.50), (3.50, 1e9))


def band_label(value: float | None, bands) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    for lo, hi in bands:
        if lo <= v < hi:
            lo_s = "<0" if lo <= -1e8 else f"{lo:g}"
            hi_s = "+" if hi >= 1e8 else f"{hi:g}"
            return f"{lo_s}-{hi_s}" if lo > -1e8 else "<0"
    return "UNKNOWN"


# ── deployment modes vs signal tiers (Prompt 1 section 15, Prompt 2 section 12) ──
# Orthogonal. SNIPER + PAPER is valid and expected this season.
SIGNAL_TIERS = ("SNIPER", "MARKSMAN", "VALUABLE", "OBSERVE", "AVOID", "NO_BET")
DEPLOYMENT_MODES = ("LIVE", "PAPER", "RESEARCH", "BLOCKED")

# Pro never bets and never notifies this season.
DEFAULT_DEPLOYMENT_MODE = "RESEARCH"
PRO_MAY_NOTIFY = False
