"""
Multi-book consensus and dispersion.
====================================
Prompt 1 section 10 and Prompt 2 section 13; Prompt 3 section 7 calls it "a high-priority
missing component". Neither v9 nor v11 has it: v11's market_baseline() returns a median fair
probability and nothing else, and collection is effectively single-book.

The distinction this module exists to enforce, stated plainly in Prompt 3 section 7:

    CONSENSUS PROBABILITY and BEST EXECUTABLE ODDS ARE DIFFERENT CONCEPTS.

Consensus answers "what does the market think" — the median of de-vigged book prices, the
sharpest available estimate of the true probability. Best executable answers "what can I
actually get on" — the single longest price with a book attached. Edge is measured against
consensus; EV is computed on executable odds. Using the best price as the probability estimate
is how you convince yourself an outlier book is an edge when it is usually a stale quote.

Dispersion is collected but NOT interpreted (Prompt 3 section 8: "Collect now; do not assume
the profitable interpretation in advance"). Whether wide disagreement means opportunity or
means one book is wrong is an empirical question this season should answer, not an assumption
to build in now.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field, asdict

from src.market.devig import devig, DevigResult


@dataclass
class BookQuote:
    """One bookmaker's two-sided price for one market at one instant."""
    bookmaker: str
    over_odds: float | None
    under_odds: float | None
    timestamp: str = ""
    is_exchange: bool = False


@dataclass
class Consensus:
    # --- what the market thinks ---
    fair_prob: float | None = None          # consensus de-vigged probability (OVER side)
    fair_prob_median: float | None = None
    fair_prob_mean: float | None = None
    fair_prob_std: float | None = None      # dispersion, section 8
    fair_prob_range: float | None = None
    fair_prob_min: float | None = None
    fair_prob_max: float | None = None
    source: str = "none"                    # exchange | cross_book_median | single_book | none

    # --- what you can actually bet ---
    best_over_odds: float | None = None
    best_over_book: str = ""
    best_under_odds: float | None = None
    best_under_book: str = ""
    median_over_odds: float | None = None
    min_over_odds: float | None = None
    max_over_odds: float | None = None

    # --- how much to trust it ---
    n_books: int = 0                        # books that produced a VALID fair probability
    n_books_seen: int = 0                   # books offered, valid or not
    n_quarantined: int = 0
    mean_overround: float | None = None
    timestamp: str = ""
    quality_flags: list[str] = field(default_factory=list)
    per_book: dict[str, float] = field(default_factory=dict)
    quarantined: dict[str, str] = field(default_factory=dict)   # book -> reason

    def as_row(self) -> dict:
        d = asdict(self)
        d["quality_flags"] = "|".join(sorted(set(self.quality_flags)))
        d["per_book"] = ";".join(f"{k}={v:.4f}" for k, v in sorted(self.per_book.items()))
        d["quarantined"] = ";".join(f"{k}={v}" for k, v in sorted(self.quarantined.items()))
        return d


# A single book is not a consensus. Below this the row is usable but flagged, so a later
# analysis can separate "the market said" from "one book said".
MIN_BOOKS_FOR_CONSENSUS = 3


def build_consensus(quotes: list[BookQuote], *, timestamp: str = "") -> Consensus:
    """Fold per-book quotes into one consensus row.

    Every book is de-vigged INDEPENDENTLY before averaging. Averaging raw odds first and
    de-vigging the average would blend different margins together and produce a probability
    no book ever offered.
    """
    c = Consensus(timestamp=timestamp)
    if not quotes:
        c.quality_flags.append("MARKET_MAPPING_INVALID")
        return c

    c.n_books_seen = len(quotes)
    exchange_prob: float | None = None
    overrounds: list[float] = []

    for q in quotes:
        r: DevigResult = devig(q.over_odds, q.under_odds)
        if not r.valid or r.prob is None:
            c.quarantined[q.bookmaker] = r.reason or "MARKET_MAPPING_INVALID"
            continue
        c.per_book[q.bookmaker] = r.prob
        if r.overround is not None:
            overrounds.append(r.overround)
        if q.is_exchange:
            exchange_prob = r.prob

        # Best executable = longest price actually on offer, tracked per side with its book.
        try:
            o = float(q.over_odds)
            if c.best_over_odds is None or o > c.best_over_odds:
                c.best_over_odds, c.best_over_book = o, q.bookmaker
        except (TypeError, ValueError):
            pass
        try:
            u = float(q.under_odds)
            if c.best_under_odds is None or u > c.best_under_odds:
                c.best_under_odds, c.best_under_book = u, q.bookmaker
        except (TypeError, ValueError):
            pass

    c.n_quarantined = len(c.quarantined)
    probs = list(c.per_book.values())
    if not probs:
        c.quality_flags.append("MARKET_MAPPING_INVALID")
        return c

    c.n_books = len(probs)
    c.fair_prob_median = round(statistics.median(probs), 6)
    c.fair_prob_mean = round(statistics.fmean(probs), 6)
    c.fair_prob_std = round(statistics.pstdev(probs), 6) if len(probs) > 1 else 0.0
    c.fair_prob_min, c.fair_prob_max = round(min(probs), 6), round(max(probs), 6)
    c.fair_prob_range = round(c.fair_prob_max - c.fair_prob_min, 6)
    if overrounds:
        c.mean_overround = round(statistics.fmean(overrounds), 6)

    # Exchange first: it is a traded price, not a quoted one, so it carries no margin of the
    # kind de-vigging has to guess at. Then the cross-book median. A single book last, flagged.
    if exchange_prob is not None:
        c.fair_prob, c.source = exchange_prob, "exchange"
    elif len(probs) >= 2:
        c.fair_prob, c.source = c.fair_prob_median, "cross_book_median"
    else:
        c.fair_prob, c.source = probs[0], "single_book"

    ovr_odds = [float(q.over_odds) for q in quotes
                if q.bookmaker in c.per_book and _is_num(q.over_odds)]
    if ovr_odds:
        c.median_over_odds = round(statistics.median(ovr_odds), 4)
        c.min_over_odds, c.max_over_odds = round(min(ovr_odds), 4), round(max(ovr_odds), 4)

    if c.n_books < MIN_BOOKS_FOR_CONSENSUS:
        c.quality_flags.append("LOW_BOOK_COUNT")
    if c.n_quarantined:
        c.quality_flags.append("MARKET_MAPPING_INVALID")
    return c


def _is_num(v) -> bool:
    try:
        return float(v) > 1.0
    except (TypeError, ValueError):
        return False


def model_edge(p_model: float | None, c: Consensus) -> float | None:
    """Edge = model probability - CONSENSUS fair probability (Prompt 1 section 10).

    Deliberately not measured against the best executable price: that would fold the
    bookmaker's generosity into the model's apparent skill.
    """
    if p_model is None or c.fair_prob is None:
        return None
    return round(float(p_model) - c.fair_prob, 6)


def ev_on_executable(p_model: float | None, c: Consensus, *, side: str = "OVER",
                     tx_cost: float = 0.0) -> float | None:
    """EV computed on the odds you could actually take, not on the consensus.

    Consensus sets the probability; the executable price sets the payout. Mixing them —
    consensus probability against consensus odds — understates what a real bet returns, and
    best-price probability against best price overstates it.
    """
    if p_model is None:
        return None
    odds = c.best_over_odds if side.upper() == "OVER" else c.best_under_odds
    if odds is None or odds <= 1.0:
        return None
    p = float(p_model) if side.upper() == "OVER" else 1.0 - float(p_model)
    return round(p * odds - 1.0 - tx_cost, 6)
