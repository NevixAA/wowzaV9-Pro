"""
Phase 4. Covers the Prompt 1 required tests: promotion fails without required validation,
a blind fixture cannot generate LIVE, a BLOCKED league cannot generate LIVE, and model SHA
matches the registry.

    python -m tests.test_registry_gates
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.betting.gates import Decision, GateInputs, decide  # noqa: E402
from src.models.registry import (GATE, ModelRecord, Registry,  # noqa: E402
                                 evaluate_gate, hash_manifest)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def good_record(mid="m1", **kw) -> ModelRecord:
    """A record that clears every gate, so tests can knock out one thing at a time."""
    base = dict(
        model_id=mid, market="OU25", scope="new_format", model_sha="abc123",
        git_sha="deadbeef", validation_type="chronological_4block", odds_policy="REAL_ONLY",
        holdout_rows=2000, sample_label="VALIDATED", real_odds_coverage=0.95,
        logloss_improvement=0.004, brier_improvement=0.001, ece=0.02,
        clv_n=400, mean_clv_pct=0.6, auc=0.60,
    )
    base.update(kw)
    return ModelRecord(**base)


def main() -> int:
    print("\n== a fully-evidenced challenger passes ==")
    res = evaluate_gate(good_record())
    check("passes with complete evidence", res.passed, res.explain())

    print("\n== promotion FAILS without each piece of required validation ==")
    for label, kw, expect in [
        ("no market-relative logloss gain", {"logloss_improvement": -0.001},
         "market_relative_logloss"),
        ("no brier gain", {"brier_improvement": 0.0}, "market_relative_brier"),
        ("holdout too small", {"holdout_rows": 100}, "holdout_rows"),
        ("sample not VALIDATED", {"sample_label": "EARLY_SIGNAL"}, "sample_validated"),
        ("poor calibration", {"ece": 0.20}, "calibration"),
        ("synthetic odds", {"odds_policy": "ALLOW_SYNTHETIC"}, "odds_policy_real"),
        ("thin real-odds coverage", {"real_odds_coverage": 0.10}, "real_odds_coverage"),
        ("CLV sample too small", {"clv_n": 5}, "clv_sample"),
        ("negative CLV", {"mean_clv_pct": -0.4}, "clv_positive"),
    ]:
        r = evaluate_gate(good_record(**kw))
        check(f"{label} blocks promotion",
              (not r.passed) and r.checks.get(expect) is False, r.explain()[:90])

    print("\n== missing evidence blocks, it does not pass by default ==")
    empty = ModelRecord(model_id="empty", market="OU25", scope="standard")
    r = evaluate_gate(empty)
    check("a record with no evidence cannot be promoted", not r.passed)
    check("every missing piece is named", len(r.reasons) >= 6, str(len(r.reasons)))

    print("\n== AUC alone can never promote ==")
    auc_only = good_record("auc_only", auc=0.99, logloss_improvement=-0.01,
                           brier_improvement=-0.01)
    r = evaluate_gate(auc_only)
    check("a huge AUC with worse market-relative loss is refused", not r.passed)
    check("AUC is recorded but not a criterion", r.checks.get("auc_recorded") is True)

    print("\n== champion / challenger ==")
    with tempfile.TemporaryDirectory() as td:
        reg = Registry(Path(td) / "registry.json")
        champ = reg.add(good_record("champ", logloss_improvement=0.005))
        res = reg.promote("champ", beat_champion=False)
        check("first model can be promoted", res.passed and champ.status == "LIVE", res.explain())
        check("promotion is timestamped", bool(champ.promoted_at))

        weak = reg.add(good_record("weak", logloss_improvement=0.001))
        res = reg.promote("weak")
        check("a challenger that is worse than the champion is refused",
              not res.passed and weak.status != "LIVE", res.explain()[:80])
        check("the incumbent stays LIVE", reg.champion("new_format", "OU25").model_id == "champ")

        strong = reg.add(good_record("strong", logloss_improvement=0.020))
        res = reg.promote("strong")
        check("a genuinely better challenger is promoted", res.passed and strong.status == "LIVE")
        check("the old champion is RETIRED", champ.status == "RETIRED")
        check("retirement is timestamped", bool(champ.retired_at))
        check("the new champion records what it replaced", strong.replaces == "champ")
        check("version incremented", strong.version == champ.version + 1)
        check("champion() returns the new one",
              reg.champion("new_format", "OU25").model_id == "strong")

        print("\n== retraining does NOT auto-replace ==")
        retrain = reg.add(good_record("retrain_sunday", logloss_improvement=0.019))
        res = reg.promote("retrain_sunday")
        check("a fresh retrain that is not better stays a challenger",
              not res.passed and retrain.status in ("RESEARCH", "PAPER", "SHADOW"),
              res.explain()[:80])
        check("it is listed as a challenger",
              "retrain_sunday" in [c.model_id for c in reg.challengers("new_format", "OU25")])

        print("\n== registry round-trips with provenance intact ==")
        reg.save()
        reg2 = Registry(reg.path)
        s2 = reg2.records["strong"]
        check("model_sha survives", s2.model_sha == "abc123")
        check("git_sha survives", s2.git_sha == "deadbeef")
        check("status survives", s2.status == "LIVE")
        check("validation_type survives", s2.validation_type == "chronological_4block")
        check("a retired record is kept, not deleted", reg2.records["champ"].status == "RETIRED")

        print("\n== blocking ==")
        reg2.block("strong", "feature drift")
        check("blocked model is BLOCKED", reg2.records["strong"].status == "BLOCKED")
        check("reason recorded", "feature drift" in reg2.records["strong"].notes)
        check("a BLOCKED model can no longer be champion",
              reg2.champion("new_format", "OU25") is None)

    print("\n== manifest hashing detects silent change ==")
    a = hash_manifest({"features": ["x", "y"], "threshold": 0.14})
    check("hash is stable", a == hash_manifest({"threshold": 0.14, "features": ["x", "y"]}),
          "key order must not matter")
    check("a changed threshold changes the hash",
          a != hash_manifest({"features": ["x", "y"], "threshold": 0.15}))

    print("\n== deployment gate: tier and permission are separate ==")
    live = GateInputs(signal_tier="SNIPER", model_status="LIVE", league_approved=True,
                      market_approved=True, odds_source="REAL", odds_two_sided=True,
                      book_count=4, price_age_minutes=5, minutes_to_kickoff=180,
                      model_validated=True, clv_n=400)
    d = decide(live, pro_may_stake=True)
    check("a fully-cleared SNIPER goes LIVE at full stake",
          d.mode == "LIVE" and d.stake_multiplier == 1.0, str(d))
    d = decide(GateInputs(**{**live.__dict__, "signal_tier": "MARKSMAN"}), pro_may_stake=True)
    check("MARKSMAN stakes three quarters", d.stake_multiplier == 0.75, str(d.stake_multiplier))

    print("\n== SNIPER + PAPER is valid, and the tier is never rewritten ==")
    d = decide(live)                       # pro_may_stake defaults False
    check("Pro does not stake this season", d.mode == "PAPER", d.mode)
    check("the tier is UNCHANGED", d.signal_tier == "SNIPER", d.signal_tier)
    check("no stake", d.stake_multiplier == 0.0)
    check("the reason is recorded, not silent", any("does not stake" in b for b in d.blockers),
          str(d.blockers))

    print("\n== a blind fixture cannot generate LIVE ==")
    d = decide(GateInputs(**{**live.__dict__, "entity_resolved": False}), pro_may_stake=True)
    check("unresolved entity is BLOCKED", d.mode == "BLOCKED", d.mode)
    d = decide(GateInputs(**{**live.__dict__,
                             "quality_flags": ("ENTITY_UNRESOLVED",)}), pro_may_stake=True)
    check("ENTITY_UNRESOLVED flag is BLOCKED", d.mode == "BLOCKED")
    d = decide(GateInputs(**{**live.__dict__, "feature_health_ok": False}), pro_may_stake=True)
    check("degraded features are BLOCKED", d.mode == "BLOCKED", d.mode)

    print("\n== a BLOCKED league/market cannot generate LIVE ==")
    for label, kw in [("league not approved", {"league_approved": False}),
                      ("market not approved", {"market_approved": False}),
                      ("model not validated", {"model_validated": False}),
                      ("model not LIVE", {"model_status": "RESEARCH"}),
                      ("synthetic odds", {"odds_source": "SYNTHETIC"}),
                      ("one-sided market", {"odds_two_sided": False}),
                      ("single book", {"book_count": 1}),
                      ("stale price", {"price_age_minutes": 120}),
                      ("thin CLV", {"clv_n": 3})]:
        d = decide(GateInputs(**{**live.__dict__, **kw}), pro_may_stake=True)
        check(f"{label} -> not LIVE", d.mode != "LIVE" and d.stake_multiplier == 0.0, d.mode)

    print("\n== post-kickoff is refused outright ==")
    d = decide(GateInputs(**{**live.__dict__, "minutes_to_kickoff": -4}), pro_may_stake=True)
    check("kickoff passed is BLOCKED", d.mode == "BLOCKED", d.mode)

    print("\n== non-signal tiers are recorded, not staked ==")
    for t in ("AVOID", "NO_BET", "OBSERVE"):
        d = decide(GateInputs(signal_tier=t), pro_may_stake=True)
        check(f"{t} -> RESEARCH, no stake",
              d.mode == "RESEARCH" and d.stake_multiplier == 0.0, d.mode)

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
