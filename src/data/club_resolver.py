"""
League-scoped club-name resolution between v9's odds naming and football-data's.
================================================================================
The backfill joined only 264 of 935 fixtures (28.2%), and the cause is naming, not availability.
656 of the 671 misses are in leagues where OTHER fixtures joined fine, so the results exist.

MEASURED per league: 143 v9 club names have no `club_slug` match in football-data's vocabulary,
and the pattern is systematic — v9 (via OddsAPI) writes the long form, football-data the short one:

    Birmingham City / Birmingham        Bolton Wanderers / Bolton
    Blackburn Rovers / Blackburn        Accrington Stanley / Accrington

which is why the English leagues, the ones football-data covers BEST, had the worst join rates
(Championship 8%, League One 8%, League Two 12%).

WHY NOT JUST STRIP "City", "United", "Rovers", "Town"
This is the trap invariant 11 exists for. Strip both "City" and "United" and Manchester City and
Manchester United both become `manchester` — a silent, confident, wrong join. Any fix here must
make ambiguity a REFUSAL, never a guess.

THE RULE. Within one league only, a v9 name resolves to a football-data name when their identity
tokens are in a subset relation (one is the other named longer), AND that pairing is unique in
BOTH directions:

  * forward  — exactly one football-data candidate for this v9 name.
    Otherwise `Bristol City` could match both `Bristol City` and `Bristol`.
  * backward — no OTHER v9 name in the league claims the same football-data name.
    This is the one that actually saves us: if football-data lists a bare `Bristol`, then both
    `Bristol City` and `Bristol Rovers` subset-match it, each seeing exactly one candidate. The
    forward check passes for both and they would BOTH map to `Bristol` — two different clubs
    collapsed onto one. Only the reverse check catches it, so both are refused.

League scoping is load-bearing: `Arsenal` in the Premier League and `Arsenal de Sarandí` in
Argentina must never meet, and two clubs sharing a city are far more likely to collide inside one
competition than across two.

Refusals are RECORDED, not silently dropped, so the residual is visible and reviewable rather than
being mistaken for an absence of fixtures.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .entities import club_slug


@dataclass
class ResolutionReport:
    """What the resolver did, per league — the auditable record of a naming decision."""
    exact: dict[str, str] = field(default_factory=dict)        # v9 name -> fd name
    resolved: dict[str, str] = field(default_factory=dict)     # v9 name -> fd name (via tokens)
    refused: dict[str, str] = field(default_factory=dict)      # v9 name -> why
    unmatched: list[str] = field(default_factory=list)         # no candidate at all

    @property
    def alias_map(self) -> dict[str, str]:
        """Every accepted mapping, exact and token-resolved."""
        return {**self.exact, **self.resolved}

    def summary(self) -> str:
        return (f"exact={len(self.exact)} resolved={len(self.resolved)} "
                f"refused={len(self.refused)} unmatched={len(self.unmatched)}")


def _tokens(name: str) -> frozenset[str]:
    s = club_slug(name)
    return frozenset(t for t in s.split("-") if t)


def resolve_league(v9_names: list[str], fd_names: list[str]) -> ResolutionReport:
    """Resolve one league's v9 club names onto that league's football-data names."""
    rep = ResolutionReport()
    fd_by_slug: dict[str, str] = {}
    for n in fd_names:
        if n and str(n).strip():
            fd_by_slug.setdefault(club_slug(n), str(n))
    fd_tokens = {n: _tokens(n) for n in fd_by_slug.values()}

    # Pass 1: exact slug agreement needs no inference at all.
    pending: list[str] = []
    for n in v9_names:
        if not n or not str(n).strip():
            continue
        s = club_slug(n)
        if s in fd_by_slug:
            rep.exact[str(n)] = fd_by_slug[s]
        else:
            pending.append(str(n))

    # Pass 2: candidates by subset relation, forward-unique only.
    proposals: dict[str, str] = {}
    for n in pending:
        tn = _tokens(n)
        if not tn:
            rep.unmatched.append(n)
            continue
        cands = [fd for fd, tf in fd_tokens.items()
                 if tf and (tn <= tf or tf <= tn)]
        # A football-data name already claimed by an EXACT match is not available for inference;
        # the exact match is stronger evidence and must win.
        taken = set(rep.exact.values())
        cands = [c for c in cands if c not in taken]
        if not cands:
            rep.unmatched.append(n)
        elif len(cands) > 1:
            rep.refused[n] = f"ambiguous_forward: {sorted(cands)[:4]}"
        else:
            proposals[n] = cands[0]

    # Pass 3: reverse uniqueness. Two different v9 clubs claiming one football-data name means we
    # cannot tell them apart, so neither is accepted. This is the check that stops
    # Bristol City + Bristol Rovers both collapsing onto a bare "Bristol".
    claims: dict[str, list[str]] = defaultdict(list)
    for v9n, fdn in proposals.items():
        claims[fdn].append(v9n)
    for fdn, claimants in claims.items():
        if len(claimants) == 1:
            rep.resolved[claimants[0]] = fdn
        else:
            for c in sorted(claimants):
                rep.refused[c] = f"ambiguous_reverse: {sorted(claimants)} all match {fdn!r}"
    return rep


def build_alias_map(v9_by_league: dict[str, list[str]],
                    fd_by_league: dict[str, list[str]]) -> tuple[dict[tuple[str, str], str],
                                                                 dict[str, ResolutionReport]]:
    """Alias map keyed by (league, v9_name) -> football-data name, plus per-league reports.

    Keyed by league deliberately: the same string can be different clubs in different
    competitions, so a flat global map would be exactly the bug this module exists to avoid.
    """
    alias: dict[tuple[str, str], str] = {}
    reports: dict[str, ResolutionReport] = {}
    for lg, names in v9_by_league.items():
        fd = fd_by_league.get(lg)
        if not fd:
            reports[lg] = ResolutionReport(unmatched=sorted({str(n) for n in names if n}))
            continue
        rep = resolve_league(sorted({str(n) for n in names if n}), fd)
        reports[lg] = rep
        for v9n, fdn in rep.alias_map.items():
            alias[(lg, v9n)] = fdn
    return alias, reports


def apply_alias(name: str, league: str, alias: dict[tuple[str, str], str]) -> str:
    """Map a v9 club name to football-data's, or return it unchanged when there is no mapping."""
    return alias.get((league, str(name)), str(name))
