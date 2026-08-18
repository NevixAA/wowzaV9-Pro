"""
Deployment gate: signal strength and permission to bet are different things.
===========================================================================
Prompt 1 section 15 and Prompt 2 section 12, which state it twice because it is the distinction
v9 does not make:

    SNIPER / MARKSMAN / VALUABLE / AVOID   = SIGNAL TIER      how strong the signal is
    LIVE / PAPER / RESEARCH / BLOCKED      = DEPLOYMENT MODE  whether it may be staked

    SNIPER + PAPER is valid and expected this season.

In v9 the tier IS the decision — a SNIPER gets a full stake because it is a SNIPER. Nothing
consults whether the model behind it was validated, whether its league was approved, whether its
features were healthy, or whether the odds were real. So a model with a leaky ensemble and a
blind fixture can produce a full-stake bet, which is exactly what happened: a fixture with no
rolling-form history showed the second-strongest edge on the board at 4.4%, built on nothing.

`decide()` keeps the tier untouched — it is the model's opinion and Prompt 2 requires storing it
either way — and returns a SEPARATE permission with every reason recorded. A PAPER signal still
notifies, is settled, and earns CLV (Prompt 2 section 11). Downgrading is never silent.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

# Tiers that would be staked if permission allowed. VALUABLE is collection-only by standing
# decision: only SNIPER and MARKSMAN are ever staked, VALUABLE is a flash to gather outcomes.
STAKED_TIERS = ("SNIPER", "MARKSMAN")
COLLECT_TIERS = ("VALUABLE",)
NON_SIGNAL_TIERS = ("AVOID", "NO_BET", "WATCH", "OBSERVE")

MODES = ("LIVE", "PAPER", "RESEARCH", "BLOCKED")


@dataclass
class GateInputs:
    """Everything the gate consults. Absent evidence is not neutral — it blocks."""
    signal_tier: str
    model_status: str = "RESEARCH"       # from the model registry
    league_approved: bool = False
    market_approved: bool = False
    feature_health_ok: bool = True
    entity_resolved: bool = True
    odds_source: str = "UNKNOWN"         # REAL | SYNTHETIC | IMPUTED | UNKNOWN
    odds_two_sided: bool = False
    book_count: int = 0
    price_age_minutes: float | None = None
    minutes_to_kickoff: float | None = None
    model_validated: bool = False
    clv_n: int = 0
    quality_flags: tuple[str, ...] = ()


@dataclass
class Decision:
    signal_tier: str                     # unchanged — the model's opinion
    mode: str                            # permission
    stake_multiplier: float
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def as_row(self) -> dict:
        d = asdict(self)
        d["reasons"] = "|".join(self.reasons)
        d["blockers"] = "|".join(self.blockers)
        return d


MAX_PRICE_AGE_MIN = 30.0
MIN_BOOKS_FOR_LIVE = 2


def decide(i: GateInputs, *, pro_may_stake: bool = False) -> Decision:
    """Map a signal onto a deployment mode.

    `pro_may_stake` is False for the whole of season 2026/27: Pro never stakes and never
    notifies. It is a parameter rather than a constant so the gate logic can be tested for the
    season where it might, without that season being now.
    """
    tier = str(i.signal_tier or "AVOID").upper()
    d = Decision(signal_tier=tier, mode="RESEARCH", stake_multiplier=0.0)

    # Hard blocks first — these are not downgrades, they are refusals.
    if tier in NON_SIGNAL_TIERS:
        d.mode = "RESEARCH"
        d.reasons.append(f"tier {tier} is not a signal; recorded for research only")
        return d
    if i.model_status == "BLOCKED":
        d.mode, _ = "BLOCKED", d.blockers.append("model status is BLOCKED")
        return d
    if not i.entity_resolved or "ENTITY_UNRESOLVED" in i.quality_flags:
        d.mode = "BLOCKED"
        d.blockers.append("entity unresolved — a blind fixture cannot be staked")
        return d
    if not i.feature_health_ok or "FEATURE_DEGRADED" in i.quality_flags:
        d.mode = "BLOCKED"
        d.blockers.append("features degraded — imputation would make an unknown row look "
                          "ordinary")
        return d
    if i.minutes_to_kickoff is not None and i.minutes_to_kickoff <= 0:
        d.mode = "BLOCKED"
        d.blockers.append("kickoff has passed — pre-match logic cannot price an in-play match")
        return d

    # Reasons a signal is real but not stakeable. Each records itself; none is silent.
    if not i.model_validated or i.model_status not in ("LIVE",):
        d.blockers.append(f"model not validated for LIVE (status={i.model_status})")
    if not i.league_approved:
        d.blockers.append("league not approved")
    if not i.market_approved:
        d.blockers.append("market not approved")
    if i.odds_source != "REAL":
        d.blockers.append(f"odds_source={i.odds_source}; only REAL prices may be staked")
    if not i.odds_two_sided:
        d.blockers.append("one-sided market — cannot de-vig honestly")
    if i.book_count < MIN_BOOKS_FOR_LIVE:
        d.blockers.append(f"book_count={i.book_count} < {MIN_BOOKS_FOR_LIVE}")
    if i.price_age_minutes is not None and i.price_age_minutes > MAX_PRICE_AGE_MIN:
        d.blockers.append(f"price is {i.price_age_minutes:.0f}m old (> {MAX_PRICE_AGE_MIN:.0f})")
    if "STALE_PRICE" in i.quality_flags:
        d.blockers.append("price flagged stale")
    if i.clv_n < 150:
        d.blockers.append(f"CLV sample {i.clv_n} < 150 — cannot yet claim it beats the close")
    if not pro_may_stake:
        d.blockers.append("Pro does not stake this season (data-collection season)")

    if d.blockers:
        # A strong signal that cannot be staked is PAPER, not discarded: it still notifies, is
        # settled and earns CLV (Prompt 2 section 11). This is the SNIPER+PAPER case.
        d.mode = "PAPER" if tier in STAKED_TIERS + COLLECT_TIERS else "RESEARCH"
        d.reasons.append(f"tier {tier} retained; not stakeable ({len(d.blockers)} blocker(s))")
        return d

    d.mode = "LIVE"
    d.stake_multiplier = {"SNIPER": 1.0, "MARKSMAN": 0.75}.get(tier, 0.0)
    d.reasons.append("all deployment criteria met")
    return d
