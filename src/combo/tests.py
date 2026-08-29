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

    print("")
    print("== notification dedup (sections 83-85) ==")
    from src.combo import notify as nt
    # A VALID SHAPE, not just valid numbers. This fixture used to be two bare probabilities with
    # no legs at all, which meant every dedup test passed against a combo that could never be
    # sent — the suite was checking the anti-spam logic on something the quality gates reject.
    # One scoreline leg plus one player leg is the minimum real builder: goal-family legs all come
    # off the same score matrix, so at most one may appear.
    base = pd.Series({"combo_id": "abc", "joint_probability": 0.20,
                      "independence_probability": 0.10, "fair_combo_odds": 5.0,
                      "n_legs": 2,
                      "leg1_market": "O25", "leg1_label": "Over 2.5", "leg1_p": 0.52,
                      "leg2_market": "player_goals", "leg2_label": "X to score", "leg2_p": 0.40})
    ok, why = nt.should_notify(base, {}, 0.0)
    check("a new qualifying combo notifies", ok and why == "NEW", why)
    st = {"abc": {"first_seen_ts": 0.0, "last_notified_ts": 0.0,
                  "joint_probability": 0.20, "odds": 5.0}}
    check("the SAME combo immediately after is suppressed",
          nt.should_notify(base, st, 0.0) == (False, "UNCHANGED"))
    # The epoch-zero bug: `if last` is False when last_notified_ts == 0, silently disabling
    # reminders. Real timestamps are large so production would have worked and nobody would
    # ever have found it. Guarded with `is not None` now.
    ok, why = nt.should_notify(base, st, nt.RENOTIFY_AFTER_HOURS * 3600 + 1)
    check("a reminder fires after the window even from timestamp 0", ok and why == "REMINDER", why)
    up = base.copy(); up["joint_probability"] = 0.20 + nt.MIN_PROB_CHANGE_PP / 100 + 0.001
    check("a meaningful probability rise re-notifies", nt.should_notify(up, st, 0.0)[0])
    tiny = base.copy(); tiny["joint_probability"] = 0.205
    check("a sub-threshold drift does NOT re-notify",
          nt.should_notify(tiny, st, 0.0) == (False, "UNCHANGED"))

    print("")
    print("== notification quality gates ==")
    short = base.copy(); short["fair_combo_odds"] = 1.5
    check("odds under the floor are refused",
          nt.should_notify(short, {}, 0.0) == (False, "ODDS_TOO_SHORT"))
    likely = base.copy(); likely["joint_probability"] = 0.64
    likely["independence_probability"] = 0.60; likely["fair_combo_odds"] = 1.56
    check("a near-certainty at short odds is refused", not nt.should_notify(likely, {}, 0.0)[0])
    indep = base.copy(); indep["independence_probability"] = 0.199
    check("a combo with no independence edge is refused",
          nt.should_notify(indep, {}, 0.0) == (False, "NO_INDEPENDENCE_EDGE"))
    check("independence_edge is +100% when the joint is double the product",
          abs(nt.independence_edge(pd.Series({"joint_probability": 0.2,
                                              "independence_probability": 0.1})) - 1.0) < 1e-9)
    check("independence_edge is None for a cross-match multiple",
          nt.independence_edge(pd.Series({"conservative_joint_probability": 0.2})) is None)

    print("")
    print("== the message is honest and leaks nothing ==")
    msg = nt.format_combo(pd.Series({
        "match": "A vs B", "league": "L", "match_date": "2026-01-01",
        "leg1_label": "Over 2.5", "leg1_model_p": 0.5,
        "leg2_label": "BTTS Yes", "leg2_model_p": 0.5,
        "joint_probability": 0.41, "independence_probability": 0.25,
        "dependency_ratio": 1.64, "fair_combo_odds": 2.44,
        "independence_fair_odds": 4.0}))
    import os as _os
    leaked = [k for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "APIFOOTBALL_KEY",
                          "ODDS_API_KEY") if (_os.getenv(k) or "__NEVER_MATCHES__") in msg]
    check("no environment secret appears in the message body", not leaked, str(leaked))
    check("the message says it is not executable", "not an executable one" in msg)
    check("the message says PAPER", "PAPER" in msg)

    # == both builders' vocabularies, not just same_match's ==
    #
    # Everything above this point was written against `builder.same_match`, which names its
    # columns fair_combo_odds / leg1_model_p. `match_picture.build` -- the N-leg builder that
    # produces every candidate the pipeline actually generates -- names them fair_odds / leg1_p.
    # The whole suite passed while notify silently rejected 6,318 of 6,360 real candidates as
    # ODDS_TOO_SHORT and rendered every leg as `0%`. A test suite that only ever feeds one
    # producer's column names cannot catch a disagreement between two producers.
    mp_row = pd.Series({
        # O25 + BTTS + a player leg would now be refused, and rightly: two goal-family legs are
        # one score matrix quoted twice. Swapped the BTTS leg for a team-card line.
        "combo_id": "fx1|O25+teamcard+player_goals",
        "match": "A vs B", "league": "L", "match_date": "2026-01-01", "n_legs": 3,
        "leg1_market": "O25", "leg1_label": "Over 2.5", "leg1_p": 0.52,
        "leg2_market": "teamcard_cards_o1.5", "leg2_label": "A over 1.5 cards", "leg2_p": 0.55,
        "leg3_market": "player_goals", "leg3_label": "X to score", "leg3_p": 0.40,
        "joint_probability": 0.22, "independence_probability": 0.114,
        "dependency_ratio": 1.93, "fair_odds": 4.55, "independence_fair_odds": 8.75})
    send, why = nt.should_notify(mp_row, {}, 0.0)
    check("match_picture's fair_odds is accepted by the notify gate", send, why)
    m2 = nt.format_combo(mp_row)
    check("match_picture leg probabilities are not rendered as 0%", "`0%`" not in m2, m2)
    check("a THREE-leg combo prints all three legs", "3️⃣" in m2, m2)
    check("fair odds render as a number, not None", "Fair odds: *4.55*" in m2, m2)
    # A leg count is data, not a constant: the two-leg row above must still print exactly two.
    check("a two-leg combo does not invent a third leg", "3️⃣" not in msg, msg)
    # _first_num must fall through a null first name rather than returning NaN, which is the
    # precise failure that made a name mismatch look like a strict filter doing its job.
    check("a null preferred column falls through to the next name",
          nt._first_num(pd.Series({"fair_combo_odds": float("nan"), "fair_odds": 3.2}),
                        "fair_combo_odds", "fair_odds") == 3.2)
    check("a genuinely absent value returns None, not 0",
          nt._first_num(pd.Series({"other": 1.0}), "fair_combo_odds", "fair_odds") is None)

    # == a builder must be more than one opinion said twice ==
    #
    # The first live tips were "Over 3.5 + Away over 1.5" and "BTTS + Away over 1.5" — every leg
    # read off the SAME fitted score matrix, so the big correlation adjustment was the symptom,
    # not the edge. These lock the shape rules in.
    two_goal = base.copy()
    two_goal["leg2_market"] = "BTTS"; two_goal["leg2_label"] = "Both teams to score"
    check("two goal-family legs are refused",
          nt.should_notify(two_goal, {}, 0.0) == (False, "MULTIPLE_GOAL_LEGS_SAME_OPINION"))
    three_goal = base.copy()
    three_goal["leg2_market"] = "BTTS"
    three_goal["leg3_market"] = "AWAY_O15"; three_goal["leg3_label"] = "Away over 1.5"
    three_goal["leg3_p"] = 0.33; three_goal["n_legs"] = 3
    check("...and so are three", not nt.should_notify(three_goal, {}, 0.0)[0])
    filler = base.copy(); filler["leg2_p"] = 0.86
    check("a near-certain filler leg is refused",
          nt.should_notify(filler, {}, 0.0) == (False, "LEG_TOO_CERTAIN_TO_ADD_ANYTHING"))
    # The floor must fall with leg count or no 4-leg builder can ever be sent: four likely legs
    # multiply well under a flat 15%, which is what silenced props entirely.
    check("the joint-probability floor falls as legs are added",
          nt.MIN_JOINT_PROB_BY_LEGS[4] < nt.MIN_JOINT_PROB_BY_LEGS[3]
          < nt.MIN_JOINT_PROB_BY_LEGS[2])
    # `match` must be present: format_combo switches on it to decide same-match vs cross-match,
    # and without it a same-match builder renders down the multiples branch and prints no legs.
    four = pd.Series({"combo_id": "f4", "match": "A vs B", "league": "L",
                      "match_date": "2026-01-01", "n_legs": 4, "joint_probability": 0.09,
                      "independence_probability": 0.03, "fair_odds": 11.1,
                      "leg1_market": "O35", "leg1_label": "Over 3.5", "leg1_p": 0.28,
                      "leg2_market": "player_sot2", "leg2_label": "A 2+ SOT", "leg2_p": 0.59,
                      "leg3_market": "player_sot", "leg3_label": "B 1+ SOT", "leg3_p": 0.48,
                      "leg4_market": "player_goals", "leg4_label": "C to score", "leg4_p": 0.40})
    ok4, why4 = nt.should_notify(four, {}, 0.0)
    check("a 4-leg builder at 9% joint IS sendable", ok4, why4)
    check("...and its message lists all four legs", "4️⃣" in nt.format_combo(four))

    # == one tip per match ==
    #
    # MAX_PER_RUN capped the total but nothing capped the spread, and ranking by correlation edge
    # concentrates on whichever fixture has the most legs available — so one Bundesliga 2 match
    # with four priced players took all six slots and the board went out as six variations of the
    # same game.
    import pathlib as _pl, tempfile as _tf
    _real_send, _real_state = nt.send, nt.STATE_FILE
    _sent: list[str] = []
    nt.send = lambda text, **k: (_sent.append(text) or (True, "sent"))
    nt.STATE_FILE = _pl.Path(_tf.mkdtemp()) / "s.json"
    try:
        many = pd.concat([
            four.to_frame().T.assign(combo_id=f"same{i}", fixture_key="FX1",
                                     leg2_p=0.59 - i * 0.01)
            for i in range(10)], ignore_index=True)
        res = nt.run(many, dry_run=False)
        check("ten combos on ONE fixture send exactly one tip", res["sent"] == 1, str(res["sent"]))
        check("...and the rest are attributed to the per-match cap",
              res["reasons"].get("ANOTHER_TIP_ALREADY_SENT_FOR_THIS_MATCH", 0) == 9,
              str(res["reasons"]))
    finally:
        nt.send, nt.STATE_FILE = _real_send, _real_state

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
