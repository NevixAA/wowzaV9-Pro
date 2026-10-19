"""Bankroll review evidence panel: reporting only; research modules can never get stakes."""
import pandas as pd

from src.bankroll import run as R


def test_panel_never_allows_research_stakes():
    b = pd.DataFrame({"unit": [1.0, -1.0, 0.9], "league": ["A", "B", "A"], "market": ["OU25"] * 3,
                      "clv": [0.01, -0.02, 0.0]})
    p = R.evidence_panel(b, pd.DataFrame())
    assert p["PRICE_TRADER_STAKES_ALLOWED"] == "NO" and p["PLAYER_V3_STAKES_ALLOWED"] == "NO"
    assert p["RATING_MAY_INCREASE_STAKE_ABOVE_BASE"].startswith("NO")
    assert p["N"] == 3 and abs(p["realized_ROI"] - 0.3 / 3) < 1e-9


def test_panel_handles_no_bets():
    assert R.evidence_panel(pd.DataFrame(), pd.DataFrame())["PLAYER_V3_STAKES_ALLOWED"] == "NO"
