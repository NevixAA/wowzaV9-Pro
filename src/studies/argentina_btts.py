"""Argentina BTTS: is the profit the model, the league, a bookmaker, or luck?

    python -m src.studies.argentina_btts

Three strategies on the SAME Argentina fixtures, plus the context needed to read them:

  A  Wowza-selected BTTS YES      the staked tips in v9's side ledger
  B  blind BTTS YES               every match with a Bet365 BTTS price, no model at all
  C  market-relative              YES only where one book's price beats the de-vigged
                                  consensus of the OTHER books (leave-one-out)

The incremental question is A - B: does selecting with the model beat simply backing YES? If the
matches Wowza did NOT pick were just as profitable, the profit is the league, not the model.

Frozen-hypothesis rule (H-BTTS-03/04): nothing here changes a threshold, a tier or a filter. It
adds CONTROL GROUPS around the unchanged hypothesis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.quality import BTTS_YES_MAX
from src.studies import common as C

LEAGUE = "Argentina Primera Division"
AF_ID = 128
TIP_START = "2026-08-10"          # PERFORMANCE_CUTOFF_DATE — the tip record starts here


def _results() -> pd.DataFrame:
    import json
    import requests
    rows = []
    for season in (2025, 2026):
        f = C.CACHE / f"argentina_fixtures_{season}.json"
        if f.exists():
            body = json.loads(f.read_text(encoding="utf-8"))
        else:
            body = requests.get("https://v3.football.api-sports.io/fixtures",
                                headers={"x-apisports-key": C._af_key()},
                                params={"league": AF_ID, "season": season}, timeout=60).json()
            C.CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(body), encoding="utf-8")
        for x in body["response"]:
            if x["fixture"]["status"]["short"] not in ("FT", "AET", "PEN"):
                continue
            rows.append({"league": LEAGUE, "season": season, "kickoff_utc": x["fixture"]["date"],
                         "match_date": x["fixture"]["date"][:10],
                         "home_team": x["teams"]["home"]["name"], "away_team": x["teams"]["away"]["name"],
                         "hg": x["goals"]["home"], "ag": x["goals"]["away"]})
    r = pd.DataFrame(rows)
    r["y"] = C.outcome("BTTS", r["hg"], r["ag"])
    return r


def _bet365_prices() -> pd.DataFrame:
    """Opening and last pre-kickoff Bet365 BTTS prices per match (v9's new-format capture)."""
    o = pd.read_csv(cfg.V9_LOCAL / "output" / "newformat_odds_history.csv", low_memory=False)
    o = o[o["league"].astype(str).eq(LEAGUE) & o["market"].isin(["btts_yes", "btts_no"])].copy()
    o["ts"] = pd.to_datetime(o["snapshot_ts"], utc=True, errors="coerce")
    o["ko"] = pd.to_datetime(o["kickoff_utc"], utc=True, errors="coerce")
    # Older rows carry no kickoff time; for those the snapshot DATE must be before the match date.
    md = pd.to_datetime(o["match_date"], utc=True, errors="coerce")
    o = o[(o["ko"].notna() & (o["ts"] < o["ko"])) | (o["ko"].isna() & (o["ts"] < md))]
    o = o.sort_values("ts")
    first = o.groupby(["match", "match_date", "market"])["odds"].first().unstack()
    last = o.groupby(["match", "match_date", "market"])["odds"].last().unstack()
    p = pd.DataFrame({"yes_open": first.get("btts_yes"), "no_open": first.get("btts_no"),
                      "yes_close": last.get("btts_yes"), "no_close": last.get("btts_no")}).reset_index()
    p[["home_team", "away_team"]] = p["match"].str.split(" vs ", n=1, expand=True)
    p["league"] = LEAGUE
    # FIRST-HALF CONTAMINATION. Some pairs are the "Both Teams Score - First Half" market captured
    # whole (YES 8.00 / NO 1.08): the margin looks normal, so an overround check cannot see it.
    # src/quality.BTTS_YES_MAX (3.20) is the measured gap between the two populations — clean
    # full-match YES never exceeded 2.97. Counted and dropped, never silently kept.
    bad = (p["yes_open"] > BTTS_YES_MAX) | (p["yes_close"] > BTTS_YES_MAX)
    p.attrs["dropped_first_half"] = int(bad.sum())
    return p[~bad].copy()


def _roi(units: pd.Series, dates: pd.Series) -> dict:
    u = pd.to_numeric(units, errors="coerce").dropna()
    if u.empty:
        return {"n": 0}
    return {"n": int(len(u)), "units": round(float(u.sum()), 2), "roi": round(float(u.mean()), 4),
            "roi_ci90": C.block_ci(u, dates.loc[u.index])}


def _flat(y, odds):
    return np.where(np.asarray(y) == 1, np.asarray(odds, float) - 1, -1.0)


def run() -> dict:
    R = _results()
    P = _bet365_prices()
    dropped = P.attrs.get("dropped_first_half", 0)
    j = C.match_frames(P, R)
    P = P[j.notna()].copy()
    P["r"] = j[j.notna()].astype(int).to_numpy()
    D = P.join(R, on="r", rsuffix="_r")
    D["yes_fair_close"] = [C.power_devig(a, b) if pd.notna(a) and pd.notna(b) else np.nan
                           for a, b in zip(D["yes_close"], D["no_close"])]
    D["period"] = np.select([D["match_date_r"] >= TIP_START, D["season"] == 2026],
                            ["2026 since Aug 10 (tip period)", "2026 before Aug 10"], "2025")

    # ── A: Wowza's staked BTTS YES tips ─────────────────────────────────────────────────────
    led = pd.read_csv(cfg.V9_LOCAL / "output" / "side_bets_ledger.csv")
    led = led[led["league"].eq(LEAGUE) & led["market"].eq("btts") & led["result"].isin(["WIN", "LOSS"])
              & (pd.to_datetime(led["match_date"], errors="coerce") >= TIP_START)].copy()
    led["staked"] = led["signal_tier"].isin(["SNIPER", "MARKSMAN"])
    led = led.sort_values("generated_at").drop_duplicates(["match_date", "home_team", "away_team"], keep="first")
    lj = C.match_frames(led, D.reset_index(drop=True).rename(columns={"match_date_r": "md"}),
                        r_cols=("league", "md", "home_team_r", "away_team_r"))
    led["d_idx"] = lj.to_numpy()

    T = D[D["period"] == "2026 since Aug 10 (tip period)"].reset_index(drop=True)
    tipped = set(led.loc[led["staked"] & led["d_idx"].notna(), "d_idx"].astype(int))
    Dr = D.reset_index(drop=True)
    tip_keys = {(Dr.loc[i, "home_team_r"], Dr.loc[i, "match_date_r"]) for i in tipped}
    T["selected"] = [(h, d) in tip_keys for h, d in zip(T["home_team_r"], T["match_date_r"])]

    out = {"league": LEAGUE, "question": "is the Argentina BTTS profit the model, the league, a book, or luck?",
           "fixtures_with_bet365_btts_price": int(len(D)),
           "dropped_first_half_contaminated_prices": dropped,
           "unmatched_price_rows": int(j.isna().sum())}

    # League regime: realised BTTS rate vs what the price implied, by period
    reg = {}
    for per, g in D.groupby("period"):
        reg[per] = {"n": int(len(g)), "btts_rate": round(float(g["y"].mean()), 4),
                    "bet365_fair_yes_close": round(float(g["yes_fair_close"].mean()), 4),
                    "gap_pp": round(float((g["y"].mean() - g["yes_fair_close"].mean()) * 100), 1),
                    "blind_yes_open": _roi(pd.Series(_flat(g["y"], g["yes_open"]), index=g.index), g["match_date_r"]),
                    "blind_yes_close": _roi(pd.Series(_flat(g["y"], g["yes_close"]), index=g.index), g["match_date_r"])}
    out["regime_by_period"] = reg
    # full-season context for the rate alone (all finished matches, priced or not)
    out["btts_rate_all_matches"] = {str(s): {"n": int(len(g)), "rate": round(float(g["y"].mean()), 4)}
                                    for s, g in R.groupby("season")}
    R26 = R[R["match_date"] >= TIP_START]
    out["btts_rate_all_matches"]["2026 since Aug 10"] = {"n": int(len(R26)), "rate": round(float(R26["y"].mean()), 4)}

    # A, B and A-B on the SAME tip-period fixtures
    T["u_open"] = _flat(T["y"], T["yes_open"])
    a = T[T["selected"]]
    nb = T[~T["selected"]]
    out["tip_period"] = {
        "B_blind_yes_all": _roi(T["u_open"], T["match_date_r"]),
        "A_wowza_selected": _roi(a["u_open"], a["match_date_r"]),
        "not_selected": _roi(nb["u_open"], nb["match_date_r"]),
        "selected_btts_rate": round(float(a["y"].mean()), 4) if len(a) else None,
        "not_selected_btts_rate": round(float(nb["y"].mean()), 4) if len(nb) else None,
        "note": "all three at Bet365's OPENING BTTS YES price, so the comparison is like for like",
    }
    diff = []
    for _ in range(3000):
        days = T["match_date_r"].unique()
        pick = set(C.RNG.choice(days, len(days)))
        s = T[T["match_date_r"].isin(pick)]
        if s["selected"].any() and (~s["selected"]).any():
            diff.append(s.loc[s["selected"], "u_open"].mean() - s.loc[~s["selected"], "u_open"].mean())
    out["tip_period"]["A_minus_not_selected_roi"] = round(float(a["u_open"].mean() - nb["u_open"].mean()), 4) if len(a) and len(nb) else None
    out["tip_period"]["A_minus_not_selected_ci90"] = ([round(float(np.quantile(diff, .05)), 4),
                                                       round(float(np.quantile(diff, .95)), 4)] if diff else None)
    out["A_ledger_record"] = {
        "staked_tips": int(led["staked"].sum()), "matched_to_results": int(led.loc[led["staked"], "d_idx"].notna().sum()),
        **_roi(pd.Series(np.where(led.loc[led["staked"], "result"] == "WIN",
                                  led.loc[led["staked"], "odds"] - 1, -1.0), index=led[led["staked"]].index),
               led.loc[led["staked"], "match_date"])}

    # Model skill on every tip-period fixture: does Wowza's P(YES) add to Bet365's price?
    M = C.model_panel("BTTS")
    M = M[M["league"] == LEAGUE]
    mj = C.match_frames(M, T.rename(columns={"match_date_r": "md"}),
                        r_cols=("league", "md", "home_team_r", "away_team_r"))
    TM = T.join(pd.Series(M["model_prob"].to_numpy(), index=mj.to_numpy()).dropna().groupby(level=0).first()
                .rename("p_model"), how="inner")
    TM = TM.dropna(subset=["p_model", "yes_fair_close"])
    if len(TM) >= 20:
        b, cov = C.fit_logistic(np.column_stack([C.logit(TM["yes_fair_close"]), C.logit(TM["p_model"])]), TM["y"])
        out["model_vs_market"] = {
            "n": int(len(TM)), "rate": round(float(TM["y"].mean()), 4),
            "mean_p_model": round(float(TM["p_model"].mean()), 4),
            "mean_p_market": round(float(TM["yes_fair_close"].mean()), 4),
            "brier_model": round(float(C.brier(TM["p_model"], TM["y"]).mean()), 4),
            "brier_market": round(float(C.brier(TM["yes_fair_close"], TM["y"]).mean()), 4),
            "residual_coef_model": round(float(b[2]), 3), "residual_z": round(float(b[2] / np.sqrt(cov[2, 2])), 2)}

    # C: is one book systematically cheap on YES? (multi-book archive, leave-one-out consensus)
    out["C_market_relative"] = _book_test(R)
    return out


def _book_test(R: pd.DataFrame) -> dict:
    from src.data import season_store as store
    bo = store.read("book_odds_snapshots")
    bo = bo[(bo["league"] == LEAGUE) & (bo["market"] == "BTTS") & ~bo["is_post_kickoff"].astype(bool)]
    if bo.empty:
        return {"n_fixtures": 0}
    bo = bo.sort_values("snapshot_ts").drop_duplicates(["fixture_key", "bookmaker", "side"], keep="last")
    w = bo.pivot_table(index=["fixture_key", "bookmaker"], columns="side", values="odds", aggfunc="last").dropna().reset_index()
    w["p"] = [C.power_devig(a, b) for a, b in zip(w["YES"], w["NO"])]
    names = bo.drop_duplicates("fixture_key").set_index("fixture_key")[["league", "match_date", "home_team", "away_team"]]
    fx = names.loc[names.index.isin(w["fixture_key"])].reset_index()
    rj = C.match_frames(fx, R)
    fx["y"] = [R.loc[int(i), "y"] if pd.notna(i) else np.nan for i in rj]
    fx = fx.dropna(subset=["y"])
    w = w.merge(fx[["fixture_key", "y", "match_date"]], on="fixture_key")
    rows = []
    for fk, g in w.groupby("fixture_key"):
        for _, r in g.iterrows():
            others = g[g["bookmaker"] != r["bookmaker"]]["p"]
            if len(others) < 3:
                continue
            loo = float(others.median())
            rows.append({"fixture_key": fk, "book": r["bookmaker"], "y": r["y"], "date": r["match_date"],
                         "odds": r["YES"], "ev_vs_loo": loo * r["YES"] - 1})
    E = pd.DataFrame(rows)
    if E.empty:
        return {"n_fixtures": int(fx["fixture_key"].nunique())}
    E["u"] = _flat(E["y"], E["odds"])
    books = {}
    for bk, g in E.groupby("book"):
        if len(g) < 15:
            continue
        cheap = g[g["ev_vs_loo"] > 0]
        books[bk] = {"n": int(len(g)), "mean_ev_vs_others": round(float(g["ev_vs_loo"].mean()), 4),
                     "always_yes": _roi(g["u"], g["date"]),
                     "only_when_cheap": _roi(cheap["u"], cheap["date"])}
    best = E.sort_values("ev_vs_loo", ascending=False).drop_duplicates("fixture_key")
    pos = best[best["ev_vs_loo"] > 0]
    return {"n_fixtures": int(E["fixture_key"].nunique()),
            "best_price_when_above_consensus": _roi(pos["u"], pos["date"]),
            "by_book": dict(sorted(books.items(), key=lambda kv: -kv[1]["mean_ev_vs_others"]))}


if __name__ == "__main__":
    import json
    r = run()
    C.write("argentina_btts", r)
    print(json.dumps(r, indent=1, default=str)[:6000])
