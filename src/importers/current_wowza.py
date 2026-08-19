"""
Import v9's live outputs into the canonical season store.
=========================================================
Prompt 2 section 4. Legacy outputs remain the source of truth on v9's side; Pro normalises
them so downstream analytics do not depend on every legacy schema.

Two rules that shape every importer here:

* **Every evaluated fixture is stored** (section 5) — AVOID and NO_BET included. v9's
  `predictions.csv` is the only artifact that holds the full board, so it is the primary
  source. `bets.csv` and the ledgers hold only what cleared a threshold.
* **Nothing is dropped for being dirty** (section 3, section 16). A row that fails a check
  gets a `quality_flags` entry and is stored anyway.

`predictions.csv` is a CURRENT-STATE file: `predict` overwrites it every 5 minutes, so each
collector run captures one point on the model's path toward kickoff. Repeated captures of the
same fixture are all retained (section 7) — that is the whole point, and it is the only way
the T-7d/T-3d/T-1h horizons in section 6 ever come to exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.data import entities as ent
from src.data import watermarks as wm
from src.data.v9_source import fetch_csv, num

# Watermarks are only committed AFTER the caller has written the rows, so a crash between
# read and write re-imports a little rather than skipping data permanently.
_PENDING_MARKS: dict[str, str] = {}


def commit_watermarks() -> dict[str, str]:
    """Call once the rows are safely stored. Returns what was advanced."""
    done = dict(_PENDING_MARKS)
    for src, val in done.items():
        wm.advance(src, val)
    _PENDING_MARKS.clear()
    return done

# market label -> (model prob column, over odds column, under odds column)
_MARKETS = {
    "OU25":    ("p_over25",    "odds_over25", "odds_under25"),
    "OU15":    ("p_over15",    "odds_over15", None),
    "OU35":    ("p_over35",    "odds_over35", None),
    "BTTS":    ("p_btts",      "odds_btts",   None),
    "HT_OU05": ("p_ht_over05", None,          None),
    "HT_OU15": ("p_ht_over15", None,          None),
}

# Feature columns are everything in predictions.csv that is neither identity, model output,
# nor market price. Listing the exclusions rather than the features keeps this correct as v9
# adds features.
_NON_FEATURE = {
    # `match_date` as well as `date`: _base() renames one to the other, and omitting the
    # renamed form put it in the feature list AND the identity list, selecting it twice.
    "league", "date", "match_date", "kickoff_utc", "home_team", "away_team", "model_type",
    "bet", "bet_stake", "best_edge", "best_side", "signal_tier", "no_form_data",
    "tier_over", "tier_under", "min_odds_blocked", "both_losing",
    "stake_over", "stake_under", "edge_over", "edge_under",
    "kelly_over", "kelly_under", "ev_over", "ev_under",
    "first_over_odds", "first_under_odds", "over_drift", "under_drift",
    "drift_signal", "odds_snapshots", "impl_prob_over", "impl_prob_under",
} | {c for m in _MARKETS.values() for c in m if c}


def _base(df: pd.DataFrame) -> pd.DataFrame:
    """Identity columns shared by every table derived from predictions.csv."""
    out = df.rename(columns={"date": "match_date"}).copy()
    out["match_date"] = out["match_date"].astype(str).str[:10]
    out = ent.add_fixture_key(out)
    out["entity_unresolved"] = ~(
        out["home_team"].map(lambda s: bool(ent.club_slug(s)))
        & out["away_team"].map(lambda s: bool(ent.club_slug(s)))
    )
    return out


# ── predictions.csv -> fixtures / model_snapshots / market_snapshots / features / signals ──

def from_predictions() -> list[tuple[str, pd.DataFrame]]:
    raw = fetch_csv("output/predictions.csv")
    if raw.empty:
        return []
    d = _base(raw)
    out: list[tuple[str, pd.DataFrame]] = []

    # fixtures — the board, every fixture evaluated
    out.append(("fixtures", d[[
        "fixture_key", "league", "match_date", "home_team", "away_team",
    ] + [c for c in ("kickoff_utc", "model_type") if c in d.columns]].drop_duplicates("fixture_key")))

    # model_snapshots — long by market. One row per fixture per market per capture.
    ms = []
    for market, (pcol, _o, _u) in _MARKETS.items():
        if pcol not in d.columns:
            continue
        blk = d[["fixture_key", "league", "match_date", "model_type"]].copy()
        blk["market"] = market
        blk["model_prob"] = num(d[pcol])
        blk["model_id"] = "v9_baseline"
        # v9 stamps generated_at / git_sha / model_sha into predictions.csv as of
        # 2026-08-17 (v9 src/provenance.py). Where present, use it: the snapshot then
        # carries the moment the board was PRODUCED rather than the moment Pro read it,
        # and MODEL_VERSION_UNKNOWN no longer applies. Rows predating that change keep
        # the flag, so old and new data stay distinguishable.
        blk["model_sha"] = d["model_sha"] if "model_sha" in d.columns else ""
        blk["git_sha"] = d["git_sha"] if "git_sha" in d.columns else ""
        if "generated_at" in d.columns:
            blk["observed_at"] = d["generated_at"].replace("", pd.NA)
        blk["quality_flags"] = d["entity_unresolved"].map(
            lambda u: "ENTITY_UNRESOLVED" if u else "")
        _no_version = (blk["model_sha"].astype(str).str.strip()
                       .isin(("", "unknown", "nan", "<NA>")))
        blk.loc[_no_version, "quality_flags"] = (
            blk.loc[_no_version, "quality_flags"] + "|MODEL_VERSION_UNKNOWN").str.strip("|")
        ms.append(blk[blk["model_prob"].notna()])
    if ms:
        out.append(("model_snapshots", pd.concat(ms, ignore_index=True)))

    # market_snapshots — the price that existed AT PREDICTION TIME. Distinct from the
    # odds-capture histories, which run on their own cadence.
    mk = []
    for market, (_p, ocol, ucol) in _MARKETS.items():
        for side, col in (("OVER", ocol), ("UNDER", ucol)):
            if not col or col not in d.columns:
                continue
            blk = d[["fixture_key", "league", "match_date"]].copy()
            blk["market"] = market
            blk["side"] = side
            blk["odds"] = num(d[col])
            blk["bookmaker"] = "v9_selected_best"
            blk["odds_source"] = "REAL"
            blk["book_count"] = pd.NA
            blk["odds_band"] = blk["odds"].map(lambda v: cfg.band_label(v, cfg.ODDS_BANDS))
            blk["quality_flags"] = ""
            # An Over with no Under cannot be honestly de-vigged (v11's rule).
            if ucol is None or ucol not in d.columns:
                blk["quality_flags"] = "MISSING_OPPOSITE_SIDE"
            mk.append(blk[blk["odds"].notna()])
    if mk:
        out.append(("market_snapshots", pd.concat(mk, ignore_index=True)))

    # feature_snapshots — the feature state at decision time (section 8). Wide is fine;
    # parquet stores it compactly and leakage research needs the values as they were.
    fcols = [c for c in d.columns if c not in _NON_FEATURE
             and c not in ("fixture_key", "entity_unresolved")]
    if fcols:
        fs = d[["fixture_key", "league", "match_date"] + fcols].copy()
        for c in fcols:
            fs[c] = num(fs[c]) if fs[c].dtype == object else fs[c]
        # v9 forces AVOID when rolling form is missing; record it as a feature-health fact.
        if "no_form_data" in d.columns:
            fs["feature_degraded"] = d["no_form_data"].astype(str).str.lower().isin(
                ("true", "1", "yes"))
        out.append(("feature_snapshots", fs))

    # signals — every evaluated fixture, whatever the tier (section 5)
    sg = d[["fixture_key", "league", "match_date"]].copy()
    sg["market"] = "OU25"
    sg["side"] = d.get("best_side", "")
    sg["bet"] = d.get("bet", "")
    sg["signal_tier"] = d.get("signal_tier", "").fillna("").replace("", "AVOID")
    sg["model_edge"] = num(d.get("best_edge", pd.Series(index=d.index, dtype=object)))
    sg["stake"] = num(d.get("bet_stake", pd.Series(index=d.index, dtype=object)))
    sg["drift_signal"] = d.get("drift_signal", "")
    sg["odds_snapshots"] = num(d.get("odds_snapshots", pd.Series(index=d.index, dtype=object)))
    # Prompt 1 section 15 / Prompt 2 section 12: tier is signal strength, mode is permission.
    # Pro never bets this season, so every imported signal is RESEARCH regardless of tier.
    sg["deployment_mode"] = cfg.DEFAULT_DEPLOYMENT_MODE
    sg["residual_band"] = sg["model_edge"].map(lambda v: cfg.band_label(v, cfg.RESIDUAL_BANDS))
    sg["quality_flags"] = d["entity_unresolved"].map(
        lambda u: "ENTITY_UNRESOLVED" if u else "")
    out.append(("signals", sg))
    return out


# ── odds capture histories -> market_snapshots ───────────────────────────────

_ODDS_FILES = {
    "output/standard_odds_history.csv":             "standard",
    "output/newformat_odds_dense.csv":              "new_format",
    "output/newformat_odds_history.csv":            "new_format",
    "output/standard_sidemarket_odds_history.csv":  "standard_side",
}


def from_odds_histories() -> list[tuple[str, pd.DataFrame]]:
    """Incremental: these files only ever grow, so import past the watermark.

    Re-importing them in full each run duplicated 39,685 rows per run — about 170M redundant
    rows over a season at 12 runs/day.
    """
    frames = []
    for path, track in _ODDS_FILES.items():
        raw = fetch_csv(path, required=False)
        if raw.empty or "match" not in raw.columns:
            continue

        mark = wm.get(path)
        if "snapshot_ts" in raw.columns:
            new_high = str(raw["snapshot_ts"].max() or "")
            if mark:
                raw = raw[raw["snapshot_ts"].astype(str) > mark]
            if raw.empty:
                print(f"[import] {path}: nothing new past {mark}")
                continue
            print(f"[import] {path}: {len(raw)} new row(s) past {mark or '(first import)'}")
            _PENDING_MARKS[path] = new_high

        home, away = ent.split_match(raw["match"])
        blk = pd.DataFrame({
            "league": raw.get("league", ""),
            "match_date": raw["match_date"].astype(str).str[:10],
            "home_team": home,
            "away_team": away,
            "market": raw.get("market", ""),
            "odds": num(raw["odds"]),
            "bookmaker": "v9_capture",
            "odds_source": "REAL",
            "track": track,
            "captured_at": raw.get("snapshot_ts", ""),
        })
        blk = ent.add_fixture_key(blk)
        blk["odds_band"] = blk["odds"].map(lambda v: cfg.band_label(v, cfg.ODDS_BANDS))
        blk["quality_flags"] = ""
        blk.loc[blk["odds"].isna(), "quality_flags"] = "MARKET_MAPPING_INVALID"
        blk.loc[blk["away_team"] == "", "quality_flags"] = "ENTITY_UNRESOLVED"
        frames.append(blk)
    if not frames:
        return []
    return [("market_snapshots", pd.concat(frames, ignore_index=True))]


# ── ledgers -> settlements ───────────────────────────────────────────────────

def from_ledgers() -> list[tuple[str, pd.DataFrame]]:
    out = []
    main = fetch_csv("output/bets_ledger.csv", required=False)
    if not main.empty:
        d = ent.add_fixture_key(main.assign(
            match_date=main["match_date"].astype(str).str[:10]))
        s = pd.DataFrame({
            "fixture_key": d["fixture_key"],
            "league": d.get("league", ""),
            "match_date": d["match_date"],
            "market": "OU25",
            "side": d.get("side", ""),
            # v9 defines edge = model_prob - 1/odds, so the model's probability AT BET TIME is
            # recoverable exactly: model_prob = edge + 1/odds. Carried because it is the ONLY
            # record of what the model thought about a fixture that has since settled.
            # predictions.csv is pre-match only and is overwritten every 5 minutes, so
            # model_snapshots can never contain a settled fixture until Pro has been running
            # long enough for its own snapshots to settle. Without this column the
            # market-relative test cannot start until then; with it, a year of history is
            # already usable.
            "edge_pct": num(d.get("edge_pct", pd.Series(dtype=object))),
            "odds": num(d.get("odds", pd.Series(dtype=object))),
            "opening_odds": num(d.get("opening_odds", pd.Series(dtype=object))),
            "closing_odds": num(d.get("closing_odds", pd.Series(dtype=object))),
            "clv_pct": num(d.get("clv_pct", pd.Series(dtype=object))),
            "signal_tier": d.get("signal_tier", ""),
            "result": d.get("result", "").fillna("").replace("", "PENDING"),
            "pnl": num(d.get("pnl", pd.Series(dtype=object))),
            "model_type": d.get("model_type", ""),
            "notes": d.get("notes", ""),
        })
        # p_model reconstructed from v9's own definition, side-aware: edge_pct is quoted for
        # the side that was TAKEN, so an UNDER row's edge is about UNDER. Converting both to
        # "probability that OVER happens" keeps one consistent target.
        _imp = 1.0 / s["odds"].where(s["odds"] > 1.0)
        _p_taken = (s["edge_pct"] / 100.0) + _imp
        s["p_model_over"] = np.where(s["side"].astype(str).str.upper() == "UNDER",
                                     1.0 - _p_taken, _p_taken)
        # A result we cannot verify is flagged, not assumed correct (section 16).
        s["quality_flags"] = ""
        s.loc[~s["result"].isin(["WIN", "LOSS", "VOID", "PENDING"]),
              "quality_flags"] = "SETTLEMENT_UNCERTAIN"
        out.append(("settlements", s))

    side = fetch_csv("output/side_bets_ledger.csv", required=False)
    if not side.empty:
        d = ent.add_fixture_key(side.assign(
            match_date=side["match_date"].astype(str).str[:10]))
        out.append(("settlements", pd.DataFrame({
            "fixture_key": d["fixture_key"],
            "league": d.get("league", ""),
            "match_date": d["match_date"],
            "market": d.get("market", "").str.upper(),
            "side": "OVER",
            "odds": num(d.get("odds", pd.Series(dtype=object))),
            "closing_odds": num(d.get("closing_odds", pd.Series(dtype=object))),
            "clv_pct": num(d.get("clv_pct", pd.Series(dtype=object))),
            "signal_tier": d.get("signal_tier", ""),
            "result": d.get("result", "").fillna("").replace("", "PENDING"),
            "pnl": num(d.get("pnl", pd.Series(dtype=object))),
            "model_type": d.get("model_type", ""),
            "quality_flags": "",
        })))
    return out


# ── player props ─────────────────────────────────────────────────────────────

def from_player_props() -> list[tuple[str, pd.DataFrame]]:
    raw = fetch_csv("output/player_ledger.csv", required=False)
    if raw.empty:
        return []
    d = ent.add_fixture_key(raw.assign(match_date=raw["match_date"].astype(str).str[:10]))
    p = pd.DataFrame({
        "fixture_key": d["fixture_key"],
        "league": d.get("league", ""),
        "match_date": d["match_date"],
        "player_name": d.get("player_name", ""),
        "team": d.get("team", ""),
        "position": d.get("position", ""),
        "market": d.get("market", ""),
        "model_prob": num(d.get("model_prob", pd.Series(dtype=object))),
        "market_odds": num(d.get("market_odds", pd.Series(dtype=object))),
        "signal_tier": d.get("tier", "").fillna("").replace("", "AVOID"),
        "result": d.get("result", "").fillna("").replace("", "PENDING"),
        "pnl": num(d.get("pnl", pd.Series(dtype=object))),
        "deployment_mode": "PAPER",   # invariant 2: props are paper-only, permanently
    })
    # An unpriced prop was never EVALUATED — it is not a model rejection. v9 conflates the
    # two under AVOID, which is why AVOID counts there are uninterpretable.
    p["never_priced"] = p["market_odds"].isna() | (p["market_odds"] <= 1.0)
    p["quality_flags"] = p["never_priced"].map(lambda x: "MISSING_OPPOSITE_SIDE" if x else "")
    p["odds_band"] = p["market_odds"].map(lambda v: cfg.band_label(v, cfg.ODDS_BANDS))
    return [("player_props", p)]


# ── clv + live scanner ───────────────────────────────────────────────────────

def from_clv() -> list[tuple[str, pd.DataFrame]]:
    raw = fetch_csv("output/clv_records.csv", required=False)
    if raw.empty or "match" not in raw.columns:
        return []
    home, away = ent.split_match(raw["match"])
    d = ent.add_fixture_key(pd.DataFrame({
        "league": "", "match_date": "", "home_team": home, "away_team": away}))
    return [("clv", pd.DataFrame({
        "fixture_key": d["fixture_key"],
        "match_date": "",
        "market": raw.get("market", ""),
        "player": raw.get("player", ""),
        "side": raw.get("side", ""),
        "odds_bet": num(raw.get("odds_bet", pd.Series(dtype=object))),
        "odds_close": num(raw.get("odds_close", pd.Series(dtype=object))),
        "p_bet_novig": num(raw.get("p_bet_novig", pd.Series(dtype=object))),
        "p_close_novig": num(raw.get("p_close_novig", pd.Series(dtype=object))),
        "clv_pct": num(raw.get("clv_pct", pd.Series(dtype=object))),
        "result": raw.get("result", ""),
        "ts_bet": raw.get("ts_bet", ""),
        "quality_flags": "",
    }))]


def from_live_signals() -> list[tuple[str, pd.DataFrame]]:
    raw = fetch_csv("output/live_signals_history.csv", required=False)
    if raw.empty or "match" not in raw.columns:
        return []
    home, away = ent.split_match(raw["match"])
    d = pd.DataFrame({
        "league": raw.get("league", ""),
        "match_date": raw.get("date", "").astype(str).str[:10],
        "home_team": home, "away_team": away,
    })
    d = ent.add_fixture_key(d)
    return [("live_signals", pd.DataFrame({
        "fixture_key": d["fixture_key"],
        "league": d["league"],
        "match_date": d["match_date"],
        "score": raw.get("score", ""),
        "elapsed_mins": num(raw.get("elapsed_mins", pd.Series(dtype=object))),
        "signal_type": raw.get("signal_type", ""),
        "bet": raw.get("bet", ""),
        "live_p_over": num(raw.get("live_p_over", pd.Series(dtype=object))),
        "pre_p_over": num(raw.get("pre_p_over", pd.Series(dtype=object))),
        "result": raw.get("result", "").fillna("").replace("", "PENDING"),
        "deployment_mode": "RESEARCH",
        "quality_flags": "",
    }))]


IMPORTERS = {
    "predictions":    from_predictions,
    "odds_histories": from_odds_histories,
    "ledgers":        from_ledgers,
    "player_props":   from_player_props,
    "clv":            from_clv,
    "live_signals":   from_live_signals,
}
