"""Forward-test registrations are immutable: a change is a NEW version with a new forward window."""
import json
from pathlib import Path

from src.monitoring.research_integrity import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_player_v3_v1_bytes_unchanged():
    lock = json.loads((ROOT / "registry/player_v3_forward/LOCK_v1.json").read_text(encoding="utf-8"))
    for rel, sha in lock["sha256"].items():
        assert content_sha256(ROOT / rel) == sha, f"{rel} changed after registration"


def test_lock_hash_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_bytes(b'{"x": 1}\r\n')
    b.write_bytes(b'{"x": 1}\n')
    assert content_sha256(a) == content_sha256(b)
    p, q = tmp_path / "a.pkl", tmp_path / "b.pkl"
    p.write_bytes(b"\x00\r\n")
    q.write_bytes(b"\x00\n")
    assert content_sha256(p) != content_sha256(q)          # binaries are never normalised


def test_player_v3_v2_matches_frozen_dict():
    from src.player_v3.consensus import REGISTRATION_V2
    p = ROOT / "registry/player_v3_forward/registration_v2.json"
    assert json.loads(p.read_text(encoding="utf-8")) == REGISTRATION_V2


def test_price_trader_v1_matches_frozen_dict():
    from src.price_trader.research import REGISTRATION_V1
    p = ROOT / "registry/price_trader/registration_v1.json"
    assert json.loads(p.read_text(encoding="utf-8")) == REGISTRATION_V1
