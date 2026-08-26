"""
Load v9's config.py without inheriting v9's dependencies.
=========================================================
WHY THIS EXISTS. Four Pro modules need v9's league mappings — team_stats, team_news,
weekly_audit and pro_tests — and v9 is the authoritative source, so duplicating the dicts is
exactly the divergence `model_type_for_league` is copied verbatim to avoid.

But `v9/config.py` line 15 is `from dotenv import load_dotenv`, and Pro's workflows install only
`pandas pyarrow requests` (+ numpy). So executing it raises ModuleNotFoundError in CI while
working perfectly on a laptop where v9's own environment has python-dotenv installed. That is how
the Pro Team News workflow failed on its first run: the collector was correct, the code path was
tested, and it died importing a package it never uses.

Adding python-dotenv to four workflow files would fix today's symptom and leave the mechanism in
place — the next optional import v9 acquires breaks Pro again, in CI only, on whichever workflow
happens to run first.

THE APPROACH: stub v9's optional imports, then execute.

Stubbing rather than parsing, deliberately. `ast.literal_eval` on the assignment would avoid
execution entirely, but it only works for literal values — `ENABLED_LEAGUES` and
`model_type_for_league` are built with comprehensions and functions, so half of what callers need
would be unavailable and the helper would silently serve a subset. Executing with a stub keeps
FULL fidelity: every constant and every function behaves exactly as v9 defines it.

The stub is inert. `load_dotenv()` returns False and reads nothing, which is correct here: Pro
must never pick up v9's secrets, and every value Pro wants from that file (league ids, sport keys,
format tags) is a hardcoded constant rather than an environment lookup. Anything v9 sources from
the environment resolves to None under this loader, which is the safe direction — a missing key is
visible, a silently inherited one is not.
"""
from __future__ import annotations

import importlib.util
import sys
import types

from config import pro_config as cfg

# Modules v9 imports that Pro does not install. Each is replaced with a stub exposing only what
# v9's config actually calls at import time.
_STUBS = {
    "dotenv": {"load_dotenv": lambda *a, **k: False,
               "find_dotenv": lambda *a, **k: "",
               "dotenv_values": lambda *a, **k: {}},
}

_CACHE = None


def load(force: bool = False):
    """v9's config module. Cached — executing it is not free and it has no side effects we want.

    Raises FileNotFoundError if v9 is not checked out, which is the honest failure: a caller that
    needs v9's league map cannot proceed without v9, and a stubbed-out empty mapping would turn
    that into "zero leagues" and look like a quiet day.
    """
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    path = cfg.V9_LOCAL / "config.py"
    if not path.exists():
        raise FileNotFoundError(
            f"v9 config not found at {path}. Set V9_LOCAL, or check out wowza-betting — Pro "
            f"reads v9's league mappings rather than keeping a second copy that can drift.")

    injected = []
    for name, attrs in _STUBS.items():
        if name in sys.modules:
            continue
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
        injected.append(name)

    try:
        # A distinctive module name, and NOT added to sys.path: inserting v9's directory shadows
        # Pro's own `config` PACKAGE for the rest of the process, which broke three test groups
        # when pro_tests did it.
        spec = importlib.util.spec_from_file_location("_v9_config_via_pro", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        # Remove only what we injected, so a real python-dotenv in the environment is untouched
        # for anything else in the process.
        for name in injected:
            sys.modules.pop(name, None)

    _CACHE = mod
    return mod


def league_ids() -> dict:
    """{league name: API-Football league id}."""
    return dict(load().API_FOOTBALL_IDS)


def sport_keys() -> dict:
    """{league name: OddsAPI sport key}."""
    return dict(getattr(load(), "ODDS_API_SPORT_KEYS", {}) or {})


def enabled_leagues() -> tuple:
    return tuple(load().ENABLED_LEAGUES)
