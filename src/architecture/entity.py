"""Resolve club identity across providers, by EVIDENCE rather than by string similarity.

The brief is explicit (section 25): do not fuzzy-match silently, and quarantine what is
ambiguous. That rule exists because this estate has already been burned by the opposite -- a
naive `startswith(first_word)` mapped "Real Valladolid CF" onto any club beginning "Real" and
left 46% of standard fixtures with no form data.

THE PROBLEM. `fd_history` says "1. FC Koln"; `backtest_all_leagues` says "FC Koln". Same club,
two strings. Merge without resolving and one club becomes two, which silently destroys every
rolling-form feature built on it -- and, worse, inflates a "we have N more fixtures!" headline
with fixtures that are duplicates of ones we already had.

HOW THIS RESOLVES THEM, and why it is not fuzzy matching. A candidate pair is only accepted when
the DATA agrees, not when the strings look alike:

    1. Two fixtures in the same LEAGUE on the same DATE, whose OTHER side already matches
       exactly, propose a mapping between their two home-team strings.
    2. That proposal is accepted only if the two rows also agree on the SCORE.
    3. A string that proposes two different partners is AMBIGUOUS and is quarantined, never
       guessed.

So "FC Koln" maps to "1. FC Koln" because on 2024-02-17 both played the same opponent in the
same league and both record 2-1 -- not because the strings share a substring. A pair that never
co-occurs is simply left unresolved and counted as unresolved, which is the honest outcome.

Normalisation (accents, punctuation, common affixes) is used ONLY to propose candidates and
never to accept one. Acceptance always requires the fixture-level evidence above.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import pandas as pd

CALC_VERSION = "1.0.0"

_AFFIX = re.compile(r"^(1\.?\s*)?(fc|cf|sc|ac|as|ss|ssc|us|usc|rc|cd|ud|sv|tsv|vfl|vfb|fk|nk|"
                    r"bk|if|ik|afc|cfc)\b|\b(fc|cf|sc|ac|afc|cfc|sk|sv|bk|if|ik|kv|vv)$")


def norm(s: str) -> str:
    """Normalised form used ONLY to propose candidate pairs, never to accept one."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    prev = None
    while prev != s:
        prev = s
        s = _AFFIX.sub("", s).strip()
    return re.sub(r"\s+", " ", s).strip()


def _fx(d: pd.DataFrame) -> pd.DataFrame:
    out = d[["date", "league", "home_team", "away_team", "home_goals", "away_goals"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ("league", "home_team", "away_team"):
        out[c] = out[c].astype(str).str.strip()
    return out.dropna(subset=["date"])


def build_mapping(a: pd.DataFrame, b: pd.DataFrame, *,
                  min_evidence: int = 2) -> tuple[dict, pd.DataFrame]:
    """Map club strings in `b` onto club strings in `a`, per league.

    Returns (mapping, audit_frame). `mapping` is keyed (league, name_in_b) -> name_in_a and
    contains only pairs with at least `min_evidence` agreeing fixtures and no competing partner.
    """
    A, B = _fx(a), _fx(b)
    votes: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    conflicts: dict[tuple, int] = defaultdict(int)

    for side, other in (("home_team", "away_team"), ("away_team", "home_team")):
        # Anchor on an EXACT match of the other side, same league, same date.
        ja = A[["date", "league", other, side, "home_goals", "away_goals"]]
        jb = B[["date", "league", other, side, "home_goals", "away_goals"]]
        m = ja.merge(jb, on=["date", "league", other], suffixes=("_a", "_b"))
        if m.empty:
            continue
        agree = (m["home_goals_a"] == m["home_goals_b"]) & (m["away_goals_a"] == m["away_goals_b"])
        for (lg, na, nb), ok in zip(zip(m["league"], m[f"{side}_a"], m[f"{side}_b"]), agree):
            if ok:
                votes[(lg, nb)][na] += 1
            else:
                conflicts[(lg, nb)] += 1

    mapping, rows = {}, []
    for (lg, nb), cand in votes.items():
        best, n = max(cand.items(), key=lambda kv: kv[1])
        runner = sorted(cand.values(), reverse=True)[1] if len(cand) > 1 else 0
        status = ("ACCEPTED" if n >= min_evidence and runner == 0 else
                  "AMBIGUOUS" if runner > 0 else "WEAK_EVIDENCE")
        if status == "ACCEPTED":
            mapping[(lg, nb)] = best
        rows.append({"league": lg, "name_b": nb, "name_a": best, "evidence": n,
                     "runner_up_evidence": runner, "score_conflicts": conflicts.get((lg, nb), 0),
                     "identical_string": nb == best, "same_normalised": norm(nb) == norm(best),
                     "status": status, "calc_version": CALC_VERSION})
    audit = pd.DataFrame(rows).sort_values(["status", "league", "name_b"])
    return mapping, audit


def apply_mapping(d: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    out = _fx(d)
    for c in ("home_team", "away_team"):
        out[c] = [mapping.get((lg, nm), nm) for lg, nm in zip(out["league"], out[c])]
    return out


def fixture_key(d: pd.DataFrame) -> pd.Series:
    return (pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d") + "|"
            + d["home_team"].astype(str).str.strip() + "|"
            + d["away_team"].astype(str).str.strip())
