"""
Feature candidate registry + admission rule (brief sections 12, 13).
====================================================================

WHY THIS EXISTS

The failure mode it prevents is specific: a feature improves historical AUC, gets added, and
nobody can later say what evidence justified it or whether its coverage was ever checked. Section
13 is explicit that improving AUC is NOT sufficient grounds for production. This is where the
decision and its evidence live together, so "why is this feature in the model" has an answer that
does not depend on remembering.

It is a REGISTRY, not a feature store. Nothing here computes a feature. Each row records what a
candidate is, whether the data actually exists, whether it is timestamp-safe, and what it would
take to promote it.

STATUSES

    PROPOSED      an idea; nothing measured yet
    COLLECTING    data is being accumulated forward; not yet analysable
    RESEARCHABLE  enough coverage and history to test
    VALIDATED     passed the admission rule, not yet wired to production
    REJECTED      tested and failed, or structurally impossible — with the reason
    PRODUCTION    live in a model

FAMILIES: FOOTBALL · MARKET · MICROSTRUCTURE · INFORMATION · QUALITY

THE ADMISSION RULE

A candidate may only reach VALIDATED with:

  * no leakage (mandatory, no exceptions), AND
  * sufficient coverage (mandatory), AND
  * at least one of: chronological improvement, calibration improvement, market-relative
    improvement, or movement/CLV improvement.

`evaluate()` enforces exactly that, and deliberately does NOT accept `auc_improvement` as
qualifying evidence on its own — passing only AUC returns a refusal naming the reason. Section 24
also rules out ROI as a selection target, so `roi_improvement` is accepted as a field but never
counts toward admission.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import pandas as pd

# Statuses
PROPOSED = "PROPOSED"
COLLECTING = "COLLECTING"
RESEARCHABLE = "RESEARCHABLE"
VALIDATED = "VALIDATED"
REJECTED = "REJECTED"
PRODUCTION = "PRODUCTION"

# Families
FOOTBALL = "FOOTBALL"
MARKET = "MARKET"
MICROSTRUCTURE = "MICROSTRUCTURE"
INFORMATION = "INFORMATION"
QUALITY = "QUALITY"

MIN_COVERAGE_PCT = 60.0     # below this a feature is mostly imputation

# Evidence kinds that can support admission. AUC is absent on purpose (section 13).
QUALIFYING_EVIDENCE = ("chronological_improvement", "calibration_improvement",
                       "market_relative_improvement", "movement_clv_improvement")


@dataclass
class Candidate:
    feature_name: str
    feature_family: str
    research_priority: str                  # P0 | P1 | P2 | P3
    production_status: str = PROPOSED
    data_available: bool = False
    historically_available: bool = False    # can it be backfilled, or forward-only?
    timestamp_safe: bool | None = None      # None = not yet established
    coverage_pct: float | None = None
    missing_pct: float | None = None
    expected_value: str = ""                # what we think it buys, in words
    evidence: dict = field(default_factory=dict)
    decision_note: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        ev = d.pop("evidence")
        d["evidence"] = "|".join(f"{k}={v}" for k, v in sorted(ev.items())) if ev else ""
        return d


def evaluate(c: Candidate) -> tuple[bool, str]:
    """(admissible, reason). The gate, not a suggestion."""
    if c.timestamp_safe is not True:
        return False, ("leakage safety not established — mandatory and not waivable, whatever "
                       "the performance evidence says")
    if c.coverage_pct is None:
        return False, "coverage never measured"
    if c.coverage_pct < MIN_COVERAGE_PCT:
        return False, (f"coverage {c.coverage_pct:.1f}% is below {MIN_COVERAGE_PCT:.0f}% — the "
                       f"feature would mostly be imputed, and a median-imputed input produces a "
                       f"confident-looking wrong answer rather than a cautious one")
    qualifying = [k for k in QUALIFYING_EVIDENCE if c.evidence.get(k)]
    if not qualifying:
        has_auc = bool(c.evidence.get("auc_improvement"))
        return False, ("AUC improvement alone is not admissible evidence (section 13); needs "
                       "chronological, calibration, market-relative or movement/CLV improvement"
                       if has_auc else "no qualifying evidence recorded")
    return True, "admissible on: " + ", ".join(qualifying)


# ─────────────────────────────────────────────────────────────────────────────
# The register. Coverage figures below are MEASURED, not estimated — they come from
# wowza_v11/output/v11_microstructure_coverage.csv (33,094 snapshot rows, 2026-08-27).
# ─────────────────────────────────────────────────────────────────────────────
CANDIDATES: list[Candidate] = [
    # ── MICROSTRUCTURE — built and measured ──────────────────────────────────
    Candidate("velocity_3h", MICROSTRUCTURE, "P0", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=84.4, missing_pct=15.6,
              expected_value="distinguishes a static market from one already moving — the "
                             "control section 20 needs",
              evidence={"leakage_test": "PASS (future-corruption test, 100% identical)"},
              decision_note="Best-covered window. Forward-only: cannot be backfilled, since it "
                            "needs our own poll history."),
    Candidate("velocity_1h", MICROSTRUCTURE, "P0", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=69.1, missing_pct=30.9,
              expected_value="shorter-horizon momentum",
              evidence={"leakage_test": "PASS"}),
    Candidate("velocity_6h", MICROSTRUCTURE, "P1", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=73.4, missing_pct=26.6,
              expected_value="longer-horizon momentum",
              evidence={"leakage_test": "PASS"}),
    Candidate("market_acceleration", MICROSTRUCTURE, "P1", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=63.0, missing_pct=37.0,
              expected_value="is the market speeding up (velocity_1h - velocity_3h)",
              evidence={"leakage_test": "PASS"},
              decision_note="Only just above the coverage floor; needs both windows present."),
    Candidate("move_from_open_pp", MICROSTRUCTURE, "P0", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=98.5, missing_pct=1.5,
              expected_value="total drift since the first observed price",
              evidence={"leakage_test": "PASS"},
              decision_note="Was named previous_market_move_pp in the movement script; renamed "
                            "because it is move-from-open, not last-move."),
    Candidate("last_move_pp", MICROSTRUCTURE, "P0", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=98.5, missing_pct=1.5,
              expected_value="the brief's last_move_pp, which did not previously exist",
              evidence={"leakage_test": "PASS"}),
    Candidate("reversal_count", MICROSTRUCTURE, "P2", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=100.0, missing_pct=0.0,
              expected_value="how choppy the path has been",
              evidence={"leakage_test": "PASS"},
              decision_note="Off-by-one found by unit test: the count excluded the move into the "
                            "current snapshot, which IS known at that timestamp. Fixed."),
    Candidate("velocity_30m", MICROSTRUCTURE, "P0", REJECTED,
              data_available=False, historically_available=False,
              timestamp_safe=True, coverage_pct=0.0, missing_pct=100.0,
              expected_value="would have separated a market moving RIGHT NOW from a slow drift",
              evidence={"measured_poll_gap_min": 33.6},
              decision_note="REJECTED on data, not on merit. Median inter-snapshot gap is 33.6 "
                            "min — longer than the window. Non-null only for unrepresentatively "
                            "densely-sampled fixtures, so it would be worse than absent. Kept as "
                            "an explicit NaN column so it reads as considered, not forgotten. "
                            "Revisit only if polling inside 6h of kickoff gets denser."),
    Candidate("market_prob_range", MICROSTRUCTURE, "P1", REJECTED,
              data_available=False, timestamp_safe=None,
              coverage_pct=0.0, missing_pct=100.0,
              expected_value="best-worst spread across books",
              decision_note="0% populated upstream; only std is carried. Needs the per-book "
                            "collection change below."),
    Candidate("book_dispersion_std", MICROSTRUCTURE, "P0", RESEARCHABLE,
              data_available=True, historically_available=False,
              timestamp_safe=True, coverage_pct=70.7, missing_pct=29.3,
              expected_value="does the residual work better against a tight or a loose consensus",
              evidence={"leakage_test": "PASS (passed through from book_consensus, not recomputed)"},
              decision_note="Tight-consensus tercile showed the study's largest apparent edge "
                            "(+10.87pp) at n=46 — reserved for out-of-time confirmation, NOT "
                            "actioned. Coverage falls to 46% at the earliest entry point."),
    Candidate("per_book_quotes", MICROSTRUCTURE, "P0", PROPOSED,
              data_available=False, historically_available=False, timestamp_safe=None,
              expected_value="the single highest-value collection change: unlocks bookmaker "
                             "lead/lag, sharp-vs-consensus, and real dispersion coverage",
              decision_note="Per-book prices are consumed inside book_consensus.build_index and "
                            "never persisted. Must be collected FORWARD — no historical purchase "
                            "exists. Blocks brief sections 6 and 7 entirely."),

    # ── MARKET ───────────────────────────────────────────────────────────────
    Candidate("wowza_residual", MARKET, "P0", REJECTED,
              data_available=True, historically_available=True,
              timestamp_safe=True, coverage_pct=100.0, missing_pct=0.0,
              expected_value="the core hypothesis: disagreement predicts future price movement",
              evidence={"toward_rate": "58.00% (N=300)",
                        "placebo_anchor": "58.33% — model-free baseline MATCHES it",
                        "logistic": "z=1.71 alone, 1.51 controlled; never significant",
                        "clv_ci": "[-0.168, +1.230] includes zero"},
              decision_note="REJECTED as a movement predictor on current evidence. corr with a "
                            "pure mean-reversion term is +0.833 (83% sign agreement) because the "
                            "model's sd is 0.564x the market's — 'moved toward Wowza' and 'moved "
                            "toward the middle' are largely one statement. Not rejected as a "
                            "football feature; that is a different question."),

    # ── INFORMATION ──────────────────────────────────────────────────────────
    Candidate("team_news_known_at", INFORMATION, "P2", PROPOSED,
              data_available=False, historically_available=False, timestamp_safe=None,
              expected_value="lets a feature use news only from after it was public — the "
                             "prerequisite for any information-timing work",
              decision_note="Schema defined in src/schemas.py; team_news is PLANNED_OPTIONAL and "
                            "correctly empty. Blocked on a source that publishes an event WITH "
                            "its publication time. Do NOT populate with synthetic rows."),

    # ── FOOTBALL — section 14, research only, behind a data-quality review ───
    Candidate("team_xg", FOOTBALL, "P3", RESEARCHABLE,
              data_available=True, historically_available=True,
              timestamp_safe=True, coverage_pct=88.3, missing_pct=11.7,
              expected_value="better per-team goal-rate estimation than goals scored",
              evidence={"market_relative_improvement": "+0.0323 vs goals, bootstrap CI excludes "
                                                       "zero (measured earlier in Pro)"},
              decision_note="The strongest football candidate on record. /fixtures/statistics "
                            "persists historically, unlike /odds, so this IS backfillable — "
                            "23,604 rows already collected."),
    Candidate("non_penalty_xg", FOOTBALL, "P3", REJECTED,
              data_available=False, timestamp_safe=None, coverage_pct=0.0,
              expected_value="removes penalty noise from attacking strength",
              decision_note="Provider does not separate it; would need event-level data we do "
                            "not collect."),
    Candidate("big_chances", FOOTBALL, "P3", REJECTED,
              data_available=False, timestamp_safe=None, coverage_pct=0.0,
              expected_value="higher-signal chance quality",
              decision_note="Sofascore-style metric, absent from the api-football payload."),
    Candidate("first_half_xg", FOOTBALL, "P3", REJECTED,
              data_available=False, timestamp_safe=None, coverage_pct=0.0,
              expected_value="would feed the HT market directly",
              decision_note="Statistics are full-match totals with no half split."),
    Candidate("rest_days", FOOTBALL, "P3", PROPOSED,
              data_available=True, historically_available=True, timestamp_safe=None,
              expected_value="fatigue and congestion effects",
              decision_note="Derivable from the fixtures table alone, so cheap. Timestamp safety "
                            "trivial (fixture dates are known in advance). Untested."),
]


def to_frame() -> pd.DataFrame:
    rows = []
    for c in CANDIDATES:
        r = c.to_row()
        ok, why = evaluate(c)
        r["admissible_now"] = ok
        r["admission_note"] = why
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> int:
    df = to_frame()
    print(df[["feature_name", "feature_family", "research_priority", "production_status",
              "coverage_pct", "timestamp_safe", "admissible_now"]].to_string(index=False))
    print(f"\n{len(df)} candidates · "
          + " · ".join(f"{k}={v}" for k, v in df["production_status"].value_counts().items()))
    adm = df[df["admissible_now"]]
    print(f"\nadmissible under the section-13 rule right now: {len(adm)}")
    for _, r in adm.iterrows():
        print(f"  {r['feature_name']}: {r['admission_note']}")
    if adm.empty:
        print("  none — and that is the expected answer while no candidate has qualifying "
              "evidence recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
