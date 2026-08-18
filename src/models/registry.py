"""
Model registry, champion/challenger, and the promotion gate.
============================================================
Prompt 1 sections 13, 14 and 19.

The rule this file exists to enforce: RETRAINING PRODUCES A CHALLENGER, NEVER A REPLACEMENT.
v9 retrains every Sunday and the new model simply becomes the model. There is no record of what
it replaced, no comparison on identical out-of-sample data, and nothing that could refuse a
worse model. `promote()` here cannot succeed without evidence.

Promotion evidence is deliberately ordered so the cheap-and-gameable metrics cannot carry a
decision on their own (Prompt 1 metric priority, section 19 pipeline):

    1. MARKET-RELATIVE LogLoss/Brier   does it beat the MARKET, not just the old model
    2. calibration (ECE)               are the probabilities usable as probabilities
    3. real-odds backtest              REAL prices only, never synthetic
    4. CLV                             does it beat the closing line
    5. sample size                     is any of the above believable yet

AUC is recorded and explicitly cannot promote anything: "Never promote solely because AUC
improved." A challenger that improves AUC while degrading market-relative LogLoss is a
challenger that has learned to rank the same information the price already contains.

Every record carries git_sha, model_sha, the training window, row counts, the feature-manifest
hash and the odds policy, so a LIVE signal can answer "which code and data produced this?"
without archaeology.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

# Lifecycle states (Prompt 1 section 3). Orthogonal to signal tier — see src/betting/gates.py.
STATUSES = ("RESEARCH", "PAPER", "SHADOW", "LIVE", "BLOCKED", "RETIRED")

# A challenger must clear all of these to be promotable. Values are intentionally modest:
# the bar is "demonstrably better than the market on enough data", not "spectacular".
GATE = {
    "min_rows_holdout": 1000,          # below this, sample_label is not VALIDATED
    "min_logloss_improvement": 0.0,    # vs MARKET-ONLY, must be strictly positive
    "min_brier_improvement": 0.0,      # both, so one metric cannot carry it alone
    "max_ece": 0.05,
    "require_real_odds": True,
    "min_real_odds_coverage": 0.80,
    "min_clv_n": 150,                  # v11's MIN_CLV_N, same reasoning
    "min_mean_clv_pct": 0.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_manifest(obj) -> str:
    """Stable hash of a feature manifest / config / threshold set, so a silent change to any of
    them shows up as a different model rather than the same model behaving differently."""
    payload = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


@dataclass
class ModelRecord:
    model_id: str
    market: str
    scope: str                       # "standard" | "new_format" | league name | "props:<mkt>"
    version: int = 1
    status: str = "RESEARCH"

    # provenance
    model_sha: str = ""
    git_sha: str = ""
    feature_manifest_hash: str = ""
    config_hash: str = ""
    created_at: str = field(default_factory=_now)

    # training window
    train_start: str = ""
    train_end: str = ""
    train_rows: int = 0
    holdout_start: str = ""
    holdout_end: str = ""
    holdout_rows: int = 0
    validation_type: str = ""        # e.g. "chronological_4block"
    odds_policy: str = "REAL_ONLY"   # REAL_ONLY | ALLOW_SYNTHETIC (diagnostics only)

    # standalone metrics — informational
    auc: float | None = None
    logloss: float | None = None
    brier: float | None = None
    ece: float | None = None

    # market-relative — decisive
    market_logloss: float | None = None
    market_brier: float | None = None
    blend_logloss: float | None = None
    blend_brier: float | None = None
    logloss_improvement: float | None = None
    brier_improvement: float | None = None
    sample_label: str = "INSUFFICIENT_SAMPLE"

    # betting evidence
    real_odds_coverage: float | None = None
    clv_n: int = 0
    mean_clv_pct: float | None = None
    roi: float | None = None
    roi_ci: tuple[float, float] | None = None

    # lifecycle
    promoted_at: str = ""
    retired_at: str = ""
    replaces: str = ""
    notes: str = ""

    def key(self) -> str:
        return f"{self.scope}|{self.market}"


@dataclass
class GateResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def explain(self) -> str:
        if self.passed:
            return "all promotion criteria met"
        return "; ".join(self.reasons)


def evaluate_gate(r: ModelRecord, gate: dict | None = None) -> GateResult:
    """Can this record be promoted to LIVE? Every failure is named.

    Missing evidence FAILS. A challenger with no CLV history and no real-odds backtest is not
    "unproven pending review" — it is not promotable, and saying so plainly is the point.
    """
    g = {**GATE, **(gate or {})}
    res = GateResult(passed=True)

    def need(name: str, ok: bool, why: str) -> None:
        res.checks[name] = bool(ok)
        if not ok:
            res.passed = False
            res.reasons.append(why)

    need("odds_policy_real",
         (not g["require_real_odds"]) or r.odds_policy == "REAL_ONLY",
         f"odds_policy is {r.odds_policy!r}; profitability may only be claimed on REAL odds")
    need("real_odds_coverage",
         r.real_odds_coverage is not None
         and r.real_odds_coverage >= g["min_real_odds_coverage"],
         f"real-odds coverage {r.real_odds_coverage} < {g['min_real_odds_coverage']} "
         f"-> INSUFFICIENT_MARKET_DATA")
    need("holdout_rows", r.holdout_rows >= g["min_rows_holdout"],
         f"final-holdout rows {r.holdout_rows} < {g['min_rows_holdout']}")
    need("sample_validated", r.sample_label == "VALIDATED",
         f"sample_label is {r.sample_label}, not VALIDATED")
    need("market_relative_logloss",
         r.logloss_improvement is not None
         and r.logloss_improvement > g["min_logloss_improvement"],
         f"market-relative logloss improvement {r.logloss_improvement} is not positive — "
         f"the model adds nothing beyond the price")
    need("market_relative_brier",
         r.brier_improvement is not None
         and r.brier_improvement > g["min_brier_improvement"],
         f"market-relative brier improvement {r.brier_improvement} is not positive")
    need("calibration", r.ece is not None and r.ece <= g["max_ece"],
         f"ECE {r.ece} > {g['max_ece']}; probabilities are not usable as probabilities")
    need("clv_sample", r.clv_n >= g["min_clv_n"],
         f"CLV sample {r.clv_n} < {g['min_clv_n']}")
    need("clv_positive",
         r.mean_clv_pct is not None and r.mean_clv_pct > g["min_mean_clv_pct"],
         f"mean CLV {r.mean_clv_pct} is not positive")

    # Recorded, never decisive.
    res.checks["auc_recorded"] = r.auc is not None
    return res


class Registry:
    """JSON-backed model registry. One champion per (scope, market); challengers alongside."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.records: dict[str, ModelRecord] = {}
        if self.path.exists():
            self.load()

    # ── persistence ──────────────────────────────────────────────────────────
    def load(self) -> None:
        d = json.loads(self.path.read_text(encoding="utf-8"))
        for mid, rec in (d.get("models") or {}).items():
            rec = dict(rec)
            if isinstance(rec.get("roi_ci"), list):
                rec["roi_ci"] = tuple(rec["roi_ci"])
            self.records[mid] = ModelRecord(**rec)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"updated_at": _now(),
             "models": {k: asdict(v) for k, v in self.records.items()}},
            indent=2, sort_keys=True, default=str), encoding="utf-8")

    # ── queries ──────────────────────────────────────────────────────────────
    def add(self, r: ModelRecord) -> ModelRecord:
        if r.model_id in self.records:
            raise ValueError(f"model_id {r.model_id!r} already registered")
        self.records[r.model_id] = r
        return r

    def champion(self, scope: str, market: str) -> ModelRecord | None:
        live = [r for r in self.records.values()
                if r.scope == scope and r.market == market and r.status == "LIVE"]
        return max(live, key=lambda r: r.version) if live else None

    def challengers(self, scope: str, market: str) -> list[ModelRecord]:
        return [r for r in self.records.values()
                if r.scope == scope and r.market == market
                and r.status in ("RESEARCH", "PAPER", "SHADOW")]

    # ── promotion ────────────────────────────────────────────────────────────
    def promote(self, model_id: str, *, gate: dict | None = None,
                beat_champion: bool = True) -> GateResult:
        """Promote to LIVE only on evidence. Retires the incumbent on success.

        `beat_champion` additionally requires the challenger to improve on the CURRENT champion's
        market-relative logloss. Without it, a challenger could pass the absolute gate while
        being worse than what is already running.
        """
        r = self.records.get(model_id)
        if r is None:
            raise KeyError(model_id)
        if r.status == "RETIRED":
            return GateResult(False, {}, ["model is RETIRED"])

        res = evaluate_gate(r, gate)

        champ = self.champion(r.scope, r.market)
        if beat_champion and champ is not None and champ.model_id != r.model_id:
            better = (r.logloss_improvement is not None
                      and champ.logloss_improvement is not None
                      and r.logloss_improvement > champ.logloss_improvement)
            res.checks["beats_champion"] = bool(better)
            if not better:
                res.passed = False
                res.reasons.append(
                    f"does not beat champion {champ.model_id} on market-relative logloss "
                    f"({r.logloss_improvement} vs {champ.logloss_improvement})")

        if not res.passed:
            return res

        if champ is not None and champ.model_id != r.model_id:
            champ.status = "RETIRED"
            champ.retired_at = _now()
            r.replaces = champ.model_id
            r.version = champ.version + 1
        r.status = "LIVE"
        r.promoted_at = _now()
        return res

    def block(self, model_id: str, reason: str) -> None:
        r = self.records[model_id]
        r.status = "BLOCKED"
        r.notes = (r.notes + " | " if r.notes else "") + f"BLOCKED: {reason}"

    def to_table(self):
        import pandas as pd
        return pd.DataFrame([asdict(r) for r in self.records.values()])
