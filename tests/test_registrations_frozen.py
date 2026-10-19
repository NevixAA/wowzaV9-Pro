"""Forward-test registrations are immutable: a change is a NEW version with a new forward window."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_player_v3_v1_bytes_unchanged():
    lock = json.loads((ROOT / "registry/player_v3_forward/LOCK_v1.json").read_text(encoding="utf-8"))
    for rel, sha in lock["sha256"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, f"{rel} changed after registration"


def test_player_v3_v2_matches_frozen_dict():
    from src.player_v3.consensus import REGISTRATION_V2
    p = ROOT / "registry/player_v3_forward/registration_v2.json"
    assert json.loads(p.read_text(encoding="utf-8")) == REGISTRATION_V2


def test_price_trader_v1_matches_frozen_dict():
    from src.price_trader.research import REGISTRATION_V1
    p = ROOT / "registry/price_trader/registration_v1.json"
    assert json.loads(p.read_text(encoding="utf-8")) == REGISTRATION_V1
