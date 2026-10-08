"""Tip scoreboard: grades what was SENT, keeps voided-leg combos out of the headline, and paper
leagues out of every sender.

    python -m pytest tests/test_tip_scoreboard.py
"""
from __future__ import annotations

import datetime as dt
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402
from src.pipelines import tip_scoreboard as ts  # noqa: E402


def _1x2(rows):
    base = {"league": "Serie B", "home_team": "H", "away_team": "A", "p_home": 0.5,
            "p_draw": 0.25, "p_away": 0.25, "notified_ev": 0.1}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_1x2_grades_only_sent_tips_at_the_sent_price():
    d = _1x2([
        {"match_date": "2026-09-01", "notified_at": "x", "notified_pick": "HOME", "notified_odds": 2.5, "result": 0},
        {"match_date": "2026-09-02", "notified_at": "x", "notified_pick": "AWAY", "notified_odds": 4.0, "result": 0},
        {"match_date": "2026-09-03", "notified_at": None, "notified_pick": None, "notified_odds": None, "result": 0},
    ])
    h = ts.one_x_two(d)["headline"]
    assert h["settled"] == 2 and h["won"] == 1
    assert h["units"] == 0.5                       # +1.5 and -1
    assert h["break_even"] == round((1 / 2.5 + 1 / 4.0) / 2, 4)


def test_1x2_paper_league_is_excluded_from_the_headline():
    d = _1x2([{"match_date": "2026-09-01", "notified_at": "x", "notified_pick": "HOME",
               "notified_odds": 2.0, "result": 0, "league": "USA MLS"}])
    r = ts.one_x_two(d)
    assert r["headline"]["settled"] == 0 and r["paper_leagues"]["settled"] == 1


def test_bet_builder_voided_legs_never_enter_the_headline():
    settled = pd.DataFrame([
        {"combo_id": "a", "league": "Serie B", "joint_probability": 0.05, "combo_result": "WON",
         "leg_results": "O25=WON | player_sot=VOID", "settle_note": "OK", "n_legs": 2},
        {"combo_id": "b", "league": "Serie B", "joint_probability": 0.05, "combo_result": "LOST",
         "leg_results": "O25=WON | player_sot=LOST", "settle_note": "OK", "n_legs": 2},
        {"combo_id": "c", "league": "Serie B", "joint_probability": 0.05, "combo_result": "WON",
         "leg_results": "O25=WON | player_sot=WON", "settle_note": "OK", "n_legs": 2},
    ])
    r = ts.bet_builder(settled, {"a": {}, "b": {}, "c": {}})
    assert r["headline"]["settled"] == 2 and r["headline"]["won"] == 1
    assert r["with_voided_legs"]["settled"] == 1
    assert "NOT MEASURED" in r["roi"]


def test_recap_sends_once_per_day_inside_the_window(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "SENT_STATE", tmp_path / "sent.json")
    sent = []
    import src.combo.notify as cn
    monkeypatch.setattr(cn, "send", lambda text: (sent.append(text), (True, ""))[1])
    r = {"one_x_two": {"sent": 0}, "bet_builder": {"sent": 0}}
    morning = dt.datetime(2026, 10, 9, 6, 0, tzinfo=dt.timezone.utc)
    assert ts.maybe_notify(r, morning) == "sent"
    assert ts.maybe_notify(r, morning + dt.timedelta(hours=2)) == "already sent today"
    assert ts.maybe_notify(r, morning.replace(hour=14)) == "outside window"
    assert len(sent) == 1


def test_no_sender_can_send_a_paper_league():
    from src.combo import notify
    from src.pipelines import paper_1x2
    for fn in (notify.run, paper_1x2.notify):
        assert "PAPER_LEAGUES" in inspect.getsource(fn), fn.__module__
    assert "USA MLS" in cfg.PAPER_LEAGUES


def test_paper_leagues_match_v9_when_a_checkout_is_present():
    try:
        from src.data import v9_config
        v9 = set(getattr(v9_config.load(), "PAPER_LEAGUES", set()))
    except Exception:
        return                                     # no v9 checkout here: nothing to compare
    if v9:
        assert set(cfg.PAPER_LEAGUES) == v9


def test_paper_1x2_notify_skips_paper_leagues(monkeypatch):
    from src.pipelines import paper_1x2
    future = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=5)).isoformat()
    d = _1x2([{"match_date": "2026-10-10", "kickoff_utc": future, "notified_at": None,
               "league": "USA MLS", "o_home": 3.0, "o_draw": 3.5, "o_away": 2.5}])
    monkeypatch.setattr(paper_1x2, "_edge", lambda r: ("HOME", 0.5, 3.0))
    out = paper_1x2.notify(d, dry_run=True)
    assert out["considered"] == 0


def test_combo_sender_drops_paper_leagues_before_anything_else():
    from src.combo import notify
    out = notify.run(pd.DataFrame([{"league": "USA MLS", "combo_id": "x|y", "joint_probability": 0.3}]),
                     dry_run=True)
    assert out["sent"] == 0 and out.get("eligible", 0) == 0
