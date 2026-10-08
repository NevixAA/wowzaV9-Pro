"""Which leagues the scout watches.

    python -m src.scout.leagues --build docs/league_scout_af_odds_probe_2026_10_08.csv

Writes registry/scout_leagues.json. The collector reads that file and nothing else, so the
watch list is a reviewed, committed artifact rather than something recomputed on every run.

SELECTION (owner, 2026-10-08: "200 sounds great", the 30 lower-tier candidates "top of the list")

    priority 1   the 30 second/third tiers the owner named
    priority 2   everything else the probe found priced, ranked by how bettable it looks
                 (Pinnacle present, BTTS offered, Bet365 present, seasons of history)

Excluded, because they are either already Wowza's or out of scope by standing rule:
    - leagues v9 already bets (ENABLED_LEAGUES) — v9 collects those itself
    - the top flights of England, Spain, Germany, Italy and France (efficiently priced; the
      owner's rule is "only our leagues")
    - women's, youth, reserve and development competitions

Seasons are NOT stored here. The collector asks the API which season is current on every run,
because a season typed into a file froze collection once already (CLAUDE.md, COLLECT_SEASONS).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

REGISTRY = cfg.REGISTRY_DIR / "scout_leagues.json"
TARGET = 200

#: The owner's priority list (API-Football ids), from the 2026-10-08 probe.
PRIORITY_1 = (
    129,  # Argentina Primera Nacional
    72,   # Brazil Serie B
    99,   # Japan J2 League
    263,  # Mexico Liga de Expansion MX
    114,  # Sweden Superettan
    104,  # Norway 1. Division
    120,  # Denmark 1. Division
    219,  # Austria 2. Liga
    89,   # Netherlands Eerste Divisie
    95,   # Portugal Segunda Liga
    204,  # Turkey 1. Lig
    80,   # Germany 3. Liga
    63,   # France Ligue 3 (National)
    138, 942, 943,  # Italy Serie C groups A, B, C
    435, 436,       # Spain Primera RFEF groups 1, 2
    293,  # South Korea K League 2
    255,  # USA USL Championship
    145,  # Belgium Challenger Pro League
    208,  # Switzerland Challenge League
    107,  # Poland I Liga
    170,  # China League One
    358,  # Ireland First Division
    494,  # Greece Super League 2
    43,   # England National League       (v9 trains on it; has football-data O/U history)
    180, 183, 184,  # Scotland Championship, League One, League Two (same)
)

#: Top flights of the big five — efficiently priced, out of scope by the owner's rule.
TOP5_TOP_FLIGHTS = (39, 140, 78, 135, 61)

_NOT_SENIOR_MEN = re.compile(
    r"women|frauen|femen|feminin|kvinn|girls|damallsvenskan|toppserien|elitettan|wk-league|"
    r"reserve|youth|primavera|junior|development|\bu\s?\d\d\b|frauenliga", re.I)


def _v9_bet_league_ids() -> set[int]:
    from src.data import v9_config
    ids = v9_config.league_ids()
    return {int(ids[n]) for n in v9_config.enabled_leagues() if n in ids}


def select(probe: pd.DataFrame, exclude_ids: set[int], target: int = TARGET) -> pd.DataFrame:
    """Rank the probe table into the watch list. Pure: no I/O, so it is testable."""
    p = probe.copy()
    p = p[p["fx"].fillna(0) > 0]                                  # actually priced in the probe
    p = p[~p["id"].isin(exclude_ids | set(TOP5_TOP_FLIGHTS))]
    p = p[~p["name"].astype(str).str.contains(_NOT_SENIOR_MEN)]
    fx = p["fx"].clip(lower=1)
    p["score"] = (2.0 * p["pinnacle"].fillna(0)
                  + (p["btts"].fillna(0) / fx)
                  + (p["b365"].fillna(0) / fx)
                  + p["n_seasons"].clip(upper=10) / 10)
    p["priority"] = p["id"].isin(PRIORITY_1).map({True: 1, False: 2})
    p = p.sort_values(["priority", "score", "n_seasons"], ascending=[True, False, False])
    return p.head(target)


def build(probe_csv: Path) -> dict:
    probe = pd.read_csv(probe_csv)
    chosen = select(probe, _v9_bet_league_ids())
    missing_p1 = sorted(set(PRIORITY_1) - set(chosen["id"]))
    out = {
        "built_from": str(probe_csv.as_posix()),
        "rule": "priority 1 = owner's lower-tier list; priority 2 = remaining priced leagues "
                "ranked by Pinnacle/BTTS/Bet365 coverage and history. Excludes v9 bet leagues, "
                "big-five top flights, women/youth/reserve.",
        "priority_1_missing_from_probe": missing_p1,
        "leagues": [
            {"id": int(r.id), "country": r.country, "name": r["name"], "priority": int(r.priority),
             "pinnacle": bool(r.pinnacle), "n_seasons": int(r.n_seasons)}
            for _, r in chosen.iterrows()
        ],
    }
    REGISTRY.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def load() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["leagues"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", type=Path, required=True, help="probe CSV")
    a = ap.parse_args()
    out = build(a.build)
    n1 = sum(1 for x in out["leagues"] if x["priority"] == 1)
    print(f"{len(out['leagues'])} leagues ({n1} priority 1) -> {REGISTRY}")
    if out["priority_1_missing_from_probe"]:
        print("priority-1 ids not in the probe:", out["priority_1_missing_from_probe"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
