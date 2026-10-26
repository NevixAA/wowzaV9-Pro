"""Frame for the Standard repair benchmark: one row per Standard-league match, as-of features only.

SOURCES (all already on disk; nothing fetched):
  * v9's own training frame for the standard track, alias-deduplicated
    (experiments/ou_info_inputs_2026_10/v9_frame_dedup.parquet, built by src.studies.ou_info_inputs).
    Copied into experiments/standard_repair_2026_10/ so this study is self-contained.
  * football-data.co.uk PRE-MATCH prices from experiments/ou_info_inputs_2026_10/fd_raw/ — the
    columns WITHOUT the "C" (closing) infix: B365>2.5, P>2.5 (Pinnacle, absent from 2026/27),
    BFE>2.5 (Betfair exchange, from 2024/25), Avg>2.5, and the 1X2 equivalents. football-data
    records these on the Friday (weekend) / Tuesday (midweek) before kickoff: genuine pre-kickoff
    quotes, i.e. roughly when v9 freezes a tip. CLOSING prices are never used as an entry or anchor;
    they are read only to prove the pre-match columns are not secretly closing (audit).
  * v9's walk-forward probabilities, reproduced by v9's own trainer (v9_probe.py -> v9_wf.parquet).

KNOWN TRAPS HANDLED
  * The frame's odds_over25 is the CLOSING price on ~91% of rows (measured). Every odds-derived
    frame column (odds_*, implied_prob_*, bookmaker_overround) is excluded from candidate features.
    v9's reproduction keeps v9's own feature list unchanged (it trains on bookmaker_overround) — that
    is what production does, and it can only flatter v9, never the challengers.
  * There is NO historical two-sided BTTS or Over 1.5 price for standard leagues (odds_btts is one
    side on 15% of rows; odds_over15 on <1%). The historical BTTS/OU15 "market" is therefore the
    market's own goal expectation inverted from the pre-match 1X2 + O/U 2.5 prices (independent
    Poisson, see market_goal_split) and optionally recalibrated walk-forward. Real quoted BTTS/OU15
    prices exist only forward (Pro book_odds_snapshots, since 2026-08-19) and are used in forward.py.
  * League environment features use strictly-earlier DATES (same-day matches are never in each
    other's window).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

EXP = cfg.BASE_DIR / "experiments" / "standard_repair_2026_10"
FD_RAW = cfg.BASE_DIR / "experiments" / "ou_info_inputs_2026_10" / "fd_raw"
FD_CODES = {"Championship": "E1", "League One": "E2", "League Two": "E3", "National League": "EC",
            "Bundesliga 2": "D2", "Ligue 2": "F2", "La Liga 2": "SP2", "Serie B": "I2",
            "Greek Super League": "G1", "Portuguese Primeira Liga": "P1", "Scottish Championship": "SC1",
            "Scottish Premiership": "SC0", "Belgian First Division A": "B1", "Dutch Eredivisie": "N1",
            "Turkish Super Lig": "T1", "Scottish League One": "SC2", "Scottish League Two": "SC3"}
MARKETS = ("OU25", "BTTS", "OU15")
TARGET = {"OU25": "over25", "BTTS": "btts", "OU15": "over15"}
OU_BOOKS = {"AVG": ("Avg>2.5", "Avg<2.5"), "B365": ("B365>2.5", "B365<2.5"),
            "PIN": ("P>2.5", "P<2.5"), "BFE": ("BFE>2.5", "BFE<2.5")}
X12_BOOKS = {"AVG": ("AvgH", "AvgD", "AvgA"), "B365": ("B365H", "B365D", "B365A"), "PIN": ("PSH", "PSD", "PSA")}
ODDS_DERIVED = {"odds_over25", "odds_under25", "odds_btts", "odds_over15", "odds_over35",
                "implied_prob_over", "implied_prob_under", "bookmaker_overround", "p_over25_poisson_dc"}
ENV_N = 80                      # league matches in the rolling scoring-environment window
EPS = 1e-6


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sig(x):
    return 1 / (1 + np.exp(-np.asarray(x, float)))


# ── de-vig ────────────────────────────────────────────────────────────────────────────────────
def power_devig(o_a, o_b) -> np.ndarray:
    """Two-sided power de-vig, vectorised: find k with (1/a)^k + (1/b)^k = 1; returns P(side a).
    NaN when a price is missing, <=1, or the pair is an arbitrage (overround < 1) or > 1.25."""
    a = 1 / np.asarray(o_a, float)
    b = 1 / np.asarray(o_b, float)
    s = a + b
    ok = np.isfinite(s) & (np.asarray(o_a, float) > 1) & (np.asarray(o_b, float) > 1) & (s >= 1.0) & (s <= 1.25)
    lo, hi = np.full(len(a), 0.5), np.full(len(a), 3.0)
    aa, bb = np.where(ok, a, 0.5), np.where(ok, b, 0.5)
    for _ in range(60):
        k = (lo + hi) / 2
        big = aa ** k + bb ** k > 1
        lo, hi = np.where(big, k, lo), np.where(big, hi, k)
    return np.where(ok, aa ** ((lo + hi) / 2), np.nan)


def prop_devig(o_a, o_b) -> np.ndarray:
    a, b = 1 / np.asarray(o_a, float), 1 / np.asarray(o_b, float)
    s = a + b
    ok = np.isfinite(s) & (s >= 1.0) & (s <= 1.25)
    return np.where(ok, a / s, np.nan)


def prop_devig3(h, d, a):
    ih, id_, ia = (1 / np.asarray(x, float) for x in (h, d, a))
    s = ih + id_ + ia
    ok = np.isfinite(s) & (s >= 1.0) & (s <= 1.3)
    return [np.where(ok, x / s, np.nan) for x in (ih, id_, ia)]


# ── market goal expectation (for BTTS / Over 1.5, which have no historical quotes) ─────────────
def _pois_over(lam, line):
    """P(Poisson(lam) > line) for line 1.5 / 2.5."""
    lam = np.asarray(lam, float)
    e = np.exp(-lam)
    cdf = e * (1 + lam) if line == 1.5 else e * (1 + lam + lam ** 2 / 2)
    return 1 - cdf


def market_goal_split(p_over25, p_home, p_away):
    """Invert the market's de-vigged O/U 2.5 and 1X2 into (lambda_home, lambda_away) under independent
    Poisson: total lambda matches P(over 2.5) exactly; the home share matches P(home) - P(away).
    Returns (lh, la); NaN where an input is missing."""
    po = np.asarray(p_over25, float)
    ok = np.isfinite(po)
    lo, hi = np.full(len(po), 0.2), np.full(len(po), 8.0)
    tgt = np.where(ok, po, 0.5)
    for _ in range(60):
        m = (lo + hi) / 2
        big = _pois_over(m, 2.5) > tgt
        lo, hi = np.where(big, lo, m), np.where(big, m, hi)
    lam = (lo + hi) / 2
    d = np.asarray(p_home, float) - np.asarray(p_away, float)
    ok2 = ok & np.isfinite(d)
    d = np.where(ok2, d, 0.0)
    k = np.arange(11)
    from scipy.special import gammaln
    lfact = gammaln(k + 1)

    def h_minus_a(share):
        lh, la = lam * share, lam * (1 - share)
        ph = np.exp(k[None, :] * np.log(lh[:, None]) - lh[:, None] - lfact[None, :])
        pa = np.exp(k[None, :] * np.log(la[:, None]) - la[:, None] - lfact[None, :])
        joint = ph[:, :, None] * pa[:, None, :]
        tri = np.subtract.outer(k, k)
        return (joint * (tri > 0)).sum((1, 2)) - (joint * (tri < 0)).sum((1, 2))
    slo, shi = np.full(len(po), 0.03), np.full(len(po), 0.97)
    for _ in range(40):
        s = (slo + shi) / 2
        big = h_minus_a(s) > d
        slo, shi = np.where(big, slo, s), np.where(big, s, shi)
    s = (slo + shi) / 2
    lh, la = lam * s, lam * (1 - s)
    lh[~ok2], la[~ok2] = np.nan, np.nan
    return lh, la


def poisson_market_probs(lh, la) -> dict:
    lam = lh + la
    return {"OU25": _pois_over(lam, 2.5), "OU15": _pois_over(lam, 1.5),
            "BTTS": (1 - np.exp(-lh)) * (1 - np.exp(-la))}


# ── football-data pre-match prices ────────────────────────────────────────────────────────────
def fd_prices() -> pd.DataFrame:
    rows = []
    for league, code in FD_CODES.items():
        for f in sorted(FD_RAW.glob(f"{code}_*.csv")):
            d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
            if not {"Date", "HomeTeam", "AwayTeam"} <= set(d.columns):
                continue
            d = d.dropna(subset=["HomeTeam", "AwayTeam"])
            r = pd.DataFrame({"league": league, "home_team": d["HomeTeam"].astype(str).str.strip(),
                              "away_team": d["AwayTeam"].astype(str).str.strip(),
                              "date": pd.to_datetime(d["Date"], dayfirst=True, errors="coerce").dt.normalize()})
            for bk, (o, u) in OU_BOOKS.items():
                r[f"o_{bk}"] = pd.to_numeric(d.get(o), errors="coerce")
                r[f"u_{bk}"] = pd.to_numeric(d.get(u), errors="coerce")
            for bk, (h, x, a) in X12_BOOKS.items():
                for col, src in (("h", h), ("d", x), ("a", a)):
                    r[f"{col}_{bk}"] = pd.to_numeric(d.get(src), errors="coerce")
            r["close_o_AVG"] = pd.to_numeric(d.get("AvgC>2.5"), errors="coerce")
            r["close_u_AVG"] = pd.to_numeric(d.get("AvgC<2.5"), errors="coerce")
            rows.append(r)
    fd = pd.concat(rows, ignore_index=True).dropna(subset=["date"])
    return fd.drop_duplicates(["league", "date", "home_team", "away_team"])


# ── league scoring environment (as-of, strictly earlier dates) ─────────────────────────────────
def _asof_roll(df: pd.DataFrame, col: str, n: int = ENV_N, minp: int = 20) -> pd.Series:
    """Per league: mean of `col` over the previous n matches played on EARLIER dates."""
    out = pd.Series(np.nan, index=df.index)
    for _, g in df.sort_values(["date"]).groupby("league", sort=False):
        r = g[col].shift(1).rolling(n, min_periods=minp).mean()
        # same-date rows all take the value of the first row of that date (only earlier dates in it)
        r = r.groupby(g["date"]).transform("first")
        out.loc[g.index] = r
    return out


def build() -> tuple[pd.DataFrame, dict]:
    fr = pd.read_parquet(EXP / "v9_frame_dedup.parquet")
    fr = fr[fr["track"] == "standard"].copy()
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    fr = fr.drop_duplicates(["league", "date", "home_team", "away_team"])
    fd = fd_prices()
    d = fr.merge(fd, on=["league", "date", "home_team", "away_team"], how="left")
    audit = {"frame_rows_standard": int(len(fr)), "rows_with_prematch_price": int(d["o_AVG"].notna().sum())}

    # per-book de-vig, then consensus = median of the books quoting both sides
    for bk in OU_BOOKS:
        d[f"pm_OU25_{bk}_power"] = power_devig(d[f"o_{bk}"], d[f"u_{bk}"])
    d["pm_OU25_AVG_prop"] = prop_devig(d["o_AVG"], d["u_AVG"])
    d["pm_OU25_CONS_power"] = d[[f"pm_OU25_{bk}_power" for bk in OU_BOOKS]].median(axis=1, skipna=True)
    d["n_books_ou"] = d[[f"pm_OU25_{bk}_power" for bk in OU_BOOKS]].notna().sum(axis=1)
    d["book_dispersion"] = d[[f"pm_OU25_{bk}_power" for bk in OU_BOOKS]].std(axis=1, skipna=True)
    # closing consensus: EVALUATION ONLY (CLV, closing accuracy) - never an entry, anchor or feature
    d["pclose_OU25_AVG_power"] = power_devig(d["close_o_AVG"], d["close_u_AVG"])
    ph, pd_, pa = [], [], []
    for bk in X12_BOOKS:
        h, x, a = prop_devig3(d[f"h_{bk}"], d[f"d_{bk}"], d[f"a_{bk}"])
        ph.append(h), pd_.append(x), pa.append(a)
    d["p1x2_h"] = np.nanmedian(np.vstack(ph), axis=0)
    d["p1x2_d"] = np.nanmedian(np.vstack(pd_), axis=0)
    d["p1x2_a"] = np.nanmedian(np.vstack(pa), axis=0)
    lh, la = market_goal_split(d["pm_OU25_CONS_power"].to_numpy(), d["p1x2_h"].to_numpy(), d["p1x2_a"].to_numpy())
    d["mkt_lh"], d["mkt_la"] = lh, la
    pois = poisson_market_probs(lh, la)
    d["pm_BTTS_POIS"], d["pm_OU15_POIS"] = pois["BTTS"], pois["OU15"]
    d["pm_OU25_POIS"] = pois["OU25"]                       # == consensus by construction (sanity)

    # audit: the pre-match columns must not be the closing columns
    both = d.dropna(subset=["o_AVG", "close_o_AVG"])
    audit["prematch_equals_closing_share_AVG"] = round(float((both["o_AVG"] == both["close_o_AVG"]).mean()), 4)
    audit["frame_odds_over25_equals_closing_share"] = round(float((both["odds_over25"] == both["close_o_AVG"]).mean()), 4)
    audit["book_coverage_share"] = {bk: round(float(d[f"pm_OU25_{bk}_power"].notna().mean()), 3) for bk in OU_BOOKS}
    audit["pois_inversion_max_abs_err_ou25"] = round(float(np.nanmax(np.abs(d["pm_OU25_POIS"] - d["pm_OU25_CONS_power"]))), 6)

    # outcomes
    d["y_OU25"] = d["over25"].astype(float)
    d["y_BTTS"] = d["btts"].astype(float)
    d["y_OU15"] = d["over15"].astype(float)
    d["total_goals"] = d["home_goals"] + d["away_goals"]

    # league scoring environment, as-of. Realised and market-implied, and their gap (the market's
    # recent miss in this league): "dynamic league scoring environment".
    d["mkt_lam"] = d["mkt_lh"] + d["mkt_la"]
    d["env_goals"] = _asof_roll(d, "total_goals")
    d["env_over25"] = _asof_roll(d, "y_OU25")
    d["env_btts"] = _asof_roll(d, "y_BTTS")
    d["env_over15"] = _asof_roll(d, "y_OU15")
    d["env_mkt_lam"] = _asof_roll(d, "mkt_lam")
    d["env_gap_goals"] = d["env_goals"] - d["env_mkt_lam"]
    for m in MARKETS:
        pmcol = "pm_OU25_CONS_power" if m == "OU25" else f"pm_{m}_POIS"
        d[f"_res_{m}"] = d[f"y_{m}"] - d[pmcol]
        d[f"env_mktres_{m}"] = _asof_roll(d, f"_res_{m}")
        d = d.drop(columns=[f"_res_{m}"])

    # Poisson from team goal strength (form model, no prices)
    hs = d["home_season_goals_h"].fillna(d["home_scored_last5"])
    ac = d["away_season_conceded_a"].fillna(d["away_conceded_last5"])
    as_ = d["away_season_goals_a"].fillna(d["away_scored_last5"])
    hc = d["home_season_conceded_h"].fillna(d["home_conceded_last5"])
    d["form_lh"] = ((hs + ac) / 2).clip(0.2, 5)
    d["form_la"] = ((as_ + hc) / 2).clip(0.2, 5)
    fp = poisson_market_probs(d["form_lh"].to_numpy(), d["form_la"].to_numpy())
    for m in MARKETS:
        d[f"form_pois_{m}"] = fp[m]
    d["lh_gap"] = d["form_lh"] - d["mkt_lh"]
    d["la_gap"] = d["form_la"] - d["mkt_la"]

    # v9's walk-forward probabilities (v9's own trainer)
    wf = pd.read_parquet(EXP / "v9_wf.parquet")
    wf["date"] = pd.to_datetime(wf["date"]).dt.normalize()
    wf = wf.drop_duplicates(["league", "date", "home_team", "away_team"])
    d = d.merge(wf.rename(columns={"p_v9_over25": "p_v9_OU25", "p_v9_btts": "p_v9_BTTS", "p_v9_over15": "p_v9_OU15"})
                .drop(columns=["block"]), on=["league", "date", "home_team", "away_team"], how="left")
    audit["rows_with_v9_wf"] = int(d["p_v9_OU25"].notna().sum())

    d = d[d["pm_OU25_CONS_power"].notna() & d["mkt_lh"].notna()].copy()
    d["week"] = d["date"].dt.strftime("%G-W%V")              # matchday-week bootstrap block
    audit["final_rows"] = int(len(d))
    audit["date_range"] = [str(d["date"].min().date()), str(d["date"].max().date())]
    keep_feat = feature_lists(d)
    cols = (["date", "week", "league", "season", "home_team", "away_team", "home_goals", "away_goals",
             "o_AVG", "u_AVG", "close_o_AVG", "close_u_AVG", "pclose_OU25_AVG_power", "n_books_ou", "book_dispersion", "p1x2_h", "p1x2_d", "p1x2_a", "mkt_lh", "mkt_la"]
            + [c for c in d.columns if c.startswith(("pm_", "y_", "p_v9_", "env_", "form_pois_"))]
            + ["lh_gap", "la_gap", "form_lh", "form_la"] + keep_feat["FULL"])
    d = d[list(dict.fromkeys(cols))].sort_values("date").reset_index(drop=True)
    EXP.mkdir(parents=True, exist_ok=True)
    d.to_parquet(EXP / "frame.parquet", index=False)
    (EXP / "frame_audit.json").write_text(json.dumps(audit, indent=1), encoding="utf-8")
    return d, audit


V9_FEATS = ['home_scored_last5', 'away_scored_last5', 'home_conceded_last5', 'away_conceded_last5',
            'home_over25_last5', 'away_over25_last5', 'home_attack_str', 'away_attack_str', 'home_defense_str',
            'away_defense_str', 'home_advantage', 'away_home_adv_factor', 'home_rest_days', 'away_rest_days',
            'home_corners_pg_roll', 'away_corners_pg_roll', 'home_fouls_pg_roll', 'away_fouls_pg_roll',
            'combined_sot_ratio', 'home_xg_last5', 'away_xg_last5', 'home_insidebox_last5', 'away_insidebox_last5',
            'home_season_goals_h', 'away_season_goals_a', 'home_season_conceded_h', 'away_season_conceded_a',
            'home_cs_rate_h', 'away_cs_rate_a', 'home_ht_scored_last5', 'away_ht_scored_last5',
            'home_ht_conceded_last5', 'away_ht_conceded_last5', 'home_ht_attack_str', 'away_ht_attack_str',
            'combined_ht_goals_avg', 'home_ht_over05_rate', 'away_ht_over05_rate', 'home_ht_over15_rate',
            'away_ht_over15_rate', 'league_avg_goals']
SIMPLE = ['home_scored_last5', 'away_scored_last5', 'home_conceded_last5', 'away_conceded_last5',
          'home_attack_str', 'away_attack_str', 'home_defense_str', 'away_defense_str',
          'home_season_goals_h', 'away_season_goals_a', 'home_season_conceded_h', 'away_season_conceded_a',
          'league_avg_goals']
# stale / noisy shot, corner, foul, xG and half-time inputs (xG is NaN on most rows; Prediction Lab
# found xG dead and the HT labels partly fabricated)
NOISY = ['home_corners_pg_roll', 'away_corners_pg_roll', 'home_fouls_pg_roll', 'away_fouls_pg_roll',
         'combined_sot_ratio', 'home_xg_last5', 'away_xg_last5', 'home_insidebox_last5', 'away_insidebox_last5',
         'home_ht_scored_last5', 'away_ht_scored_last5', 'home_ht_conceded_last5', 'away_ht_conceded_last5',
         'home_ht_attack_str', 'away_ht_attack_str', 'combined_ht_goals_avg', 'home_ht_over05_rate',
         'away_ht_over05_rate', 'home_ht_over15_rate', 'away_ht_over15_rate']


def feature_lists(d: pd.DataFrame | None = None) -> dict:
    full = [c for c in V9_FEATS if c not in ODDS_DERIVED]
    return {"FULL": full, "SIMPLE": SIMPLE, "NO_NOISY": [c for c in full if c not in NOISY], "NOISY": NOISY}


def load() -> pd.DataFrame:
    return pd.read_parquet(EXP / "frame.parquet")
