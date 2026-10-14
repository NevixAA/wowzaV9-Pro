"""Existing-league regression harness - the rule is pinned so it cannot drift after results."""
from src.scout import regression_harness as RH


def test_rule_constants():
    assert RH.REGISTERED_ON == "2026-10-14"
    assert RH.TARGETS == ("over25", "btts")
    assert RH.CUT_QUANTILE == 0.80
    assert RH.MIN_CANDIDATE_ROWS == 300
    assert RH.POOLED_MARGIN == 0.002
    assert RH.LEAGUE_MIN_N == 150


def test_goals_only_families():
    # a new-format candidate has goals only - no shots, corners or cards may enter the comparison
    assert set(RH.FAMILIES) == {"BASE", "FORM", "STRENGTH", "REST", "H2H"}


def test_promotion_wires_harness_and_fails_closed():
    import inspect
    from src.scout import promotion
    src = inspect.getsource(promotion.validate)
    assert "RH.run(lid)" in src and "REGRESSION_HARNESS_ERROR" in src
    assert "PENDING_REGRESSION_HARNESS" not in src
