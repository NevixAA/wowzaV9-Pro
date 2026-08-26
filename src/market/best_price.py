"""
Best-executable pricing: stop paying one book's margin.
=======================================================
The single most effective lever found so far, and it needs no model improvement at all.

MEASURED 2026-08-21 on a live 146-fixture board against v9's per-book capture (~12 books/fixture):

    overround actually paid     7.74%  ->  3.19%
    edge gain per fixture       median +1.85pp, p90 +3.97pp, max +6.66pp
    fixtures clearing 4%        34 -> 51   (+17)
    fixtures clearing 8%         9 -> 15   (+6)
    fixtures clearing 12%        3 ->  3   (+0)

WHY IT MATTERS MORE THAN LOWERING A GATE. v9's edge is `p_model - 1/odds`, computed against the RAW
price, so half the overround is subtracted before the model is consulted. On standard leagues the
overround is ~8%, meaning a perfectly calibrated model reports about -4% edge on BOTH sides, and a
reported +8% edge is really a ~12% disagreement with the fair price — which happens on 1.8% of
fixtures. Lowering the gate accepts worse selections; halving the margin makes the SAME selections
profitable. Those are opposite interventions, and only one of them requires nothing to improve.

THE THREE PRICES, AND WHY CONFLATING THEM IS THE CLASSIC ERROR:

    CONSENSUS  median of per-book de-vigged probabilities. The best estimate of what the market
               believes. Use for the PROBABILITY.
    BEST       the highest odds any book offers on the side you want. Use for the EV and the stake,
               because that is what you can actually get.
    MEDIAN     the middle price. Useful only as a sanity reference.

Using BEST as the probability manufactures edge out of one book being an outlier. Using CONSENSUS as
the price understates every edge by the margin. v9 does neither — it uses one book for both.

EXECUTABILITY IS AN ASSUMPTION, NOT A FACT. A price is only "best executable" if an account exists
that will take the bet at that price and at size. `matchbook` and `pinnacle` show up in the data and
both limit or are exchange-priced. So `allowed_books` is a required, explicit input rather than a
default: pricing against 17 books you cannot bet with produces a fictional edge, which is the same
failure as median-imputing a missing feature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

import pandas as pd

from .devig import devig

# Books that are exchanges or well-known limiters. Not excluded automatically — the caller decides
# — but flagged so a price that depends on them is never mistaken for freely available size.
LIMITED_OR_EXCHANGE = frozenset({
    "pinnacle", "matchbook", "smarkets", "betfair_ex_uk", "betfair_ex_eu", "betfair_ex_au",
})

# Below this the median is a small sample wearing a consensus costume.
MIN_BOOKS = 3


@dataclass
class Priced:
    """One fixture-side, priced across the book set."""
    p_consensus: float | None = None      # de-vigged median — the BELIEF
    best_odds: float | None = None        # highest available — the EXECUTABLE price
    best_book: str = ""
    median_odds: float | None = None
    n_books: int = 0
    overround_best: float | None = None   # margin paid when taking best on both sides
    overround_median: float | None = None
    dispersion: float | None = None
    from_limited: bool = False            # best price comes from a limiter/exchange
    reason: str = "no_data"

    @property
    def usable(self) -> bool:
        return (self.p_consensus is not None and self.best_odds is not None
                and self.n_books >= MIN_BOOKS)

    def edge(self, p_model: float, *, blend_weight: float = 0.0) -> float | None:
        """Edge against the BEST executable price, using CONSENSUS as the market belief.

        `blend_weight` optionally shrinks the model toward the market before computing edge, which
        is v11's market-first stance. 0.0 reproduces v9's model-first definition so the two can be
        compared on identical prices.
        """
        if not self.usable or p_model is None:
            return None
        p = (blend_weight * float(p_model) + (1 - blend_weight) * self.p_consensus
             if blend_weight else float(p_model))
        return p - 1.0 / self.best_odds


def price_side(quotes: pd.DataFrame, *, side: str, other_side: str,
               allowed_books: set[str] | None = None,
               book_col: str = "bookmaker", side_col: str = "side",
               odds_col: str = "odds") -> Priced:
    """Price one side of one fixture-market from a frame of per-book quotes.

    `quotes` must cover BOTH sides: de-vigging a single side is impossible, and a one-sided quote
    carries an unknown margin, so including it would bias the consensus by whatever that book
    charges.
    """
    out = Priced()
    if quotes is None or quotes.empty:
        return out
    q = quotes.copy()
    q[odds_col] = pd.to_numeric(q[odds_col], errors="coerce")
    q = q[q[odds_col] > 1.0]
    q[book_col] = q[book_col].astype(str).str.strip()
    q[side_col] = q[side_col].astype(str).str.upper().str.strip()
    if allowed_books is not None:
        q = q[q[book_col].str.lower().isin({b.lower() for b in allowed_books})]
        if q.empty:
            out.reason = "no_allowed_book_priced_this"
            return out

    want = q[q[side_col] == side.upper()].set_index(book_col)[odds_col]
    other = q[q[side_col] == other_side.upper()].set_index(book_col)[odds_col]
    if want.empty:
        out.reason = "side_not_priced"
        return out

    # consensus from books quoting BOTH sides only
    probs: dict[str, float] = {}
    for bk in set(want.index) & set(other.index):
        d = devig(float(want.loc[bk]), float(other.loc[bk]))
        p = getattr(d, "prob", None)
        if p is not None and 0.0 < p < 1.0:
            probs[bk] = float(p)
    out.n_books = len(probs)
    if probs:
        vals = list(probs.values())
        out.p_consensus = float(median(vals))
        if len(vals) > 1:
            mu = sum(vals) / len(vals)
            out.dispersion = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5

    out.best_odds = float(want.max())
    out.best_book = str(want.idxmax())
    out.median_odds = float(median(list(want.values)))
    out.from_limited = out.best_book.lower() in LIMITED_OR_EXCHANGE
    if not other.empty:
        out.overround_best = 1.0 / out.best_odds + 1.0 / float(other.max()) - 1.0
        out.overround_median = (1.0 / out.median_odds
                                + 1.0 / float(median(list(other.values))) - 1.0)
    out.reason = "ok" if out.usable else (
        "too_few_two_sided_books" if out.n_books else "no_two_sided_book")
    return out


@dataclass
class Comparison:
    """v9's single-book edge against the best-executable edge, for one fixture-side."""
    edge_single: float | None = None
    edge_best: float | None = None
    gain: float | None = None
    best_book: str = ""
    n_books: int = 0
    from_limited: bool = False
    overround_single: float | None = None
    overround_best: float | None = None


def compare(p_model: float, single_odds: float, single_other_odds: float,
            priced: Priced) -> Comparison:
    """Quantify what the single-book price costs, on one side.

    Kept as an explicit comparison rather than a silent upgrade: the whole point is to be able to
    show how much margin the current pricing gives away, per fixture, and a number nobody can see
    is a number nobody will act on.
    """
    c = Comparison(best_book=priced.best_book, n_books=priced.n_books,
                   from_limited=priced.from_limited,
                   overround_best=priced.overround_best)
    try:
        c.edge_single = float(p_model) - 1.0 / float(single_odds)
        c.overround_single = 1.0 / float(single_odds) + 1.0 / float(single_other_odds) - 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return c
    c.edge_best = priced.edge(p_model)
    if c.edge_best is not None and c.edge_single is not None:
        c.gain = c.edge_best - c.edge_single
    return c
