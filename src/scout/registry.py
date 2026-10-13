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
            "API_FOOTBALL_IDS", "ODDS_API_SPORT_KEYS")


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


def build() -> dict:
    v9 = literal_assignments(cfg.V9_LOCAL / "config.py", V9_NAMES)
    pm = literal_assignments(cfg.V9_LOCAL / "player_model" / "config.py", ("PROP_LEAGUES",))
    lc_f = cfg.REGISTRY_DIR / "league_lifecycle.json"
    lc = json.loads(lc_f.read_text(encoding="utf-8")) if lc_f.exists() else {}
    std, nf = set(v9.get("STANDARD_FORMAT_LEAGUES", ())), set(v9.get("NEW_FORMAT_LEAGUES", ()))
    enabled, paper = set(v9.get("ENABLED_LEAGUES", ())), set(v9.get("PAPER_LEAGUES", ()))
    af_only, fd = set(v9.get("API_FOOTBALL_ONLY_LEAGUES", ())), v9.get("FOOTBALL_DATA_LEAGUES", {})
    ids, odds_keys = v9.get("API_FOOTBALL_IDS", {}), v9.get("ODDS_API_SPORT_KEYS", {})
    props = pm.get("PROP_LEAGUES", {})
    leagues = sorted(std | nf | enabled | paper | af_only | set(ids) | set(odds_keys) | set(props))
    rows = []
    for lg in leagues:
        fmt = "standard" if lg in std else "new_format" if lg in nf else None
        deploy = ("PAPER" if lg in paper else "LIVE" if lg in enabled and fmt else
                  "TRAINING_ONLY" if fmt else "PLAYER_ONLY" if lg in props else "UNSUPPORTED")
        rows.append({
            "league_name": lg, "api_football_id": ids.get(lg) if lg in ids else props.get(lg),
            "odds_api_key": odds_keys.get(lg), "football_data_code": fd.get(lg),
            "season_type": "calendar_year" if lg in nf else "split_season" if lg in std else None,
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
            div.append(f"{lg}: live league with no OddsAPI sport key")
        if lg in paper and lg not in enabled:
            div.append(f"{lg}: PAPER but not ENABLED (would stop collection)")
    return {"generated_from": "v9 config.py + player_model/config.py (ast, read-only) + scout lifecycle",
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
