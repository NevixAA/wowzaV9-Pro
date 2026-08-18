"""
Phase 2 market layer. Prompt 1 required tests: de-vig probabilities are mathematically valid,
invalid market mappings are quarantined.

    python -m tests.test_market
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.market.consensus import (BookQuote, build_consensus, ev_on_executable,  # noqa: E402
                                 model_edge)
from src.market.devig import (devig, overround, power_devig,  # noqa: E402
                              proportional_devig)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def main() -> int:
    print("\n== de-vig is mathematically valid ==")
    r = devig(2.00, 2.00)
    check("fair 50/50 -> 0.5", r.valid and abs(r.prob - 0.5) < 1e-6, str(r))
    check("overround of a fair market is 1.0", abs(r.overround - 1.0) < 1e-6, str(r.overround))

    r = devig(1.80, 2.10)
    check("typical market gives a valid probability", r.valid and 0 < r.prob < 1, str(r))
    check("overround above 1 for a real market", r.overround > 1.0, str(r.overround))

    # Both sides must sum to 1 after de-vigging — the defining property.
    a = power_devig(1.80, 2.10)
    b = power_devig(2.10, 1.80)
    check("the two sides sum to 1", abs((a + b) - 1.0) < 1e-6, f"{a}+{b}")

    check("short price -> higher probability", power_devig(1.40, 3.20) > power_devig(3.20, 1.40))
    check("power differs from proportional on a skewed pair",
          abs(power_devig(1.20, 5.50) - proportional_devig(1.20, 5.50)) > 1e-6,
          "identical would mean the power method is not doing anything")

    print("\n== dishonest inputs are refused, with a reason ==")
    for label, args, want in [
        ("one-sided (no under)", (1.90, None), "MISSING_OPPOSITE_SIDE"),
        ("one-sided (no over)", (None, 1.90), "MISSING_OPPOSITE_SIDE"),
        ("both missing", (None, None), "MARKET_MAPPING_INVALID"),
        ("odds <= 1.0", (1.0, 2.0), "MISSING_OPPOSITE_SIDE"),
        ("arbitrage (overround < 1)", (2.20, 2.20), "ODDS_ORDER_INVALID"),
        ("absurd margin", (1.10, 1.10), "STALE_PRICE"),
        ("non-numeric", ("x", "y"), "MARKET_MAPPING_INVALID"),
    ]:
        r = devig(*args)
        check(f"{label} -> {want}", (not r.valid) and r.reason == want,
              f"valid={r.valid} reason={r.reason}")
    check("a refused de-vig returns no probability", devig(1.9, None).prob is None)

    print("\n== consensus: probability and executable price are different things ==")
    quotes = [
        BookQuote("bookA", 1.90, 2.00),
        BookQuote("bookB", 1.95, 1.95),
        BookQuote("bookC", 2.10, 1.82),      # the outlier, longest Over
    ]
    c = build_consensus(quotes, timestamp="2026-08-20T12:00:00Z")
    check("all three books de-vigged", c.n_books == 3, str(c.n_books))
    check("consensus is the cross-book median", c.source == "cross_book_median", c.source)
    check("best executable is the LONGEST over price", c.best_over_odds == 2.10,
          str(c.best_over_odds))
    check("best executable names its book", c.best_over_book == "bookC", c.best_over_book)
    check("consensus prob is NOT the outlier's prob",
          abs(c.fair_prob - c.per_book["bookC"]) > 1e-9,
          "using the best price as the probability is the classic error")
    check("dispersion recorded", c.fair_prob_std > 0 and c.fair_prob_range > 0,
          f"std={c.fair_prob_std} range={c.fair_prob_range}")
    check("min/max tracked", c.fair_prob_min < c.fair_prob_max)

    print("\n== exchange outranks the book median ==")
    ce = build_consensus(quotes + [BookQuote("betfair", 2.02, 1.98, is_exchange=True)])
    check("exchange becomes the source", ce.source == "exchange", ce.source)

    print("\n== quarantine, not silent drop ==")
    mixed = [BookQuote("good", 1.90, 2.00), BookQuote("onesided", 1.90, None),
             BookQuote("arb", 2.20, 2.20)]
    cq = build_consensus(mixed)
    check("valid book still used", cq.n_books == 1, str(cq.n_books))
    check("bad books quarantined with a reason", len(cq.quarantined) == 2, str(cq.quarantined))
    check("quarantined reasons are specific",
          cq.quarantined.get("onesided") == "MISSING_OPPOSITE_SIDE"
          and cq.quarantined.get("arb") == "ODDS_ORDER_INVALID", str(cq.quarantined))
    check("every offered book is still counted", cq.n_books_seen == 3, str(cq.n_books_seen))
    check("single surviving book is flagged", "LOW_BOOK_COUNT" in cq.quality_flags,
          str(cq.quality_flags))
    check("source records it was one book", cq.source == "single_book", cq.source)

    print("\n== nothing usable -> flagged, never a fabricated number ==")
    cn = build_consensus([BookQuote("bad", None, None)])
    check("no fair prob invented", cn.fair_prob is None)
    check("flagged invalid", "MARKET_MAPPING_INVALID" in cn.quality_flags)
    check("empty input handled", build_consensus([]).fair_prob is None)

    print("\n== edge vs EV use different inputs ==")
    check("edge measured against CONSENSUS",
          model_edge(0.60, c) == round(0.60 - c.fair_prob, 6))
    ev = ev_on_executable(0.60, c, side="OVER")
    check("EV computed on the EXECUTABLE price",
          ev == round(0.60 * 2.10 - 1.0, 6), str(ev))
    check("EV on consensus odds would differ", ev != round(0.60 * 1.95 - 1.0, 6))
    check("no model prob -> no edge", model_edge(None, c) is None)
    check("no executable price -> no EV", ev_on_executable(0.6, cn) is None)
    check("transaction cost reduces EV",
          ev_on_executable(0.60, c, tx_cost=0.02) < ev)

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
