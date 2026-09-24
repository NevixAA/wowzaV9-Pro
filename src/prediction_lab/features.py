"""Pre-match features, grouped into FAMILIES so each one can be ablated in or out.

    python -m src.prediction_lab.features --audit

THE ONE RULE. Every value in this module answers "what could we have known the morning of the
match?" Nothing is computed from the fixture it describes. The code enforces that structurally
rather than by care: every rolling statistic is shifted one match back inside its own team's
history before any window is applied, and every league/season aggregate is built from STRICTLY
EARLIER DATES, not merely earlier rows.

WHY STRICTLY EARLIER DATES AND NOT EARLIER ROWS. A league plays five matches on a Saturday. An
expanding mean that only shifts by one ROW lets match 5 see matches 1-4 of the same afternoon --
results that had not happened when a real prediction would have been made. It is a small leak
that flatters every league-level feature, and it is invisible unless you look for it. So the
league aggregates here are cumulative to the PREVIOUS DATE.

FAMILIES, and what each is for:

    BASE        Calendar and league context. Includes the league's own prior scoring rate, which
                is the single most informative "free" feature and the thing a model must beat.
    FORM        Rolling goals for/against over 5 and 10 prior matches, plus an exponentially
                weighted version, plus the same split by home/away.
    SHOTS       Rolling shots for/against.
    SOT         Rolling shots on target for/against.
    CORNERS     Rolling corners for/against.
    DISCIPLINE  Rolling fouls and cards.
    STRENGTH    Attack and defence strength as a ratio to the league's own prior average, so a
                Bundesliga 2 side and an Argentine side are on the same scale.
    REST        Days since the team's last match, and matches played in the last 14 days.
    HT          Rolling first-half goals -- a tempo proxy that is not the same thing as full-time
                goals.
    H2H         Prior meetings between these two clubs.
    MARKET      De-vigged bookmaker probabilities. NOT PART OF THE FOOTBALL-ONLY EXPERIMENT.
                It exists only so the market ablation can add it and report the delta separately.

MISSING VALUES ARE LEFT AS NaN. A team with three matches of history has no 10-match average,
and a standard-format league has no card data at all. Writing a zero there would tell the model
"this team takes no shots", which is a confident lie; writing the column median inside the
feature builder would leak the future, because the median would be computed over the whole
dataset including the test period. HistGradientBoosting consumes NaN natively; the linear models
impute with a median fitted on TRAIN ONLY, in the model layer, where it belongs (rule 23).
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.prediction_lab import data as D

CALC_VERSION = "1.0.0"

# Windows used everywhere. 5 is "recent form", 10 is "this is roughly who they are".
WINDOWS = (5, 10)
EWM_HALFLIFE = 5.0

FAMILIES = ("BASE", "FORM", "SHOTS", "SOT", "CORNERS", "DISCIPLINE", "STRENGTH", "REST",
            "HT", "H2H", "EARLY", "MARKET")

# Football-only means every family except the market. Stated once, used by every experiment, so
# that "football only" cannot quietly start including a price.
#
# EARLY IS ALSO EXCLUDED BY DEFAULT, AND THAT IS A MEASURED DECISION, NOT AN OVERSIGHT.
# It was built to fix the season-start weak spot by labelling stale form (see _early_season).
# Tested on the season phase where the problem actually lives, it did NOT help: 0 of 4
# opening-20% cells improved significantly, and it significantly HURT four mid/late-season
# cells. Shipping it by default would cost accuracy across the calendar to fix nothing.
#
# The family is kept because the negative is worth keeping -- it says the season-start problem
# is NOT the model's ignorance of staleness. Telling a model its numbers are old cannot help
# when there is no fresher number to reach for. The gap is missing CURRENT-season information,
# not missing metadata about the old information. Opt in with FAMILIES if testing that further.
FOOTBALL_FAMILIES = tuple(f for f in FAMILIES if f not in ("MARKET", "EARLY"))


def _prior_mean_by_date(d: pd.DataFrame, group: str, value: str) -> pd.Series:
    """Mean of `value` within `group` over STRICTLY EARLIER DATES. Never the same day.

    Returns a Series aligned to d.index. This is the leak-safe version of
    `groupby(group)[value].expanding().mean().shift(1)`, which lets a match see other matches
    played the same afternoon.
    """
    t = d[[group, "date", value]].copy()
    per = (t.groupby([group, "date"], sort=True)[value]
             .agg(s="sum", n="count").reset_index().sort_values("date", kind="mergesort"))
    cs = per.groupby(group, sort=False)[["s", "n"]].cumsum()
    per["prior_s"] = cs["s"] - per["s"]
    per["prior_n"] = cs["n"] - per["n"]
    per["prior_mean"] = np.where(per["prior_n"] > 0, per["prior_s"] / per["prior_n"], np.nan)
    m = per[[group, "date", "prior_mean", "prior_n"]]
    out = d[[group, "date"]].merge(m, on=[group, "date"], how="left")
    out.index = d.index
    return out["prior_mean"], out["prior_n"]


def _team_rolling(long: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Rolling means over a team's OWN PRIOR matches. The shift happens first, always.

    `long` must already be sorted by (team, date). The shift is applied inside each team's
    history, so a team's first ever match gets NaN rather than its own result.
    """
    cols = [c for c in cols if c in long.columns]
    if not cols:
        return pd.DataFrame(index=long.index)
    g = long.groupby("team", sort=False)
    shifted = g[cols].shift(1)                       # the current match can never be seen
    shifted["team"] = long["team"].to_numpy()
    out = {}
    for w in WINDOWS:
        r = (shifted.groupby("team", sort=False)[cols]
                    .rolling(w, min_periods=max(2, w // 3)).mean())
        r.index = r.index.droplevel(0)
        r = r.reindex(long.index)                    # be explicit: never trust index order
        for c in cols:
            out[f"{c}_r{w}"] = r[c]
    e = (shifted.groupby("team", sort=False)[cols]
                .apply(lambda s: s.ewm(halflife=EWM_HALFLIFE, min_periods=2).mean()))
    if isinstance(e.index, pd.MultiIndex):
        e.index = e.index.droplevel(0)
    e = e.reindex(long.index)
    for c in cols:
        out[f"{c}_ewm"] = e[c]
    return pd.DataFrame(out, index=long.index)


def _venue_rolling(long: pd.DataFrame, cols: list[str], w: int = 5) -> pd.DataFrame:
    """Rolling means over the team's prior matches AT THE SAME VENUE (home or away).

    Kept separate from `_team_rolling` on purpose. A side that scores freely at home and not away
    is a real and common pattern, and a single blended average erases it.
    """
    cols = [c for c in cols if c in long.columns]
    if not cols:
        return pd.DataFrame(index=long.index)
    key = long["team"].astype(str) + "|" + long["is_home"].astype(str)
    tmp = long[cols].copy()
    tmp["_k"] = key.to_numpy()
    sh = tmp.groupby("_k", sort=False)[cols].shift(1)
    sh["_k"] = key.to_numpy()
    r = sh.groupby("_k", sort=False)[cols].rolling(w, min_periods=2).mean()
    r.index = r.index.droplevel(0)
    r = r.reindex(long.index)
    return r.rename(columns={c: f"{c}_venue{w}" for c in cols})


def _rest(long: pd.DataFrame) -> pd.DataFrame:
    """Days since the team's previous match, and how many it played in the prior 14 days."""
    g = long.groupby("team", sort=False)
    prev = g["date"].shift(1)
    days = (long["date"] - prev).dt.days
    cong = []
    for _, idx in long.groupby("team", sort=False).indices.items():
        dts = long["date"].to_numpy()[idx]
        # matches strictly before this one, within 14 days
        cnt = np.searchsorted(dts, dts, side="left") - np.searchsorted(
            dts, dts - np.timedelta64(14, "D"), side="left")
        cong.append(pd.Series(cnt, index=long.index[idx]))
    return pd.DataFrame({"days_rest": days,
                         "matches_14d": pd.concat(cong).reindex(long.index)}, index=long.index)


def _early_season(long: pd.DataFrame) -> pd.DataFrame:
    """Tell the model WHEN its form numbers came from. The gap nobody had filled.

    The walk-forward found prediction is worst at the start of a season and that retraining
    helps least there. The obvious explanation -- "there is no form data yet" -- is WRONG, and
    measuring it said so: rolling form is populated on 94.9% of opening-20% fixtures.

    The real problem is that the numbers are STALE AND UNLABELLED. On a team's first match of a
    season the entire five-match window is last season's football, played by a partly different
    squad, sometimes in a different division -- and `gf_r5` looks exactly the same as a mid-season
    `gf_r5`. The model has no way to discount it because nothing in the feature set distinguishes
    the two.

    So this family does not invent data. It labels the data that is already there:

        season_match_idx        matches this team has played in this season, before this one
        frac_window_this_season what share of the 5-match form window is CURRENT-season football
                                (0.0 on the opening day, 1.0 from match six onward)
        is_season_opener        the first match of a team's season
        days_since_last_match   already in REST, but the 57-day median summer gap is the signal
        changed_league          promoted, relegated or moved -- last season's form was earned in
                                a different division (1.7% of team-seasons, and exactly the ones
                                a stale number misleads on most)
        prev_season_gf/ga/n     an EXPLICIT carry-over prior, so the model has a deliberate
                                anchor rather than an accidental one

    A CAVEAT WORTH RECORDING. `season_label` is an Aug-Jul rule, which is right for the European
    leagues and wrong for the calendar-year ones (Brazil, Japan, MLS, Scandinavia) where a single
    campaign straddles two labels. For those leagues `changed_league` and the carry-over prior are
    noisier than they look. The features are still computed -- a noisy signal beats no signal --
    but a per-league season calendar would sharpen them, and that is a collection change.
    """
    d = long.sort_values(["team", "date"], kind="mergesort").copy()
    g = d.groupby("team", sort=False)
    prev_season = g["season_label"].shift(1)
    prev_league = g["league"].shift(1)

    out = pd.DataFrame(index=d.index)
    out["season_match_idx"] = d.groupby(["team", "season_label"], sort=False).cumcount()
    out["is_season_opener"] = (out["season_match_idx"] == 0).astype(float)
    out["frac_window_this_season"] = np.minimum(out["season_match_idx"] / 5.0, 1.0)
    out["changed_league"] = ((prev_season.notna()) & (prev_season != d["season_label"])
                             & (prev_league != d["league"])).astype(float)

    # Explicit carry-over: the team's own previous-season averages. Every match behind these
    # numbers was played before the current season began, so no future information is involved.
    per = (d.groupby(["team", "season_label"], sort=False)
             .agg(_gf=("gf", "mean"), _ga=("ga", "mean"), _n=("gf", "size"))
             .reset_index().sort_values(["team", "season_label"], kind="mergesort"))
    for c in ("_gf", "_ga", "_n"):
        per[f"prev{c}"] = per.groupby("team", sort=False)[c].shift(1)
    m = d[["team", "season_label"]].merge(
        per[["team", "season_label", "prev_gf", "prev_ga", "prev_n"]],
        on=["team", "season_label"], how="left")
    m.index = d.index
    out["prev_season_gf"] = m["prev_gf"]
    out["prev_season_ga"] = m["prev_ga"]
    out["prev_season_n"] = m["prev_n"]

    # A shrinkage weight the model can use directly: how much should this season's short form be
    # trusted against the carry-over? Standard n/(n+k) form, k=5.
    n = out["season_match_idx"].astype(float)
    out["form_reliability"] = n / (n + 5.0)
    return out


def build_team_features(fx: pd.DataFrame) -> pd.DataFrame:
    """All per-team pre-match features, on the long (team x match) frame."""
    long = D.team_match_long(fx)

    core = ["gf", "ga", "total_goals", "btts"]
    shots = ["shots_f", "shots_a"]
    sot = ["sot_f", "sot_a"]
    corners = ["corners_f", "corners_a"]
    disc = ["fouls_f", "fouls_a", "yellow_f", "yellow_a", "red_f", "red_a"]
    ht = ["ht_gf", "ht_ga"]

    parts = [long[["fixture_key", "team", "is_home", "date", "league"]],
             _team_rolling(long, core + shots + sot + corners + disc + ht),
             _venue_rolling(long, core),
             _rest(long),
             _early_season(long)]
    feat = pd.concat(parts, axis=1)

    # STRENGTH: the team's prior scoring vs its league's prior scoring. Ratio, not difference,
    # so the scale is comparable across a 2.2-goal league and a 3.2-goal league.
    lg_gf, _ = _prior_mean_by_date(long.assign(v=long["gf"]), "league", "v")
    feat["league_prior_goals_per_team"] = lg_gf
    for w in WINDOWS:
        feat[f"attack_strength_r{w}"] = feat[f"gf_r{w}"] / lg_gf.replace(0, np.nan)
        feat[f"defence_strength_r{w}"] = feat[f"ga_r{w}"] / lg_gf.replace(0, np.nan)
    feat["n_prior_matches"] = (long.groupby("team", sort=False).cumcount()).to_numpy()
    return feat


def _pivot_to_fixture(feat: pd.DataFrame) -> pd.DataFrame:
    """Back to one row per fixture, with home_* and away_* columns."""
    val = [c for c in feat.columns if c not in ("fixture_key", "team", "is_home", "date", "league")]
    h = feat[feat.is_home == 1].set_index("fixture_key")[val].add_prefix("h_")
    a = feat[feat.is_home == 0].set_index("fixture_key")[val].add_prefix("a_")
    return h.join(a, how="outer")


def _h2h(fx: pd.DataFrame) -> pd.DataFrame:
    """Prior meetings between the same two clubs, either way round, before this date."""
    d = fx[["fixture_key", "date", "home_team", "away_team", "total_goals", "btts"]].copy()
    pair = np.where(d.home_team < d.away_team,
                    d.home_team + "|" + d.away_team, d.away_team + "|" + d.home_team)
    d["_pair"] = pair
    d = d.sort_values("date", kind="mergesort")
    g = d.groupby("_pair", sort=False)
    out = pd.DataFrame(index=d.index)
    out["h2h_n"] = g.cumcount()
    for col, name in (("total_goals", "h2h_avg_goals"), ("btts", "h2h_btts_rate")):
        cs = g[col].cumsum() - d[col]
        out[name] = np.where(out["h2h_n"] > 0, cs / out["h2h_n"].replace(0, np.nan), np.nan)
    out["fixture_key"] = d["fixture_key"].to_numpy()
    return out.set_index("fixture_key")


def _market(fx: pd.DataFrame) -> pd.DataFrame:
    """De-vigged bookmaker probabilities. ABLATION ONLY -- never in the football-only model.

    Only OU2.5 has both sides priced, so only OU2.5 can be properly de-vigged. The one-sided
    prices (BTTS, O1.5, O3.5) are passed through as raw implied probability WITH THE VIG STILL
    IN, which makes them biased high by roughly the book's margin. That is stated rather than
    silently corrected with an assumed overround, because assuming one would be inventing a
    number (invariant 9).
    """
    o, u = fx["odds_over25"], fx["odds_under25"]
    ip_o, ip_u = 1.0 / o, 1.0 / u
    book = ip_o + ip_u
    out = pd.DataFrame(index=fx.index)
    ok = o.notna() & u.notna() & (book > 1.0) & (book < 1.35)
    out["mkt_p_over25"] = np.where(ok, ip_o / book, np.nan)
    out["mkt_overround"] = np.where(ok, book, np.nan)
    for col, name in (("odds_btts", "mkt_ip_btts"), ("odds_over15", "mkt_ip_over15"),
                      ("odds_over35", "mkt_ip_over35")):
        if col in fx.columns:
            out[name] = np.where(fx[col].notna() & (fx[col] > 1.01), 1.0 / fx[col], np.nan)
    out["fixture_key"] = fx["fixture_key"].to_numpy()
    return out.set_index("fixture_key")


def build(fx: pd.DataFrame) -> pd.DataFrame:
    """The full pre-match feature matrix, one row per fixture, joined back onto `fx`."""
    feat = _pivot_to_fixture(build_team_features(fx))
    out = fx.set_index("fixture_key").join(feat, how="left")

    # BASE: calendar + the league's own prior rate for each target. The league prior is the
    # honest "free" signal; a model that cannot beat it has learned nothing about football.
    out = out.reset_index()
    for t in ("btts", "over15", "over25", "over35"):
        pm, pn = _prior_mean_by_date(out, "league", t)
        out[f"league_prior_{t}"] = pm
        if t == "over25":
            out["league_prior_n"] = pn
    pg, _ = _prior_mean_by_date(out, "league", "total_goals")
    out["league_prior_avg_goals"] = pg
    out["month"] = out["date"].dt.month
    out["dow"] = out["date"].dt.dayofweek
    out["is_weekend"] = out["dow"].isin([5, 6]).astype(int)
    # Season stage: where in its own season bucket the fixture sits, 0..1.
    grp = out.groupby(["league", "season_label"])["date"]
    out["season_stage"] = ((out["date"] - grp.transform("min")).dt.days
                           / (grp.transform("max") - grp.transform("min")).dt.days.replace(0, np.nan))

    out = out.set_index("fixture_key")
    out = out.join(_h2h(fx), how="left").join(_market(fx), how="left")
    return out.reset_index()


def family_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Which built columns belong to which family. Drives every ablation."""
    cols = list(df.columns)

    def pick(*subs, exclude=()):
        return [c for c in cols
                if any(s in c for s in subs) and not any(x in c for x in exclude)
                and c not in D.TARGETS and c != "goals_bucket"]

    fam = {
        "BASE": [c for c in ("league_prior_btts", "league_prior_over15", "league_prior_over25",
                             "league_prior_over35", "league_prior_avg_goals", "league_prior_n",
                             "month", "dow", "is_weekend", "season_stage") if c in cols],
        # exclude "ht_": the columns are prefixed h_/a_, so a bare "gf_r" substring also matches
        # h_ht_gf_r5 and FORM would silently swallow the entire HT family.
        "FORM": pick("gf_r", "ga_r", "gf_ewm", "ga_ewm", "total_goals_r", "total_goals_ewm",
                     "btts_r", "btts_ewm", "_venue", "n_prior_matches", exclude=("ht_",)),
        "SHOTS": pick("shots_f", "shots_a"),
        "SOT": pick("sot_f", "sot_a"),
        "CORNERS": pick("corners_f", "corners_a"),
        "DISCIPLINE": pick("fouls_f", "fouls_a", "yellow_f", "yellow_a", "red_f", "red_a"),
        "STRENGTH": pick("attack_strength", "defence_strength", "league_prior_goals_per_team"),
        "REST": pick("days_rest", "matches_14d"),
        "HT": pick("ht_gf", "ht_ga"),
        "H2H": pick("h2h_"),
        # EARLY is picked BEFORE MARKET and after H2H; ordering matters because a column may
        # only belong to one family and the dedupe below keeps the first claim.
        "EARLY": pick("season_match_idx", "is_season_opener", "frac_window_this_season",
                      "changed_league", "prev_season_gf", "prev_season_ga", "prev_season_n",
                      "form_reliability"),
        "MARKET": pick("mkt_"),
    }
    # A column may only belong to one family, else an ablation "removing SHOTS" would leave a
    # shot-derived column behind and understate the family's contribution.
    seen: set[str] = set()
    for k in FAMILIES:
        fam[k] = [c for c in fam.get(k, []) if c not in seen and not seen.add(c)]
    return fam


def feature_columns(df: pd.DataFrame, families) -> list[str]:
    fam = family_columns(df)
    out: list[str] = []
    for f in families:
        out.extend(fam.get(f, []))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    fx = D.load_fixtures()
    df = build(fx)
    fam = family_columns(df)
    print(f"[features] {len(df):,} fixtures x {sum(len(v) for v in fam.values())} features")
    for k in FAMILIES:
        c = fam[k]
        cov = df[c].notna().mean().mean() if c else float("nan")
        print(f"  {k:<11}{len(c):>4} cols   mean coverage {cov:.3f}")
    if a.audit:
        from src.prediction_lab import leakage
        leakage.audit(fx, df, verbose=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
