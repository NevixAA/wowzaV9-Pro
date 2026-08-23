"""
The full CLV schema, with RAW preserved separately from CLEAN and no fabricated closes.
======================================================================================
    python -m src.market.clv_schema [--write]

WHAT WAS WRONG WITH THE CLV TABLE. 1,283 rows, and measured today:

    odds_close missing entirely            700  (54.6%)  -> no CLV is computable
    odds_close == odds_bet                 165  (12.9%)  -> clv_pct exactly 0.0
    genuinely non-zero clv_pct             418
    p_bet_novig / p_close_novig populated    0            -> never written, always NaN
    match_date populated                     0            -> no kickoff, so no horizon
    every single row is a PLAYER PROP (goals/sot/cards/assists) — no team market at all

The 165 rows are the dangerous ones. A "close" equal to the entry price is not a
measurement; it is the absence of one, recorded as 0.0% CLV. Averaged in, it drags the mean
toward zero and inflates n — and an n that includes non-measurements is what gates v11's BET
state. THE BRIEF IS EXPLICIT: never fabricate a closing price, NULL is preferable to a
contaminated one. So `clean_clv_pct` is NULL for all 865 of them, while `clv_pct` keeps whatever
v9 recorded, unaltered.

RAW AND CLEAN SIT SIDE BY SIDE, NEITHER OVERWRITING THE OTHER:

    clv_pct          exactly as v9 recorded it. Never edited. Auditing what v9 believed needs
                     this, and a filtered view cannot tell you how much it filtered.
    clean_clv_pct    NULL unless the close is evidenced. This is the one to average.
    clv_quality      why a row is or is not clean — one value, the first disqualifying reason.
    clv_source       where the close came from, so a number is traceable to an observation.

RECOVERING REAL CLOSES (the "improve coverage without fabricating" part). `player_props` holds
20,116 rows with `market_odds` on 8,034 and `observed_at` on all of them — a mean of 8.7
snapshots per (player, market). So for a prop whose close v9 never recorded, the last
PRE-KICKOFF observed price is a genuine close and can be recovered.

    KICKOFF IS ONLY KNOWN TO THE DAY. `match_date` is a date, not a timestamp, so:
      observed_at date  <  match_date   definitely pre-kickoff  -> clean close
      observed_at date  == match_date   cannot be PROVEN pre-kickoff -> usable at CLEAN,
                                        excluded from STRICT_CLEAN, flagged MISSING_KICKOFF
      observed_at date  >  match_date   post-kickoff -> never used

    Guessing in the permissive direction on match-day rows is exactly how post-kickoff prices
    manufactured the entire apparent CLV edge before 2026-08-10, so they are kept but marked.

THE UNIT TRAP — the reason a first pass reported a mean of -3.93% where v9 said -0.039%.

`clv_records.csv` stores `clv_pct` as a FRACTION despite the name: odds_bet 2.25 -> odds_close
2.00 is recorded as **0.125**, not 12.5. Meanwhile `bets_ledger.csv` stores the same-named column
as a PERCENT (values like 120.0 and -66.86 appear there). Two files, one column name, two units,
and nothing anywhere says so.

Two consequences worth knowing:

  * A recomputation that multiplies by 100 disagrees with the stored value by exactly 100x, which
    is what happened here and is easy to mistake for a data problem rather than a unit one.
  * `CLV_PLAUSIBLE_ABS = 25.0` applied to this table means "2500%", so the implausibility filter
    can NEVER fire on it. The filter is not wrong; it was written against the percent-valued
    ledger. It is simply inert here.

This module therefore keeps `clv_pct` byte-identical to what v9 stored (raw means raw, including
its units) and adds `clv_pct_normalised` and `clean_clv_pct` in **percent**, so every derived
number is in one stated unit.

OUTPUT is a derived artifact (`output/clv_enriched.csv`), NOT a new canonical table and NOT an
append to `clv`. Appending would duplicate 1,283 rows on every run in an append-only store, and
the enrichment is reproducible from `clv` + `player_props` at any time — so storing it as
canonical would create a second authority for a number that already has one.
"""
from __future__ import annotations

