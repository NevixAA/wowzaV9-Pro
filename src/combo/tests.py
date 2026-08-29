"""
Deterministic tests for the combo research layer (bet-builder brief, section 38).
=================================================================================
    python -m src.combo.tests

No network, no credentials, no reliance on the canonical store. Every check encodes either a
mathematical law the joint layer must obey or a defect that actually occurred while building it.
"""
from __future__ import annotations

import itertools
import sys

import numpy as np
import pandas as pd

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def _frame(scores):
    return pd.DataFrame([{"home_goals": h, "away_goals": a, "league": "L",
                          "season": "2026", "match_date": "2026-01-01"} for h, a in scores])


def main() -> int:
    from src.combo import events as ev
    from src.combo import dependency as dep

    print("== settlement from the scoreline ==")
    d = ev.settle(_frame([(2, 1)]))
    r = d.iloc[0]
    # One scoreline settles every market at once, coherently. 2-1 is the worked example in
    # section 59 of the brief.
    for mkt, want in (("HOME", True), ("DRAW", False), ("AWAY", False), ("O15", True),
                      ("O25", True), ("O35", False), ("BTTS", True), ("BTTS_NO", False),
                      ("1X", True), ("X2", False), ("12", True)):
        check(f"2-1 settles {mkt} = {want}", bool(r[f"ev_{mkt}"]) is want, str(r[f"ev_{mkt}"]))
    d = ev.settle(_frame([(0, 0)]))
    r = d.iloc[0]
    check("0-0 is DRAW, under everything, BTTS No",
          bool(r.ev_DRAW) and not bool(r.ev_O15) and bool(r.ev_BTTS_NO))

    print("\n== a missing scoreline is DROPPED, never settled as a loss ==")
    d = ev.settle(pd.DataFrame({"home_goals": [1, None], "away_goals": [1, 2]}))
    check("row with a null score is removed", len(d) == 1, str(len(d)))
    check("...and counted, not silently lost", d.attrs["dropped_no_scoreline"] == 1)

    print("\n== logical nesting: O1.5 >= O2.5 >= O3.5 ==")
    d = ev.settle(_frame([(h, a) for h in range(6) for a in range(6)]))
    p15, p25, p35 = d.ev_O15.mean(), d.ev_O25.mean(), d.ev_O35.mean()
    check("O1.5 >= O2.5 >= O3.5 holds", p15 >= p25 >= p35, f"{p15:.3f} {p25:.3f} {p35:.3f}")
    check("no coherence violations on a full grid", ev.check_coherence(d) == [],
          str(ev.check_coherence(d)))

    print("\n== redundant / impossible pairs are refused ==")
    # Each of these was MISSED by the first hand-written version and reported as a finding.
    for a, b, want in (("O25", "O15", "NESTED"), ("O35", "O25", "NESTED"),
                       ("U15", "BTTS_NO", "NESTED"), ("BTTS", "O15", "NESTED"),
                       ("HOME", "X2", "MUTUALLY_EXCLUSIVE"),
                       ("DRAW", "12", "MUTUALLY_EXCLUSIVE"),
                       ("AWAY", "1X", "MUTUALLY_EXCLUSIVE"),
                       ("U15", "O25", "MUTUALLY_EXCLUSIVE"),
                       ("U25", "O35", "MUTUALLY_EXCLUSIVE"),
                       ("HOME", "DRAW", "MUTUALLY_EXCLUSIVE"),
                       ("O25", "U25", "MUTUALLY_EXCLUSIVE")):
        got = ev.is_redundant(a, b) or ""
        check(f"{a}+{b} refused ({want})", want in got, got or "ALLOWED")
    check("identical legs refused", ev.is_redundant("O25", "O25") == "IDENTICAL_LEGS")
    for a, b in (("O25", "BTTS"), ("O35", "BTTS"), ("O25", "HOME"), ("DRAW", "U25")):
        check(f"{a}+{b} IS a legitimate pair", ev.is_redundant(a, b) is None,
              str(ev.is_redundant(a, b)))

    print("\n== mutual exclusion and nesting are decided by the OUTCOME SPACE ==")
    # The property that makes it robust: it is set containment, so a market added later is
    # classified correctly without editing a list.
    check("U15 support is a subset of BTTS_NO support",
          ev._SUPPORT["U15"] <= ev._SUPPORT["BTTS_NO"])
    check("HOME and X2 supports are disjoint",
          not (ev._SUPPORT["HOME"] & ev._SUPPORT["X2"]))
    check("O25 and BTTS supports genuinely overlap without nesting",
          bool(ev._SUPPORT["O25"] & ev._SUPPORT["BTTS"])
          and not ev._SUPPORT["O25"] <= ev._SUPPORT["BTTS"]
          and not ev._SUPPORT["BTTS"] <= ev._SUPPORT["O25"])

    print("\n== Frechet bounds (brief section 39) ==")
    lo, hi = ev.frechet_bounds(0.6, 0.7)
    check("bounds for (0.6,0.7) are [0.30, 0.60]", abs(lo - 0.3) < 1e-9 and abs(hi - 0.6) < 1e-9,
          f"{lo} {hi}")
    lo, hi = ev.frechet_bounds(0.2, 0.3)
    check("disjoint-capable marginals give a 0 lower bound", abs(lo) < 1e-9)
    check("joint can never exceed min(P(A),P(B))", hi == 0.2)

    print("\n== joint probability laws on real-shaped data ==")
    # 8x8 = 64 fixtures, comfortably above dependency.MIN_CELL_N (30). The first version used a
    # 5x5 grid = 25 rows, which is BELOW that floor, so pair_rows returned an empty list and the
    # three `all(...)` checks below passed vacuously on all([]) before the next line raised
    # StopIteration. An empty-input assertion now makes that impossible to repeat.
    d = ev.settle(_frame([(h, a) for h in range(8) for a in range(8)]))
    rows = dep.pair_rows(d, segment="T")
    check("the grid actually produced pairs (guards against vacuous passes)",
          len(rows) > 20, f"only {len(rows)} rows — checks below would be meaningless")
    check("every pair obeys Frechet", bool(rows) and all(r["frechet_ok"] for r in rows))
    check("joint <= min(component probabilities)",
          bool(rows) and all(r["p_joint"] <= min(r["p_a"], r["p_b"]) + 1e-9 for r in rows))
    check("no redundant pair reached the matrix",
          bool(rows) and all(ev.is_redundant(r["market_a"], r["market_b"]) is None
                             for r in rows))

    print("\n== independence multiplication is NOT used for same-match joints ==")
    # A perfectly dependent pair must report a ratio far from 1, proving the joint is measured
    # rather than assumed. O25 and BTTS on the real grid are strongly positively dependent.
    _m = [x for x in rows if {x["market_a"], x["market_b"]} == {"O25", "BTTS"}]
    check("the O25+BTTS pair is present to test", len(_m) == 1, f"found {len(_m)}")
    r = _m[0] if _m else {"p_joint": 0, "independent_joint": 0, "dependency_ratio": 1.0}
    check("O25+BTTS joint differs from the product of marginals",
          abs(r["p_joint"] - r["independent_joint"]) > 1e-6,
          f"joint={r['p_joint']} product={r['independent_joint']}")
    check("...and the dependency ratio records the size of the error",
          r["dependency_ratio"] is not None and abs(r["dependency_ratio"] - 1.0) > 0.05,
          str(r["dependency_ratio"]))

    print("\n== phi is a correlation: bounded, signed, and exact on degenerate cases ==")
    check("all |phi| <= 1", all(abs(r["phi"]) <= 1 + 1e-9 for r in rows))
    a = np.array([True, True, False, False]); b = np.array([True, True, False, False])
    check("identical vectors give phi = +1", abs(dep._phi(a, b) - 1.0) < 1e-9)
    check("opposite vectors give phi = -1", abs(dep._phi(a, ~b) + 1.0) < 1e-9)

    print("\n== sample-status labels ==")
    for n, want in ((50, "INSUFFICIENT"), (300, "EARLY"), (900, "RESEARCH"),
                    (5000, "VALIDATION_CANDIDATE")):
        check(f"n={n} -> {want}", dep.sample_status(n) == want, dep.sample_status(n))

    print("\n== half-time markets are declared unavailable, not silently missing ==")
    check("HT markets named with a reason",
          set(ev.HT_EVENTS) == {"HT_O05", "HT_O15"} and all(ev.HT_EVENTS.values()))
    check("...and are NOT in the settleable event set",
          "HT_O05" not in ev.EVENTS and "HT_O15" not in ev.EVENTS)

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
