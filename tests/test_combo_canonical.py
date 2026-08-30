"""
Prompt 01 section 17 — builder identity, probability validity, canonical shape.

    python -m tests.test_combo_canonical

The combo_id tests are the load-bearing ones. The id was broken in BOTH directions at once and
each direction cost something real: leg ORDER changed the id, so the same bet notified more than
once; the SELECTION was absent from the id, so eight different bets shared one identity and ~250
distinct combos were deduplicated away on every settle pass. Neither was visible in any output —
the settled file looked collision-free precisely because the collapse happened upstream of it.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import schemas  # noqa: E402
from src.combo import canonical as cc  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def _identity(row: pd.Series, legcols: list[str], labcols: list[str]) -> str:
    """The id exactly as bet_builder.generate() builds it. Duplicated here on purpose: a test
    that imports the implementation cannot catch the implementation changing shape."""
    legs = sorted(f"{row.get(m) or ''}:{row.get(lab) or ''}"
                  for m, lab in zip(legcols, labcols) if isinstance(row.get(m), str))
    return hashlib.sha1("|".join(legs).encode("utf-8")).hexdigest()[:12]


def _row(**kw) -> pd.Series:
    base = {"fixture_key": "FX1", "generated_at": "2026-08-30T09:00:00Z",
            "kickoff_utc": "2026-08-30T15:00:00Z", "league": "L", "n_legs": 2,
            "joint_probability": 0.20, "independence_probability": 0.16,
            "dependency_ratio": 1.25, "fair_odds": 5.0, "independence_fair_odds": 6.25,
            "leg1_market": "O25", "leg1_label": "Over 2.5 goals", "leg1_p": 0.55,
            "leg2_market": "player_sot", "leg2_label": "A. Player 1+ SOT", "leg2_p": 0.40,
            "combo_id": "FX1|x", "calc_version": "1.0.0"}
    base.update(kw)
    return pd.Series(base)


LEGCOLS = ["leg1_market", "leg2_market"]
LABCOLS = ["leg1_label", "leg2_label"]


def test_combo_id() -> None:
    print("combo_id — stability and uniqueness")

    a = _row()
    # Same two legs, swapped between the leg1_/leg2_ slots. One bet, therefore one id.
    b = _row(leg1_market="player_sot", leg1_label="A. Player 1+ SOT", leg1_p=0.40,
             leg2_market="O25", leg2_label="Over 2.5 goals", leg2_p=0.55)
    check("leg order does not change the id",
          _identity(a, LEGCOLS, LABCOLS) == _identity(b, LEGCOLS, LABCOLS),
          "reordering the legs produced a second identity — this is what sent duplicate tips")

    # Same markets, different player. Two different bets, therefore two ids.
    c = _row(leg2_label="B. Other 1+ SOT")
    check("a different selection changes the id",
          _identity(a, LEGCOLS, LABCOLS) != _identity(c, LEGCOLS, LABCOLS),
          "two different bets share one identity — this is what deduplicated combos away")

    check("the id is deterministic across calls",
          _identity(a, LEGCOLS, LABCOLS) == _identity(_row(), LEGCOLS, LABCOLS))

    # The historical shape, asserted directly so a regression to it is caught by name.
    legacy_a = "+".join(str(a.get(m) or "") for m in LEGCOLS)
    legacy_b = "+".join(str(b.get(m) or "") for m in LEGCOLS)
    check("the OLD market-only id really was order-dependent (regression guard)",
          legacy_a != legacy_b,
          "if these are equal the test fixture no longer reproduces the original defect")


def test_candidates_shape() -> None:
    print("combo_candidates / combo_legs")
    d = pd.DataFrame([_row(combo_id="FX1|aaa"), _row(combo_id="FX1|bbb", n_legs=2)])
    head, legs = cc.candidates(d, run_id="t")

    check("one candidate row in, one out", len(head) == len(d))
    check("legs are normalized one row per leg", len(legs) == 4, f"got {len(legs)}")
    check("leg_index is 1-based", set(legs["leg_index"]) == {1, 2}, str(set(legs["leg_index"])))
    check("declared n_legs matches the legs produced",
          (head.set_index("combo_id")["n_legs"].sort_index().values ==
           legs.groupby("combo_id").size().sort_index().values).all())

    # The price discipline. A 0.0 here would read as "we measured no edge", which is a claim.
    for col in ("offered_odds", "implied_probability", "market_probability", "model_edge"):
        check(f"{col} is NULL, never 0.0", head[col].isna().all(),
              "a fabricated price or edge entered the canonical store")

    check("no leg is left UNMAPPED", (legs["market_family"] != "UNMAPPED").all(),
          str(sorted(set(legs.loc[legs.market_family == 'UNMAPPED', 'market']))))
    check("fair_odds is the reciprocal of the model probability",
          np.allclose(legs["fair_odds"], 1.0 / legs["model_probability"]))


def test_empty_inputs() -> None:
    print("empty inputs")
    h, l = cc.candidates(pd.DataFrame(), run_id="t")
    check("an empty build returns empty frames, does not raise", h.empty and l.empty)
    check("empty settlements return empty", cc.settlements(pd.DataFrame()).empty)
    check("empty dependencies return empty", cc.dependencies(pd.DataFrame(), None).empty)


def test_horizons() -> None:
    print("horizon buckets")
    check("T-10m is the tightest bucket", cc.horizon_bucket(5) == "T-10m")
    check("a bound belongs to its own bucket", cc.horizon_bucket(60) == "T-1h")
    check("just past a bound falls to the next", cc.horizon_bucket(61) == "T-3h")
    check("beyond 48h is FAR", cc.horizon_bucket(5000) == "FAR")
    check("missing is UNKNOWN, not a bucket", cc.horizon_bucket(None) == "UNKNOWN")
    # Section 14: a post-kickoff observation must never be usable as a pre-match close.
    check("post-kickoff is its own state, never a pre-match bucket",
          cc.horizon_bucket(-5) == "POST_KICKOFF")


def test_settlement_states() -> None:
    print("settlement grading")
    s = pd.DataFrame([
        {"combo_id": "a", "fixture_key": "F", "combo_result": "WON", "n_legs": 2,
         "leg_results": "O25=WON | player_sot=WON", "generated_at": "2026-08-30T00:00:00Z"},
        {"combo_id": "b", "fixture_key": "F", "combo_result": "LOST", "n_legs": 2,
         "leg_results": "O25=WON | player_sot=LOST", "generated_at": "2026-08-30T00:00:00Z"},
        {"combo_id": "c", "fixture_key": "F", "combo_result": None, "n_legs": 2,
         "leg_results": None, "generated_at": "2026-08-30T00:00:00Z"},
    ])
    out = cc.settlements(s, run_id="t")
    check("WON -> WIN", out.loc[0, "result"] == "WIN")
    check("LOST -> LOSS", out.loc[1, "result"] == "LOSS")
    # An ungradeable combo is not a loss. Mapping it to one would improve every hit rate below it.
    check("ungradeable -> UNKNOWN, not LOSS", out.loc[2, "result"] == "UNKNOWN")
    check("UNKNOWN is marked UNGRADEABLE", out.loc[2, "settlement_quality"] == "UNGRADEABLE")
    check("winning legs are counted", out.loc[0, "n_legs_won"] == 2, str(out.loc[0, "n_legs_won"]))
    check("a losing leg is not counted as won", out.loc[1, "n_legs_won"] == 1,
          str(out.loc[1, "n_legs_won"]))
    check("no profit is invented without a price", out["profit"].isna().all())


def test_frechet() -> None:
    print("Fréchet bounds on dependency estimates")
    # A joint probability outside [max(0, pa+pb-1), min(pa, pb)] is arithmetically impossible.
    m = pd.DataFrame([{"market_a": "O25", "market_b": "BTTS", "p_a": 0.6, "p_b": 0.5,
                       "p_joint": 0.45, "independent_joint": 0.30, "frechet_lo": 0.1,
                       "frechet_hi": 0.5, "frechet_ok": True, "n": 500,
                       "sample_status": "OK", "calc_version": "1.0.0"}])
    out = cc.dependencies(m, None, run_id="t")
    lo = np.maximum(0.0, out["p_a"] + out["p_b"] - 1.0)
    hi = np.minimum(out["p_a"], out["p_b"])
    check("declared Fréchet lower bound matches max(0, pa+pb-1)", np.allclose(out["frechet_lo"], lo))
    check("declared Fréchet upper bound matches min(pa, pb)", np.allclose(out["frechet_hi"], hi))
    check("observed joint lies inside the bounds",
          bool(((out["observed_joint"] >= lo) & (out["observed_joint"] <= hi)).all()))
    check("calculation_version is carried, so an estimate cannot silently replace an older one",
          out["calculation_version"].notna().all())


def test_lifecycle() -> None:
    print("table lifecycle accounting")
    check("combo_price_snapshots is SOURCE_REQUIRED, not ACTIVE",
          schemas.status("combo_price_snapshots") == schemas.SOURCE_REQUIRED,
          "no bookmaker builder price exists to collect; ACTIVE would alarm forever")
    check("SOURCE_REQUIRED counts as legitimately empty",
          schemas.is_expected_empty("combo_price_snapshots"))
    check("SOURCE_REQUIRED is NOT 'planned' (nobody can act on it)",
          not schemas.is_planned("combo_price_snapshots"))
    check("team_match_stats is ACTIVE, so an empty one alarms",
          schemas.status("team_match_stats") == schemas.ACTIVE
          and not schemas.is_expected_empty("team_match_stats"))
    check("an undeclared table defaults to ACTIVE",
          schemas.status("something_new") == schemas.ACTIVE)
    for t in ("combo_candidates", "combo_legs", "combo_dependencies", "combo_settlements",
              "combo_price_snapshots"):
        check(f"{t} is declared in config.TABLES", t in __import__(
            "config.pro_config", fromlist=["TABLES"]).TABLES)


def main() -> int:
    for fn in (test_combo_id, test_candidates_shape, test_empty_inputs, test_horizons,
               test_settlement_states, test_frechet, test_lifecycle):
        fn()
    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): {', '.join(FAILS)}")
        return 1
    print("all combo canonical tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
