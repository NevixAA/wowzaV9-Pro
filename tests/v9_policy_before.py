"""v9's bankroll policy as it was before the owner's 2026-11-17 decision ("Yes, adopt": every v9 cell and track at
0, the only real stake is the manual TOP-3 flat stake). Pro's bankroll MECHANICS tests (allocator, simulator, side
routing) need staked tracks; v9 keeps each entry's previous values in `before_2026_11_17`, restored here. Never used
by production code."""
from __future__ import annotations


def before_2026_11_17(policy: dict) -> dict:
    import copy
    p = copy.deepcopy(policy)
    p.pop("top3_league", None)
    entries = list((p.get("tracks") or {}).values()) + list(((p.get("cell_staking") or {}).get("cells") or {}).values())
    for t in entries:
        t.update(t.pop("before_2026_11_17", {}))
        t.pop("staking_basis_2026_11_17", None)
    return p