import argparse

import pandas as pd

from config import pro_config as cfg
from src import quality as q
from src.data import season_store as store

SCHEMA_COLS = [
    "fixture_key", "match_date", "market", "player", "side",
    "entry_ts", "entry_odds", "entry_fair_probability",
    "close_ts", "close_odds", "close_fair_probability",
    "minutes_close_before_kickoff",
    "clv_pct",              # RAW — byte-identical to v9, INCLUDING its fraction units
    "clv_pct_normalised",   # the same value in percent, so derived numbers share one unit
    "clean_clv_pct",        # percent. NULL unless the close is evidenced
    "clv_quality", "clv_source", "result",
]

# Quality verdicts, most severe first. One value per row: the FIRST disqualifying reason, so
# "why is this row not clean" has a single answer rather than a set to interpret.
Q_OK = "OK"
Q_NO_CLOSE = "NO_CLOSE"
Q_CLOSE_EQUALS_ENTRY = "CLOSE_EQUALS_ENTRY"
Q_IMPLAUSIBLE = "CLV_IMPLAUSIBLE"
Q_UNPROVEN_PREKICKOFF = "CLOSE_NOT_PROVEN_PRE_KICKOFF"


def _fair(odds) -> float:
    """Implied probability from decimal odds. No de-vig: the opposite side is not stored here.

    Named `fair` to match the brief's field name, but it is a SINGLE-SIDED implied probability
    and therefore carries the bookmaker's margin. Stated because averaging it as if it were
    de-vigged would bias every probability upward by roughly half the overround.
    """
    v = pd.to_numeric(odds, errors="coerce")
    return 1.0 / v


def _recover_closes() -> pd.DataFrame:
    """Last PROVABLY pre-kickoff prop price per (fixture, player, market), from player_props."""
    try:
        p = store.read("player_props")
    except Exception:
        return pd.DataFrame()
    if p is None or p.empty or "market_odds" not in p.columns:
        return pd.DataFrame()
    d = p.copy()
    d["_odds"] = pd.to_numeric(d["market_odds"], errors="coerce")
    d = d[d["_odds"].notna()]
    if d.empty:
        return pd.DataFrame()
    d["_obs"] = pd.to_datetime(d["observed_at"], errors="coerce", utc=True)
    d["_md"] = pd.to_datetime(d["match_date"], errors="coerce", utc=True)
    d = d[d["_obs"].notna() & d["_md"].notna()]
    # Post-kickoff-day rows are dropped outright; match-day rows are kept and marked.
    d = d[d["_obs"].dt.normalize() <= d["_md"].dt.normalize()]
    if d.empty:
        return pd.DataFrame()
    d["_same_day"] = d["_obs"].dt.normalize() == d["_md"].dt.normalize()
    d = d.sort_values("_obs")
    keys = [k for k in ("fixture_key", "player_name", "market") if k in d.columns]
    last = d.drop_duplicates(subset=keys, keep="last")
    return last[keys + ["_odds", "_obs", "_same_day", "_md"]].rename(
        columns={"_odds": "rec_close_odds", "_obs": "rec_close_ts",
                 "_same_day": "rec_same_day", "_md": "rec_match_date"})


