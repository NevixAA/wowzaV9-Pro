"""Price Trader v2 guards: entries never use the future, registration is frozen, no orders exist."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.price_trader import research as R  # noqa: E402

KO = pd.Timestamp("2026-10-25 15:00", tz="UTC")


def _path(rows):
    """rows: (minutes_to_kickoff, best_back, best_opposite, consensus_p)."""
    return pd.DataFrame([{"timestamp": KO - pd.Timedelta(minutes=m), "minutes_to_kickoff": float(m),
                          "best_back": b, "best_opposite": o, "exch_back": float("nan"),
                          "exch_opposite": float("nan"), "consensus_probability": p} for m, b, o, p in rows])


def test_entry_never_uses_a_quote_after_the_entry_moment():
    v = R._side_view(_path([(3000, 2.0, 1.9, 0.50), (1500, 2.1, 1.8, 0.48), (100, 2.4, 1.6, 0.42)]), False)
    sig = KO - pd.Timedelta(minutes=4000)
    i = R.entry_row(v, 24 * 60, sig, KO)            # T-24h = 1440 min -> last quote at/before is 1500
    assert v["mins"][i] == 1500


def test_signal_from_the_future_is_never_borrowed():
    v = R._side_view(_path([(3000, 2.0, 1.9, 0.50), (100, 2.4, 1.6, 0.42)]), False)
    sig = KO - pd.Timedelta(minutes=500)            # signal arrives after T-24h
    assert R.entry_row(v, 24 * 60, sig, KO) is None
    i = R.entry_row(v, None, sig, KO)               # EARLIEST = first quote at/after the signal
    assert v["mins"][i] == 100


def test_no_post_kickoff_exit():
    v = R._side_view(_path([(600, 2.0, 1.9, 0.50), (-10, 2.0, 1.2, 0.40)]), False)
    s = R.simulate(v, 0, "GREEN_1PCT", 0.0, 0.0, use_exchange=False)
    # the only green quote is after kickoff -> must not be taken
    assert s["state"] != "CLOSED_GREEN" or s.get("exit_ts") < KO


def test_state_machine_reads_only_the_past():
    """Same path up to row k must give the same decision at row k whatever comes later."""
    base = [(600, 2.0, 2.0, 0.50), (300, 1.9, 2.2, 0.52)]
    a = R.simulate(R._side_view(_path(base + [(120, 2.0, 1.5, 0.60)]), False), 0, "GREEN_2PCT", 0.0, 0.0, False)
    b = R.simulate(R._side_view(_path(base + [(120, 2.0, 3.0, 0.40)]), False), 0, "GREEN_2PCT", 0.0, 0.0, False)
    # backed 2.00; row 1 the OPPOSITE lengthens to 2.20 -> locked 1 - 2/2.2 = +9.1%: both must close
    # there, at the same P/L, whatever the third row later says
    assert a["state"] == b["state"] == "CLOSED_GREEN"
    assert a["pnl"] == pytest.approx(b["pnl"])


def test_states_are_from_the_registered_vocabulary():
    allowed = {"CANDIDATE", "ENTERED", "WAITING_FOR_TARGET", "FULL_GREEN_AVAILABLE", "PARTIAL_HEDGE_AVAILABLE",
               "STOP_TRIGGERED", "CLOSED_GREEN", "CLOSED_PARTIAL", "CLOSED_STOP", "HELD_TO_KICKOFF",
               "VOID_DATA_FAILURE", "TIME_EXIT"}
    v = R._side_view(_path([(600, 2.0, 1.9, 0.50), (300, 2.0, 2.2, 0.45)]), False)
    for rule in R.RULES:
        s = R.simulate(v, 0, rule, 0.0, 0.0, False)
        assert {st for st, _ in s["log"]} <= allowed


def test_registration_is_immutable(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "REG_DIR", tmp_path)
    R.registration()
    p = tmp_path / "registration_v1.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["exit_rules"] = ["GREEN_9PCT"]
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(RuntimeError):
        R.registration()


def test_lay_and_arbitrage_are_never_claimed_without_size():
    st = R.data_status(_path([(600, 2.0, 1.9, 0.5)]))
    assert st["STRICT_ARBITRAGE_TESTABLE"] == "NO" and st["CAPACITY_UNKNOWN"] == "YES"
    assert st["SYNTHETIC_ODDS_USED"] == "NO"


def test_price_trader_cannot_place_orders():
    """No HTTP clients, no order verbs anywhere in the price-trader package."""
    pkg = Path(R.__file__).parent
    src = "\n".join(p.read_text(encoding="utf-8") for p in pkg.glob("*.py"))
    for banned in ("requests.post", "place_order", "placeOrders", "betfairlightweight", "submit_bet"):
        assert banned not in src
