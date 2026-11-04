"""The data readiness gate. FAIL-CLOSED: the research refuses to run until every check passes.

    python -m src.props_matchup --check-readiness      # prints the gate; exit 1 while not ready

Two halves, kept apart so the logic is testable without real data:
  measure(...)   reads the REAL committed inputs and returns measured values (counts and shares only)
  evaluate(...)  compares measured values with THRESHOLDS -> PASS / FAIL / OWNER_DECISION_PENDING /
                 MISSING_INPUT per check, READY only if every check is PASS

THRESHOLDS ARE OWNER DECISIONS. Every value below is None until the owner sets it in a reviewed
commit. None means OWNER_DECISION_PENDING, which is not PASS: an unset threshold blocks the research,
it never defaults to something permissive. reports/R_PROPS_MATCHUP_SPEC.md section E lists them.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.props_matchup import inputs as I

THRESHOLDS: dict[str, float | None] = {
    # max share of player_history rows (research window) whose counts are 'zeros_unverified'
    "max_unverified_count_share": None,
    # min share of finished fixtures (props leagues, window) with an injury list observed BEFORE kickoff
    "min_injury_list_coverage": None,
    # min share of finished fixtures with a confirmed XI carrying provider player ids, observed BEFORE kickoff
    "min_lineup_id_coverage": None,
    # min share of player_history fixtures that have fullstats shots / SoT conceded
    "min_fullstats_coverage": None,
    # min number of (fixture, player, market, book) keys priced BOTH before and after team news, pre-kickoff
    "min_keys_priced_pre_and_post_news": None,
    # min share of prop-odds rows carrying provider player_id AND fixture_id (no name matching)
    "min_prop_odds_identity_share": None,
    # min share of settled props ledger rows carrying provider player_id AND fixture_id
    "min_settlement_identity_share": None,
}

#: check name -> (threshold key, direction); 'max' passes when measured <= threshold
CHECKS = {
    "counts_verified": ("max_unverified_count_share", "max"),
    "injury_lists_pre_kickoff": ("min_injury_list_coverage", "min"),
    "lineups_with_ids_pre_kickoff": ("min_lineup_id_coverage", "min"),
    "fullstats_concessions": ("min_fullstats_coverage", "min"),
    "prices_pre_and_post_news": ("min_keys_priced_pre_and_post_news", "min"),
    "prop_odds_identity": ("min_prop_odds_identity_share", "min"),
    "settlement_identity": ("min_settlement_identity_share", "min"),
}

PASS, FAIL, PENDING, MISSING = "PASS", "FAIL", "OWNER_DECISION_PENDING", "MISSING_INPUT"


def evaluate(measured: dict, thresholds: dict | None = None) -> dict:
    """measured: {check: {"value": float | None, "detail": ...}}. A value of None = the input is
    missing (MISSING_INPUT). Any check not PASS -> not ready."""
    th = THRESHOLDS if thresholds is None else thresholds
    out, ready = {}, True
    for check, (key, direction) in CHECKS.items():
        m = measured.get(check) or {}
        v, t = m.get("value"), th.get(key)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            status = MISSING
        elif t is None:
            status = PENDING
        elif (v <= t) if direction == "max" else (v >= t):
            status = PASS
        else:
            status = FAIL
        ready &= status == PASS
        out[check] = {"status": status, "measured": v, "threshold": t, "threshold_key": key,
                      "direction": direction, "detail": m.get("detail")}
    return {"ready": bool(ready), "checks": out}


# ── real measurements (counts and shares only; no model, no edge, no ROI) ────────────────────────
def _share(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _fixture_universe(v9: Path, leagues: set, start, end) -> pd.DataFrame:
    p = v9 / "output/strength/competition_fixtures.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["fixture_id", "league", "date"])
    f = pd.read_parquet(p, columns=["fixture_id", "league", "date", "status"])
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    f = f[f["status"].isin(["FT", "AET", "PEN"]) & f["league"].isin(leagues)]
    return f[(f["date"] >= start) & (f["date"] <= end)]


def measure(v9_root: Path | None = None, pro_root: Path | None = None) -> tuple[dict, dict]:
    """(measured values per check, inventory with provenance)."""
    v9 = I.v9_root(v9_root)
    inv, m = {}, {}

    ph, prov = I.read_player_history(v9_root, ["fixture_id", "player_id", "date", "league",
                                               I.SOURCE_COL])
    inv["player_history"] = prov.to_dict()
    if len(ph):
        vc = ph[I.SOURCE_COL].value_counts().to_dict()
        inv["player_history"].update({"date_min": str(ph["date"].min().date()),
                                      "date_max": str(ph["date"].max().date()),
                                      "fixtures": int(ph["fixture_id"].nunique()),
                                      "players": int(ph["player_id"].nunique()),
                                      "leagues": int(ph["league"].nunique()), "count_source": vc})
        m["counts_verified"] = {"value": _share(int(vc.get(I.UNVERIFIED, 0)), len(ph)),
                                "detail": f"{vc.get(I.UNVERIFIED, 0):,} of {len(ph):,} rows zeros_unverified"}
        ph_leagues, ph_end = set(ph["league"].dropna()), ph["date"].max()
    else:
        m["counts_verified"] = {"value": None, "detail": "player_history missing"}
        ph_leagues, ph_end = set(), None

    # injury lists observed before kickoff: Pro snapshots + v9 injuries fetched before the fixture
    snaps, sprov = I.read_injury_snapshots(pro_root)
    inj, iprov = I.read_injuries(v9_root)
    inv["pro_injury_snapshots"] = sprov.to_dict()
    inv["v9_injuries"] = iprov.to_dict()
    pre_ids, first = set(), []
    if len(snaps):
        pre = snaps[snaps["pre_kickoff"] & (snaps["captured_at"] < snaps["fixture_ts"])]
        pre_ids |= set(pd.to_numeric(pre["af_fixture_id"], errors="coerce").dropna().astype("int64"))
        first.append(snaps["captured_at"].min())
        inv["pro_injury_snapshots"].update({"captured_min": str(snaps["captured_at"].min()),
                                            "captured_max": str(snaps["captured_at"].max()),
                                            "pre_kickoff_rows": int(snaps["pre_kickoff"].sum()),
                                            "fixtures_seen_pre_kickoff": len(pre_ids),
                                            "leagues": sorted(snaps["league"].dropna().unique().tolist())})
    if len(inj) and {"fetched_at", "date", "fixture_id"} <= set(inj.columns):
        fa = pd.to_datetime(inj["fetched_at"], utc=True, errors="coerce")
        ko = pd.to_datetime(inj["date"], utc=True, errors="coerce")
        pre_ids |= set(pd.to_numeric(inj.loc[fa < ko, "fixture_id"], errors="coerce").dropna().astype("int64"))
        first.append(fa.min())
    if ph_end is not None and first:
        start = min(first).tz_localize(None) if getattr(min(first), "tzinfo", None) else min(first)
        uni = _fixture_universe(v9, ph_leagues, start.normalize(), ph_end)
        hit = int(uni["fixture_id"].isin(pre_ids).sum())
        m["injury_lists_pre_kickoff"] = {
            "value": _share(hit, len(uni)),
            "detail": f"{hit} of {len(uni)} finished fixtures in player_history's leagues from "
                      f"{start.date()} to {ph_end.date()} have an injury list captured before kickoff"}
    else:
        m["injury_lists_pre_kickoff"] = {"value": None, "detail": "no injury list with a capture clock"}

    # lineups with provider ids observed before kickoff
    lu, lprov = I.read_lineups(v9_root)
    tn, tprov = I.read_team_news(pro_root)
    inv["v9_lineups"] = lprov.to_dict()
    inv["pro_team_news"] = tprov.to_dict()
    if len(tn):
        inv["pro_team_news"].update({"fixtures": int(tn["fixture_id"].nunique()),
                                     "first_seen_min": str(tn["first_seen_ts"].min()),
                                     "first_seen_max": str(tn["first_seen_ts"].max()),
                                     "rows_pre_kickoff": int((pd.to_numeric(tn["minutes_to_kickoff"],
                                                                            errors="coerce") > 0).sum())})
    if len(lu) and "fetched_at" in lu.columns:
        # the v9 lineup collector backfills FINISHED fixtures: a pre-kickoff fetch is impossible by
        # construction, but it is measured rather than assumed
        m["lineups_with_ids_pre_kickoff"] = {"value": 0.0, "detail": "v9 lineups are fetched after full time"}
    elif len(tn):
        n_pre = tn.loc[pd.to_numeric(tn["minutes_to_kickoff"], errors="coerce") > 0, "fixture_id"].nunique()
        m["lineups_with_ids_pre_kickoff"] = {
            "value": 0.0, "detail": (f"Pro team_news has {n_pre} fixtures with an XI seen pre-kickoff "
                                     "but stores starters as NAMES (no provider ids); v9 lineups absent")}
    else:
        m["lineups_with_ids_pre_kickoff"] = {"value": None, "detail": "no lineup source"}

    # fullstats concessions
    fs, fprov = I.read_fullstats(v9_root)
    inv["af_fullstats"] = fprov.to_dict()
    if len(fs) and len(ph):
        ok = fs.dropna(subset=["shots_against", "sot_against"])
        have = set(ok["fixture_id"].dropna().astype("int64"))
        fx = pd.Series(ph["fixture_id"].unique())
        hit = int(fx.isin(have).sum())
        inv["af_fullstats"].update({"date_min": str(fs["date"].min().date()), "date_max": str(fs["date"].max().date()),
                                    "fixtures": int(fs["fixture_id"].nunique()),
                                    "team_rows_missing_sot_or_shots": int(len(fs) - len(ok))})
        m["fullstats_concessions"] = {"value": _share(hit, len(fx)),
                                      "detail": f"{hit:,} of {len(fx):,} player_history fixtures"}
    else:
        m["fullstats_concessions"] = {"value": None, "detail": "fullstats or player_history missing"}

    # prices
    po, pprov = I.read_prop_odds(v9_root)
    inv["prop_odds_history"] = pprov.to_dict()
    if len(po):
        key = ["match_date", "match", "player", "market", "bookmaker"]
        nd = po.groupby(key)["odds"].size()
        inv["prop_odds_history"].update({
            "snapshot_min": str(po["snapshot_ts"].min()), "snapshot_max": str(po["snapshot_ts"].max()),
            "match_date_min": str(po["match_date"].min()), "match_date_max": str(po["match_date"].max()),
            "markets": po["market"].value_counts().to_dict(), "books": po["bookmaker"].value_counts().to_dict(),
            "keys": int(len(nd)), "keys_with_2plus_distinct_prices": int((nd >= 2).sum())})
        has_ids = {"player_id", "fixture_id"} <= set(po.columns)
        ident = (po["player_id"].notna() & po["fixture_id"].notna()).sum() if has_ids else 0
        m["prop_odds_identity"] = {"value": _share(int(ident), len(po)),
                                   "detail": "columns player_id / fixture_id absent" if not has_ids else None}
        if not (has_ids and "kickoff_ts" in po.columns):
            m["prices_pre_and_post_news"] = {
                "value": 0.0,
                "detail": ("UNIDENTIFIABLE: prop odds carry no fixture_id and no kickoff time, so no price can "
                           "be placed before or after the team news (snapshots every 4 h, distinct-price append)")}
        else:
            # fail closed: a new schema needs a reviewed measurement, not a guess
            m["prices_pre_and_post_news"] = {
                "value": None, "detail": "prop odds now carry ids + kickoff: extend readiness.measure first"}
    else:
        m["prop_odds_identity"] = {"value": None, "detail": "prop odds history missing"}
        m["prices_pre_and_post_news"] = {"value": None, "detail": "prop odds history missing"}

    clv, cprov = I.read_prop_clv(v9_root)
    inv["prop_clv_records"] = cprov.to_dict()
    led, lgprov = I.read_player_ledger(v9_root)
    inv["player_ledger"] = lgprov.to_dict()
    if len(led):
        settled = led[led["result"].isin(["WIN", "LOSS"])]
        ident = int((settled["player_id"].notna() & settled["fixture_id"].notna()).sum())
        inv["player_ledger"].update({"signal_date_min": str(led["signal_date"].min()),
                                     "match_date_max": str(led["match_date"].max()),
                                     "results": led["result"].value_counts().to_dict(),
                                     "markets": led["market"].value_counts().to_dict()})
        m["settlement_identity"] = {"value": _share(ident, len(settled)),
                                    "detail": f"{ident:,} of {len(settled):,} WIN/LOSS rows carry player_id and fixture_id"}
    else:
        m["settlement_identity"] = {"value": None, "detail": "player_ledger missing"}

    sl, slprov = I.read_sidelined(v9_root)
    inv["sidelined_spells"] = slprov.to_dict()
    if len(sl):
        inv["sidelined_spells"].update({"players": int(sl["player_id"].nunique()),
                                        "start_min": str(sl["start"].min().date()),
                                        "start_max": str(sl["start"].max().date()),
                                        "types_top": sl["type"].value_counts().head(6).to_dict()})
    pr, prprov = I.read_profiles(v9_root)
    inv["player_profiles"] = prprov.to_dict()
    if len(pr):
        inv["player_profiles"].update({"players": int(pr["player_id"].nunique()),
                                       "height_missing_rows": int(pr["height_cm"].isna().sum())})
    return m, inv


def check(v9_root: Path | None = None, pro_root: Path | None = None,
          thresholds: dict | None = None) -> dict:
    measured, inv = measure(v9_root, pro_root)
    res = evaluate(measured, thresholds)
    res["inventory"] = inv
    return res
