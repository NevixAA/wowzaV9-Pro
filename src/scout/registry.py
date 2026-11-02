"""Canonical Wowza league registry — one row per league, every system's view side by side.

    python -m src.scout.registry          # -> registry/wowza_league_registry.json (+ divergences)

WHY. League support in v9 is spread over hand-kept lists (STANDARD_FORMAT_LEAGUES,
NEW_FORMAT_LEAGUES, ENABLED_LEAGUES, PAPER_LEAGUES, API_FOOTBALL_ONLY_LEAGUES,
API_FOOTBALL_EXTRA_SEASONS, FOOTBALL_DATA_LEAGUES, API_FOOTBALL_IDS, ODDS_API_SPORT_KEYS, and the
player model's PROP_LEAGUES). They have diverged before — PROP_LEAGUES gained 18 leagues the
collector never fetched, Ligue 2 carried the wrong API id for months.

This module READS those lists — by parsing v9's source with `ast`, never importing or running it —
and joins them with the scout lifecycle into one registry with the fields the onboarding brief asks
for. It also lists every DIVERGENCE (a league enabled with no model format, a format league with no
API id, ...). It does not change v9. Making v9 derive its lists from this file is a separate,
reviewed production change (proposal in the registry's `proposal` field).
"""
from __future__ import annotations

import ast
import json

from config import pro_config as cfg

OUT = cfg.REGISTRY_DIR / "wowza_league_registry.json"
V9_NAMES = ("STANDARD_FORMAT_LEAGUES", "NEW_FORMAT_LEAGUES", "ENABLED_LEAGUES", "PAPER_LEAGUES",
            "API_FOOTBALL_ONLY_LEAGUES", "API_FOOTBALL_EXTRA_SEASONS", "FOOTBALL_DATA_LEAGUES",
            "API_FOOTBALL_IDS", "ODDS_API_SPORT_KEYS", "PROVIDER_UNSUPPORTED")


