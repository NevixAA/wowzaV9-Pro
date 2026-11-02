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
from src import quality as q
from src.data import entities as ent
from src.data import watermarks as wm
from src.data.v9_source import fetch_csv, num, v9_model_version

# Watermarks are only committed AFTER the caller has written the rows, so a crash between
# read and write re-imports a little rather than skipping data permanently.
_PENDING_MARKS: dict[str, str] = {}



# The side each v9 side-ledger market is bet on; used only when the row has no side of its own.
SIDE_MARKET_SIDE = {"BTTS": "YES", "OVER15": "OVER", "OVER35": "OVER"}


def _blank_to_na(v) -> pd.Series:
    """Strings with blanks as NaN - a blank tier/result/side is MISSING, never a stand-in value."""
    v = v if isinstance(v, pd.Series) else pd.Series(v)
    return v.astype(object).where(v.notna() & v.astype(str).str.strip().ne(""))

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
    # Resolved once per import, not per market: it reads 12 MB off disk and the answer is
    # identical for every row of this run.
    _mv = v9_model_version()
    if not _mv:
        print("[import] v9 model version UNAVAILABLE — model_snapshots will carry "
              "MODEL_VERSION_UNKNOWN. Set V9_LOCAL to a wowza-betting checkout.")
    else:
        print(f"[import] frozen v9 model version {_mv['model_content_sha']} "
              f"({_mv['n_model_files']} files, {_mv['model_bytes']/1024/1024:.1f} MB)")

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
        # THE STABLE VERSION, beside v9's own. `model_sha` above is v9's stamp and it is not a
        # version: it hashes size+mtime, and CI checkout resets mtime, so it changed 95 times
        # while the models changed 4 times. Kept verbatim for lineage; `model_content_sha` is
        # what a query should group by. See v9_source.v9_model_version.
        blk["model_content_sha"] = _mv.get("model_content_sha", "")
        if "generated_at" in d.columns:
            blk["observed_at"] = d["generated_at"].replace("", pd.NA)
        blk["quality_flags"] = d["entity_unresolved"].map(
            lambda u: "ENTITY_UNRESOLVED" if u else "")
        # Flagged on the CONTENT sha, not v9's stamp. A row whose v9 stamp is present but whose
        # content sha is missing still has no usable version, and the old test would have called
        # it versioned.
        _no_version = (blk["model_content_sha"].astype(str).str.strip()
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
    # A blank tier stays blank and is FLAGGED (it used to be recorded as AVOID, a decision v9
    # never made). v9 writes AVOID itself when it declines a fixture.
    sg["signal_tier"] = _blank_to_na(d.get("signal_tier", pd.Series(index=d.index, dtype=object)))
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
    sg["quality_flags"] = q.add_flag(sg["quality_flags"], sg["signal_tier"].isna(), "TIER_MISSING")
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
        # Flags ACCUMULATE via quality.add_flag. The two lines here were previously bare
        # assignments, so a row that was both entity-unresolved AND market-invalid reported only
        # whichever check ran last — the second overwrote the first.
        blk["quality_flags"] = ""
        blk["quality_flags"] = q.add_flag(blk["quality_flags"], blk["odds"].isna(),
                                          "MARKET_MAPPING_INVALID")
        blk["quality_flags"] = q.add_flag(blk["quality_flags"], blk["away_team"] == "",
                                          "ENTITY_UNRESOLVED")
        # First-half BTTS captured as full-match (parser fixed 2026-08-23; 271 historical rows).
        # FLAGGED, not dropped — Pro stores dirty rows and lets the reader choose a level.
        blk = q.flag_btts_first_half(blk)
        frames.append(blk)
    if not frames:
        return []
    return [("market_snapshots", pd.concat(frames, ignore_index=True))]


_BOOK_ODDS_FILE = "output/book_odds_snapshots.csv"


def from_book_odds() -> list[tuple[str, pd.DataFrame]]:
    """v9's PER-BOOKMAKER quotes -> the `book_odds_snapshots` canonical table.

    WHY THIS EXISTS. `market_snapshots.bookmaker` holds two synthetic values — `v9_selected_best`
    and `v9_capture` — because v9 gives Pro the price it CHOSE, not the book that offered it. So
    three questions were unanswerable from the canonical store: two-sided de-vigging against a
    named book, multi-book consensus, and which book moves first. v9 has been committing the
    per-book data all along in output/book_odds_snapshots.csv; nothing imported it.

    Incremental on `snapshot_ts`, the same contract as from_odds_histories: the file only grows,
    and a full re-import would add ~132k duplicate rows per run.

    NOTHING IS DROPPED FOR BEING INCOMPLETE. A book quoting only one side is kept and flagged
    MISSING_OPPOSITE_SIDE — 19.9% of (snapshot, match, market, book) groups are one-sided, and
    which books those are is itself a research finding about book behaviour. Pro stores dirty rows
    and lets the reader choose a strictness level; discarding them here would silently answer a
    question the reader should be asking.
    """
    raw = fetch_csv(_BOOK_ODDS_FILE, required=False)
    if raw.empty or "match" not in raw.columns or "bookmaker" not in raw.columns:
        return []

    mark = wm.get(_BOOK_ODDS_FILE)
    if "snapshot_ts" in raw.columns:
        new_high = str(raw["snapshot_ts"].max() or "")
        if mark:
            raw = raw[raw["snapshot_ts"].astype(str) > mark]
        if raw.empty:
            print(f"[import] {_BOOK_ODDS_FILE}: nothing new past {mark}")
            return []
        print(f"[import] {_BOOK_ODDS_FILE}: {len(raw):,} new row(s) past "
              f"{mark or '(first import)'}")
        _PENDING_MARKS[_BOOK_ODDS_FILE] = new_high

    home, away = ent.split_match(raw["match"])
    blk = pd.DataFrame({
        "league": raw.get("league", ""),
        "match_date": raw["match_date"].astype(str).str[:10],
        "home_team": home,
        "away_team": away,
        "kickoff_utc": raw.get("kickoff_utc", ""),
        "market": raw.get("market", ""),
        "side": raw.get("side", ""),
        # The whole reason for the table: the REAL book name, as the provider gave it.
        "bookmaker": raw["bookmaker"].astype(str),
        "odds": num(raw["odds"]),
        "odds_source": "REAL",
        "snapshot_ts": raw.get("snapshot_ts", ""),
    })
    blk = ent.add_fixture_key(blk)
    blk["odds_band"] = blk["odds"].map(lambda v: cfg.band_label(v, cfg.ODDS_BANDS))

    # Minutes to kickoff, so the horizon question can be asked of this table directly rather
    # than by re-joining fixtures every time.
    _ko = pd.to_datetime(blk["kickoff_utc"], errors="coerce", utc=True)
    _ts = pd.to_datetime(blk["snapshot_ts"], errors="coerce", utc=True)
    blk["minutes_to_kickoff"] = ((_ko - _ts).dt.total_seconds() / 60.0).round(1)
    # A post-kickoff quote is NOT a pre-match price and must never be used as a close.
    blk["is_post_kickoff"] = blk["minutes_to_kickoff"] < 0

    blk["quality_flags"] = ""
    blk["quality_flags"] = q.add_flag(blk["quality_flags"], blk["odds"].isna(),
                                      "MARKET_MAPPING_INVALID")
    blk["quality_flags"] = q.add_flag(blk["quality_flags"], blk["away_team"] == "",
                                      "ENTITY_UNRESOLVED")
    # One-sided quotes, flagged per (snapshot, fixture, market, book) rather than per row: the
    # property belongs to the group, and a row cannot tell on its own whether its partner exists.
    sides = blk.groupby(["snapshot_ts", "fixture_key", "market", "bookmaker"])["side"] \
               .transform("nunique")
    blk["quality_flags"] = q.add_flag(blk["quality_flags"], sides < 2, "MISSING_OPPOSITE_SIDE")
    return [("book_odds_snapshots", blk)]


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
            "result": _blank_to_na(d.get("result", pd.Series(index=d.index, dtype=object))),
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
        # A blank result is RESULT_MISSING (it used to be written as PENDING); any other value
        # that is not a known outcome is SETTLEMENT_UNCERTAIN.
        s["quality_flags"] = q.add_flag(s["quality_flags"], s["result"].isna(), "RESULT_MISSING")
        s["quality_flags"] = q.add_flag(
            s["quality_flags"],
            s["result"].notna() & ~s["result"].isin(["WIN", "LOSS", "VOID", "PENDING"]),
            "SETTLEMENT_UNCERTAIN")
        out.append(("settlements", s))

    side = fetch_csv("output/side_bets_ledger.csv", required=False)
    if not side.empty:
        d = ent.add_fixture_key(side.assign(
            match_date=side["match_date"].astype(str).str[:10]))
        _mkt = d.get("market", "").astype(str).str.upper()
        # The row's own side when v9 wrote one, else the side its market is bet on (BTTS YES,
        # Over 1.5 / 3.5 OVER). An unknown market keeps a blank side and is flagged - it used to
        # become "OVER" whatever the market was.
        _own = _blank_to_na(d.get("side", pd.Series(index=d.index, dtype=object))).str.upper()
        _side = _own.where(_own.notna(), _mkt.map(SIDE_MARKET_SIDE))
        _res = _blank_to_na(d.get("result", pd.Series(index=d.index, dtype=object)))
        _flags = q.add_flag(pd.Series("", index=d.index), _side.isna(), "SIDE_UNKNOWN")
        _flags = q.add_flag(_flags, _res.isna(), "RESULT_MISSING")
        out.append(("settlements", pd.DataFrame({
            "fixture_key": d["fixture_key"],
            "league": d.get("league", ""),
            "match_date": d["match_date"],
            "market": _mkt,
            # SIDE DERIVED FROM THE MARKET, not hard-coded to "OVER". BTTS resolves YES/NO and
            # was being recorded as OVER, which is not a side that market has. v9's ledger
            # leaves the column blank for side markets because each path only ever produces one
            # side, so the value has to be reconstructed here rather than copied.
            "side": _side,
            # THE COLUMN THAT WAS MISSING, AND WHAT IT COST.
            #
            # This frame omitted edge_pct entirely while the main-market frame above carries it.
            # src/validation/threshold_curves.py::load() drops rows whose edge_pct is NaN, so
            # EVERY side-market row was discarded at load and Pro's threshold verdicts covered
            # OU25 only -- 0% of 4,891 settled BTTS rows, 2,886 OVER15 and 158 OVER35 reached
            # any study.
            #
            # The cost was not academic. Argentina BTTS carries v9's entire staked book
            # (+33.95u of new-format's +21.12u), and it was the one cell with NO independent Pro
            # read -- so the cross-check that is supposed to catch a v9 result Pro disagrees
            # with could not look at the most important cell in the estate.
            "edge_pct": num(d.get("edge_pct", pd.Series(dtype=object))),
            "odds": num(d.get("odds", pd.Series(dtype=object))),
            # v9's side ledger has no `opening_odds` column — the opening price lives in
            # `mv_open`, written by the market-movement tracker. Reading the name the main
            # ledger uses gives an always-empty column; reading mv_open gives 185 of 448.
            # Thin, but a real number beats a column that is structurally NaN and looks like
            # missing data rather than a missing source.
            "opening_odds": num(d.get("opening_odds",
                                      d.get("mv_open", pd.Series(dtype=object)))),
            "closing_odds": num(d.get("closing_odds", pd.Series(dtype=object))),
            "clv_pct": num(d.get("clv_pct", pd.Series(dtype=object))),
            "signal_tier": d.get("signal_tier", ""),
            "result": _res,
            "pnl": num(d.get("pnl", pd.Series(dtype=object))),
            "model_type": d.get("model_type", ""),
            "notes": d.get("notes", ""),
            "quality_flags": _flags,
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
        "signal_tier": _blank_to_na(d.get("tier", pd.Series(index=d.index, dtype=object))),
        "result": _blank_to_na(d.get("result", pd.Series(index=d.index, dtype=object))),
        "pnl": num(d.get("pnl", pd.Series(dtype=object))),
        "deployment_mode": "PAPER",   # invariant 2: props are paper-only, permanently
    })
    # An unpriced prop was never EVALUATED — it is not a model rejection. v9 conflates the
    # two under AVOID, which is why AVOID counts there are uninterpretable.
    p["never_priced"] = p["market_odds"].isna() | (p["market_odds"] <= 1.0)
    p["quality_flags"] = p["never_priced"].map(lambda x: "MISSING_OPPOSITE_SIDE" if x else "")
    p["quality_flags"] = q.add_flag(p["quality_flags"], p["signal_tier"].isna(), "TIER_MISSING")
    p["quality_flags"] = q.add_flag(p["quality_flags"], p["result"].isna(), "RESULT_MISSING")
    p["odds_band"] = p["market_odds"].map(lambda v: cfg.band_label(v, cfg.ODDS_BANDS))
    return [("player_props", p)]


# ── clv + live scanner ───────────────────────────────────────────────────────

def clv_identity(raw: pd.DataFrame) -> pd.DataFrame:
    """(league, match_date, home_team, away_team) per clv_records row: the date v9 wrote into
    bet_id ('PLAYER|<match_date>|...'), the clubs from `match`, the league from v9's player_ledger
    row for the same date, match, player and market. NaN where not found (never guessed). Shared by
    the importer and the fixture_key v2 migration, which recovers pre-2026-11-01 clv rows."""
    home, away = ent.split_match(raw["match"])
    bid = raw.get("bet_id", pd.Series(index=raw.index, dtype=object)).astype(str).str.split("|")
    mdate = bid.str[1].where(bid.str[1].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False))
    league = pd.Series(pd.NA, index=raw.index, dtype=object)
    led = fetch_csv("output/player_ledger.csv", required=False)
    need = {"match_date", "league", "home_team", "away_team", "player_name", "market"}
    if not led.empty and need <= set(led.columns):
        k = ["match_date", "home_team", "away_team", "player_name", "market"]
        lk = led.assign(match_date=led["match_date"].astype(str).str[:10])[k + ["league"]]
        lk = lk.drop_duplicates(k + ["league"])
        lk = lk[~lk.duplicated(k, keep=False)]                # ambiguous league -> no match
        j = pd.DataFrame({"match_date": mdate, "home_team": home, "away_team": away,
                          "player_name": raw.get("player", ""), "market": raw.get("market", "")},
                         index=raw.index).reset_index().merge(lk, on=k, how="left").set_index("index")
        league = j["league"].reindex(raw.index)
    return pd.DataFrame({"league": league, "match_date": mdate, "home_team": home,
                         "away_team": away}, index=raw.index)


def from_clv() -> list[tuple[str, pd.DataFrame]]:
    """v9's CLV records. clv_records.csv has no league or match_date column (Data Truth
    2026-11-01: the key used to be built from an EMPTY league and date, so every meeting of two
    clubs in any season hashed to one fixture). The match date is the one v9 recorded in bet_id
    ('PLAYER|<match_date>|<player>|<market>'); the league comes from v9's player_ledger row for
    the same date, match, player and market (one v9 source, same strings). Where either is not
    found the row keeps NaN, no fixture_key, and a LEAGUE_MISSING / DATE_MISSING flag."""
    raw = fetch_csv("output/clv_records.csv", required=False)
    if raw.empty or "match" not in raw.columns:
        return []
    ident = clv_identity(raw)
    home, away = ident["home_team"], ident["away_team"]
    mdate, league = ident["match_date"], ident["league"]
    known = mdate.notna() & league.notna()
    keys = pd.Series(pd.NA, index=raw.index, dtype=object)
    if known.any():
        kd = ent.add_fixture_key(pd.DataFrame({
            "league": league[known], "match_date": mdate[known],
            "home_team": home[known], "away_team": away[known]}))
        keys[known] = kd["fixture_key"]
    flags = q.add_flag(pd.Series("", index=raw.index), mdate.isna(), "DATE_MISSING")
    flags = q.add_flag(flags, league.isna(), "LEAGUE_MISSING")
    if (~known).any():
        print(f"[import] clv: {int((~known).sum())} of {len(raw)} row(s) without a league or "
              f"date - stored with no fixture_key")
    return [("clv", pd.DataFrame({
        "fixture_key": keys,
        "league": league,
        "match_date": mdate,
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
        "quality_flags": flags,
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
        "result": _blank_to_na(raw.get("result", pd.Series(index=raw.index, dtype=object))),
        "deployment_mode": "RESEARCH",
        "quality_flags": q.add_flag(pd.Series("", index=raw.index),
                                    _blank_to_na(raw.get("result", pd.Series(index=raw.index, dtype=object))).isna(),
                                    "RESULT_MISSING"),
    }))]


IMPORTERS = {
    "predictions":    from_predictions,
    "odds_histories": from_odds_histories,
    # Registered AFTER odds_histories deliberately: both read snapshot-keyed v9 files and both
    # advance a watermark, and running the coarse one first means a failure here cannot stop the
    # market_snapshots import that existing research already depends on.
    "book_odds":      from_book_odds,
    "ledgers":        from_ledgers,
    "player_props":   from_player_props,
    "clv":            from_clv,
    "live_signals":   from_live_signals,
}
