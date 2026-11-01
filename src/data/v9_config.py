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

    # Since the R2-A league registry (v9 246b2cc4, 2026-11-01) v9's config runs
    # `from src import league_registry`. Pro also has a top-level `src`, already in sys.modules, so
    # that import resolved to PRO's package and died with ImportError — Team Stats and Studies both
    # failed on it. Hide Pro's `src` while v9's config executes so `src` means v9's, then put Pro's
    # back. v9's src modules stay reachable through the loaded config's own references.
    pro_src = {n: m for n, m in sys.modules.items() if n == "src" or n.startswith("src.")}
    saved_path = list(sys.path)
    for n in pro_src:
        del sys.modules[n]
    sys.path.insert(0, str(path.parent))

    try:
        # A distinctive module name. sys.path is restored below: v9's config inserts its own
        # directory and leaves it there, which shadows Pro's own `config` PACKAGE for the rest of
        # the process — that broke three test groups when pro_tests did it.
        spec = importlib.util.spec_from_file_location("_v9_config_via_pro", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        # Remove only what we injected, so a real python-dotenv in the environment is untouched
        # for anything else in the process.
        for name in injected:
            sys.modules.pop(name, None)
        for n in [n for n in sys.modules if n == "src" or n.startswith("src.")]:
            del sys.modules[n]
        sys.modules.update(pro_src)
        sys.path[:] = saved_path

    _CACHE = mod
    return mod


def league_ids() -> dict:
    """{league name: API-Football league id}."""
    return dict(load().API_FOOTBALL_IDS)


def api_season(league: str, when) -> str | None:
    """API-Football season for `league` on date `when`, by v9's CANONICAL resolver
    (config/leagues.json + auto_leagues.json season rules; the module v9's config imported).
    None when v9 cannot resolve it. This covers every league v9 knows - top flights and European
    cups included - where Pro's own season calendar only has the model leagues, so collectors
    using it skipped the Premier League, La Liga, Champions League... (Data Truth audit, found
    validating the finding-34 fix)."""
    sr = getattr(load(), "_season_resolver", None)
    if sr is None:
        return None
    s = sr.resolve_api_season(league, str(when)[:10])
    return s if sr.is_known(s) else None


def sport_keys() -> dict:
    """{league name: OddsAPI sport key}."""
    return dict(getattr(load(), "ODDS_API_SPORT_KEYS", {}) or {})


def enabled_leagues() -> tuple:
    return tuple(load().ENABLED_LEAGUES)


# ── v9 league registry + club resolver (Data Truth 2026-11-01) ──────────────────────────────────
# Every league name, list, model type and paper flag Pro needs comes from v9's config/leagues.json
# through v9's own src/league_registry, never from a list typed in Pro. Unknown -> None, not a guess.

def league_registry():
    """v9's src/league_registry module (the one v9's config imported)."""
    return load()._league_registry


def canonical_league(name) -> str | None:
    """Canonical league name for a canonical name or registered alias; None when unknown."""
    return league_registry().canonical_name(name)


def paper_leagues() -> frozenset:
    """Leagues the registry marks paper (predicted, never sent, never staked)."""
    return frozenset(load().PAPER_LEAGUES)


def is_paper(league) -> bool:
    """True when the league - by canonical name or any registered alias - is a paper league."""
    return canonical_league(league) in paper_leagues()


def drop_paper_leagues(df, col: str = "league"):
    """Rows of `df` whose league is NOT paper, matched on the canonical name so an alias
    spelling of a paper league is dropped too (a raw isin() let it through)."""
    if df is None or len(df) == 0 or col not in df.columns:
        return df
    paper = paper_leagues()
    canon = df[col].map(canonical_league)
    return df[~(canon.isin(paper) | df[col].astype(str).str.strip().isin(paper))]


def model_type(league) -> str | None:
    """'standard' | 'new_format' for a league the registry knows, else None (never 'unknown')."""
    lg = canonical_league(league)
    if lg is None:
        return None
    m = load()
    if lg in m.STANDARD_FORMAT_LEAGUES:
        return "standard"
    if lg in m.NEW_FORMAT_LEAGUES:
        return "new_format"
    return None


def leagues_of_type(competition_type: str) -> frozenset:
    """Canonical names whose registry `competition_type` equals the given one ('club_league' |
    'club_cup' | 'national_teams', registry LR-1.1). Raises when the checked-out registry has no
    competition_type at all - an empty set would read as 'no cups' and silently change results."""
    entries = league_registry().leagues()
    if not any("competition_type" in e for e in entries):
        raise RuntimeError("v9 config/leagues.json has no competition_type (needs registry LR-1.1)")
    return frozenset(e["name"] for e in entries if e.get("competition_type") == competition_type)


def standard_leagues() -> frozenset:
    return frozenset(load().STANDARD_FORMAT_LEAGUES)


def new_format_leagues() -> frozenset:
    return frozenset(load().NEW_FORMAT_LEAGUES)


def football_data_codes() -> dict:
    """{league: football-data.co.uk code} for the leagues the registry maps to football-data."""
    return dict(load().FOOTBALL_DATA_LEAGUES)


_TEAM_NAMES = None


def team_names():
    """v9's src/team_names module (resolve / resolve_result), loaded by path so Pro's own `src`
    is never shadowed. Raises FileNotFoundError when v9 is not checked out."""
    global _TEAM_NAMES
    if _TEAM_NAMES is None:
        p = cfg.V9_LOCAL / "src" / "team_names.py"
        if not p.exists():
            raise FileNotFoundError(f"v9 team_names not found at {p}")
        spec = importlib.util.spec_from_file_location("_v9_team_names_via_pro", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TEAM_NAMES = mod
    return _TEAM_NAMES