def literal_assignments(path, names) -> dict:
    """{name: value} for top-level `NAME = <literal>` / `NAME: T = <literal>` in a source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        tgt, val = None, None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            tgt, val = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            tgt, val = node.target.id, node.value
        if tgt in names:
            try:
                out[tgt] = ast.literal_eval(val)
            except ValueError:
                pass
    return out


MIN_V9_LEAGUES = 40

#: v9 season_rule.type -> this registry's season_type vocabulary.
_RULE_TO_SEASON_TYPE = {"start_year": "split_season", "end_year": "split_season",
                        "calendar_year": "calendar_year", "fixed": "tournament"}


def season_type_from_rule(rule, today: str | None = None) -> str | None:
    """season_type DERIVED from v9's registry season_rule (config/leagues.json), never from the
    model format. Data Truth round 3: it was `calendar_year if new_format else split_season`, which
    is wrong for every autumn-spring new-format league (Denmark, Austria, Romania, Saudi, Mexico...).
    `eras` -> the era in force on `today`; no rule -> None (unknown stays unknown)."""
    if not isinstance(rule, dict):
        return None
    if rule.get("type") == "eras" or "eras" in rule:
        day = today or __import__("datetime").date.today().isoformat()
        cur = None
        for er in rule.get("eras") or []:
            if str(er.get("from", "0000")) <= day and (er.get("until") is None or day < str(er["until"])):
                cur = er
        return _RULE_TO_SEASON_TYPE.get((cur or {}).get("type"))
    return _RULE_TO_SEASON_TYPE.get(rule.get("type"))


def _v9_tables() -> dict:
    """v9's league tables as v9 itself computes them (src/data/v9_config.load executes config.py).

    Since v9 R2-A (2026-11-01) config.py DERIVES these from config/leagues.json, so the old
    `ast.literal_eval` read returned {} for every one: the committed registry fell from 49 leagues
    to 29, all PLAYER_ONLY, live leagues included, and the drift check passed on nothing (Data
    Truth audit finding 49). Fails LOUDLY when the read is implausibly small."""
    from src.data import v9_config
    mod = v9_config.load()
    out = {n: getattr(mod, n) for n in V9_NAMES if hasattr(mod, n)}
    for n in ("STANDARD_FORMAT_LEAGUES", "NEW_FORMAT_LEAGUES", "ENABLED_LEAGUES", "PAPER_LEAGUES",
              "API_FOOTBALL_ONLY_LEAGUES"):
        if n in out:
            out[n] = list(out[n])
    for n in ("FOOTBALL_DATA_LEAGUES", "API_FOOTBALL_IDS", "ODDS_API_SPORT_KEYS", "PROVIDER_UNSUPPORTED"):
        if n in out:
            out[n] = dict(out[n])
    n_lg = len(set(out.get("STANDARD_FORMAT_LEAGUES", ())) | set(out.get("NEW_FORMAT_LEAGUES", ()))
               | set(out.get("API_FOOTBALL_IDS", {})))
    if n_lg < MIN_V9_LEAGUES:
        raise RuntimeError(f"v9 league tables read only {n_lg} leagues (< {MIN_V9_LEAGUES}) — refusing "
                           f"to publish a registry that would mark live leagues unsupported")
    return out


def build() -> dict:
    v9 = _v9_tables()
    pm = literal_assignments(cfg.V9_LOCAL / "player_model" / "config.py", ("PROP_LEAGUES",))
    lc_f = cfg.REGISTRY_DIR / "league_lifecycle.json"
    lc = json.loads(lc_f.read_text(encoding="utf-8")) if lc_f.exists() else {}
    std, nf = set(v9.get("STANDARD_FORMAT_LEAGUES", ())), set(v9.get("NEW_FORMAT_LEAGUES", ()))
    enabled, paper = set(v9.get("ENABLED_LEAGUES", ())), set(v9.get("PAPER_LEAGUES", ()))
    af_only, fd = set(v9.get("API_FOOTBALL_ONLY_LEAGUES", ())), v9.get("FOOTBALL_DATA_LEAGUES", {})
    ids, odds_keys = v9.get("API_FOOTBALL_IDS", {}), v9.get("ODDS_API_SPORT_KEYS", {})
    props = pm.get("PROP_LEAGUES", {})
    # Leagues v9 documents as NOT offered by a provider (e.g. OddsAPI has no Romanian competition at
    # any tier, config.PROVIDER_UNSUPPORTED). A missing key there is a known fact, not a divergence.
    unsupported = v9.get("PROVIDER_UNSUPPORTED", {}) or {}
    leagues = sorted(std | nf | enabled | paper | af_only | set(ids) | set(odds_keys) | set(props))
    from src.data import v9_config
    lreg = v9_config.league_registry()

    def _rule(lg):
        e = lreg.entry(lg) if hasattr(lreg, "entry") else None
        if e is None and lreg.canonical_name(lg):
            e = lreg.entry(lreg.canonical_name(lg))
        return (e or {}).get("season_rule")

    rows = []
    for lg in leagues:
        fmt = "standard" if lg in std else "new_format" if lg in nf else None
        deploy = ("PAPER" if lg in paper else "LIVE" if lg in enabled and fmt else
                  "TRAINING_ONLY" if fmt else "PLAYER_ONLY" if lg in props else "UNSUPPORTED")
        rows.append({
            "league_name": lg, "api_football_id": ids.get(lg) if lg in ids else props.get(lg),
            "odds_api_key": odds_keys.get(lg), "football_data_code": fd.get(lg),
            "season_type": season_type_from_rule(_rule(lg)),
            "standard_supported": lg in std, "new_format_supported": lg in nf,
            "side_markets_supported": bool(fmt), "player_supported": lg in props,
            "v11_supported": lg in enabled and lg not in paper and bool(fmt),
            "deployment_state": deploy, "source": "api_football_only" if lg in af_only else
            ("football_data" if lg in fd else None), "scout_state": None,
        })
    for lid, rec in lc.items():
        if rec.get("state") in ("SHADOW_APPROVED", "WOWZA_SUPPORTED", "PAPER_ACTIVE"):
            rows.append({"league_name": f"scout:{lid}", "api_football_id": int(lid),
                         "deployment_state": "SHADOW", "scout_state": rec["state"]})
    div = []
    for r in rows:
        lg = r["league_name"]
        if lg.startswith("scout:"):
            continue
        if lg in enabled and not (r["standard_supported"] or r["new_format_supported"]):
            div.append(f"{lg}: ENABLED but in no model-format list")
        if (r["standard_supported"] or r["new_format_supported"]) and r["api_football_id"] is None:
            div.append(f"{lg}: model league with no API-Football id")
        if lg in enabled and lg not in paper and r["odds_api_key"] is None and r["source"] != "api_football_only":
            if lg in unsupported:
                r["provider_note"] = str(unsupported[lg].get("reason", "provider does not offer it"))
            else:
                div.append(f"{lg}: live league with no OddsAPI sport key")
        if lg in paper and lg not in enabled:
            div.append(f"{lg}: PAPER but not ENABLED (would stop collection)")
    live_unsupported = [r["league_name"] for r in rows
                        if r["league_name"] in enabled and r.get("deployment_state") == "PLAYER_ONLY"]
    if live_unsupported:
        raise RuntimeError(f"ENABLED v9 league(s) came out PLAYER_ONLY: {live_unsupported}")
    return {"generated_from": "v9 config.py as v9 computes it (src/data/v9_config) + "
                              "player_model/config.py (ast, read-only) + scout lifecycle",
            "n_leagues": len(rows), "leagues": rows, "divergences": div,
            "proposal": "Have v9 derive these lists from one committed registry file in a reviewed PR; "
                        "a test then asserts every derived list equals today's literal (behaviour-identical)."}


def main() -> int:
    r = build()
    OUT.write_text(json.dumps(r, indent=1), encoding="utf-8")
    print(f"{r['n_leagues']} leagues; {len(r['divergences'])} divergence(s):")
    for d in r["divergences"]:
        print("  -", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