def build(*, quiet: bool = False) -> pd.DataFrame:
    try:
        c = store.read("clv")
    except Exception as e:                                        # noqa: BLE001
        print(f"[clv_schema] clv unreadable: {e}")
        return pd.DataFrame()
    if c is None or c.empty:
        return pd.DataFrame()

    d = pd.DataFrame(index=c.index)
    d["fixture_key"] = c.get("fixture_key", "")
    d["match_date"] = c.get("match_date", "")
    d["market"] = c.get("market", "")
    d["player"] = c.get("player", "")
    d["side"] = c.get("side", "")
    d["entry_ts"] = c.get("ts_bet", "")
    d["entry_odds"] = pd.to_numeric(c.get("odds_bet"), errors="coerce")
    d["close_odds"] = pd.to_numeric(c.get("odds_close"), errors="coerce")
    d["close_ts"] = pd.NA
    d["clv_pct"] = pd.to_numeric(c.get("clv_pct"), errors="coerce")
    d["result"] = c.get("result", pd.NA)
    d["clv_source"] = pd.NA

    # v9 recorded a close where one exists.
    has_v9 = d["close_odds"].notna()
    d.loc[has_v9, "clv_source"] = "v9_clv_records"

    # ── recover missing closes from player_props ────────────────────────────
    # JOIN ON (player, market) BOUNDED BY ts_bet — NOT on fixture_key.
    #
    # `from_clv` builds fixture_key from league="" and match_date="", because clv_records.csv
    # carries neither. The resulting keys match NOTHING: measured overlap with player_props is
    # 0 of 57. Player names overlap 256/256 and the market vocabularies are identical, so the
    # join has to go through those instead.
    #
    # (player, market) alone is ambiguous across a season, so each clv row is matched to the
    # EARLIEST fixture whose match_date is on or after the bet timestamp — the next fixture the
    # player appeared in. That is the right inference and it is still an inference, so any row
    # resolved this way is marked CLOSE_NOT_PROVEN_PRE_KICKOFF and excluded from STRICT_CLEAN.
    rec = _recover_closes()
    n_recovered = 0
    d["_same_day"] = pd.NA
    d["_inferred_fixture"] = False
    if not rec.empty and {"player_name", "market"}.issubset(rec.columns):
        bet_t = pd.to_datetime(d["entry_ts"], errors="coerce", utc=True)
        idx = {}
        for (pl, mk), g in rec.groupby(["player_name", "market"], sort=False):
            idx[(str(pl), str(mk))] = g.sort_values("rec_match_date")
        for i in d.index[d["close_odds"].isna()]:
            g = idx.get((str(d.at[i, "player"]), str(d.at[i, "market"])))
            if g is None:
                continue
            t = bet_t.get(i)
            cand = g if pd.isna(t) else g[g["rec_match_date"] >= t.normalize()]
            if cand.empty:
                continue
            r = cand.iloc[0]
            d.at[i, "close_odds"] = r["rec_close_odds"]
            d.at[i, "close_ts"] = str(r["rec_close_ts"])
            d.at[i, "clv_source"] = "player_props_last_prekickoff"
            d.at[i, "_same_day"] = bool(r["rec_same_day"])
            d.at[i, "_inferred_fixture"] = True
            if not str(d.at[i, "match_date"]):
                d.at[i, "match_date"] = r["rec_match_date"].strftime("%Y-%m-%d")
            n_recovered += 1

    # v9's clv_pct is a fraction; express it in percent once, here, and use only that downstream.
    d["clv_pct_normalised"] = (d["clv_pct"] * 100.0).round(4)
    d["entry_fair_probability"] = _fair(d["entry_odds"])
    d["close_fair_probability"] = _fair(d["close_odds"])

    # Horizon. NULL where either timestamp is unknown — never estimated.
    et = pd.to_datetime(d["close_ts"], errors="coerce", utc=True)
    md = pd.to_datetime(d["match_date"], errors="coerce", utc=True)
    d["minutes_close_before_kickoff"] = ((md - et).dt.total_seconds() / 60.0).round(1)

    # ── quality, most severe first ──────────────────────────────────────────
    d["clv_quality"] = Q_OK
    d.loc[d["close_odds"].isna(), "clv_quality"] = Q_NO_CLOSE
    # CLOSE == ENTRY MEANS TWO DIFFERENT THINGS AND MUST NOT BE ONE VERDICT.
    #
    # For a close RECOVERED from player_props it is a real observation: the price genuinely did
    # not move between entry and the last pre-kickoff snapshot. Zero CLV is the correct answer
    # and the row is measured.
    #
    # For a close that came from v9's clv_records it is ambiguous. It may be a genuinely unmoved
    # price, or it may be the entry price written into the close field because no close was ever
    # observed — and 165 of 583 v9-sourced rows (28%) sitting at exactly equal odds is high for a
    # moving market. I cannot prove which, so it is marked UNVERIFIED rather than WRONG: usable
    # at CLEAN, excluded from STRICT_CLEAN. Asserting fabrication would be a claim the data does
    # not support, and treating it as a clean zero would let a non-measurement into the headline.
    # This is precisely what the STRICT_CLEAN level exists for.
    same = (d["close_odds"].notna() & d["entry_odds"].notna()
            & (d["close_odds"] == d["entry_odds"]))
    from_v9 = d["clv_source"].eq("v9_clv_records")
    d.loc[same & from_v9 & d["clv_quality"].eq(Q_OK), "clv_quality"] = Q_CLOSE_EQUALS_ENTRY
    # Compared in PERCENT, so the threshold means what it says. Against the raw fraction it
    # would mean 2500% and could never fire.
    impl = (d["clv_pct_normalised"].notna()
            & (d["clv_pct_normalised"].abs() > q.CLV_PLAUSIBLE_ABS))
    d.loc[impl & d["clv_quality"].eq(Q_OK), "clv_quality"] = Q_IMPLAUSIBLE
    unproven = ((d["_same_day"].fillna(False).astype(bool)
                 | d["_inferred_fixture"].fillna(False).astype(bool))
                & d["clv_quality"].eq(Q_OK))
    d.loc[unproven, "clv_quality"] = Q_UNPROVEN_PREKICKOFF

    # ── clean_clv_pct: recomputed from the evidenced pair, never copied from raw ────
    #
    # Recomputed rather than copied so a recovered close actually produces a NEW number. Copying
    # clv_pct would carry v9's 0.0 for every CLOSE_EQUALS_ENTRY row straight through the filter.
    d["clean_clv_pct"] = pd.NA
    ok = d["clv_quality"].isin((Q_OK, Q_UNPROVEN_PREKICKOFF, Q_CLOSE_EQUALS_ENTRY)) \
        & d["entry_odds"].notna() & d["close_odds"].notna() & d["close_odds"].gt(0)
    d.loc[ok, "clean_clv_pct"] = ((d.loc[ok, "entry_odds"] / d.loc[ok, "close_odds"] - 1.0)
                                  * 100.0).round(4)

    out = d[SCHEMA_COLS].copy()

    if not quiet:
        n = len(out)
        vc = out["clv_quality"].value_counts()
        clean = out["clean_clv_pct"].notna()
        strict = clean & out["clv_quality"].eq(Q_OK)
        print(f"[clv_schema] {n:,} rows")
        print(f"  closes recovered from player_props : {n_recovered:,}")
        for k, v in vc.items():
            print(f"    {k:32} {v:>6,} ({v / n:.1%})")
        print(f"  RAW      clv_pct present           : {out['clv_pct'].notna().sum():>6,}")
        print(f"  CLEAN    clean_clv_pct present      : {int(clean.sum()):>6,} "
              f"({clean.mean():.1%})")
        print(f"  STRICT   proven pre-kickoff close   : {int(strict.sum()):>6,} "
              f"({strict.mean():.1%})")
        if clean.any():
            cc = pd.to_numeric(out.loc[clean, "clean_clv_pct"], errors="coerce")
            rr = pd.to_numeric(out.loc[clean, "clv_pct_normalised"], errors="coerce")
            print(f"  mean CLEAN clv {cc.mean():+.4f}%   median {cc.median():+.4f}%   "
                  f"positive {(cc > 0).mean():.1%}")
            print(f"  same rows, v9 clv normalised to percent: mean {rr.mean():+.4f}% "
                  f"(agreement here confirms the unit fix)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the full CLV schema (raw + clean)")
    ap.add_argument("--write", action="store_true", help="write output/clv_enriched.csv")
    a = ap.parse_args()
    d = build()
    if d.empty:
        return 0
    if a.write:
        p = cfg.OUTPUT_DIR / "clv_enriched.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        d.to_csv(p, index=False)
        print(f"[clv_schema] written -> {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
