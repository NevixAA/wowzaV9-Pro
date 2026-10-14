"""V3 feature families — every value as-of match time (shifted), built from v9's raw primitives.

    from src.player_v3 import features as F
    X = F.build()                 # one row per appearance, v9 baseline columns + V3 families

FAMILIES (names used by the ablation):
  BASE_V9        v9's own 138 PLAYER_FEATURE_COLS as stored in player_history (the champion's view)
  FORM_MH        per-90 rates over last 3/5/10 appearances, season, career, EWMA 5 / 15
  FORM_SHRUNK    the same rates shrunk toward a position x league prior: n/(n+k) rate + k/(n+k) prior,
                 n in 90-minute blocks; k chosen on VALIDATION only (see sot_lab)
  USAGE_SHARE    player share of TEAM shots / SOT / goals / key passes / fouls / minutes over the
                 same windows (sum of his stat / sum of the team stat in the matches he played)
  OPP_PERSONNEL  the opponent's PROJECTED unit: whoever started their previous match, each with his
                 own as-of rates (D: tackles, interceptions, dribbled past, fouls, duel win, height;
                 GK: save rate, saves/90). Knowable before kickoff; not the realised lineup.
  MATCHUP_RAW    raw attacker x unit pairs (dribbles90 vs dribbled_past90, fouls_drawn90 vs fouls90,
                 sot90 vs gk save rate, height vs unit height) — left to the tree, not multiplied
  ROLE           latent role from the career per-90 profile (k-means, fitted on TRAIN rows only)

Priors and the role model are fit on TRAIN rows only and applied everywhere, so the holdout never
shapes a feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.player_v3 import HOLDOUT_FROM, TRAIN_END, VALID_END
from src.player_v3 import data as D

STATS = ["shots_on_target", "shots_total", "goals", "assists", "key_passes", "fouls_drawn",
         "fouls_committed", "yellow_cards", "duels_won", "dribbles_success", "dribbles_attempted"]
SHARE = {"shots_on_target": "team_sot", "shots_total": "team_shots", "goals": "team_goals",
         "key_passes": "team_kp", "fouls_drawn": "team_fouls_drawn", "minutes": "team_minutes"}
WINDOWS = (3, 5, 10)
FAMILIES: dict[str, list[str]] = {}


def _v9_feature_cols() -> list[str]:
    import importlib.util
    import sys
    from config import pro_config as cfg
    spec = importlib.util.spec_from_file_location("v9_player_config", cfg.V9_LOCAL / "player_model" / "config.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["v9_player_config"] = mod
    spec.loader.exec_module(mod)
    return list(mod.PLAYER_FEATURE_COLS)


def form(h: pd.DataFrame) -> pd.DataFrame:
    """Per-90 rates over windows, season, career and EWMA — sums of stat over sums of minutes."""
    cols = STATS + ["minutes"]
    out = {}
    roll = D.asof_rolling(h, "player_id", cols, windows=WINDOWS, how="sum")
    cum = D.asof_rolling(h, "player_id", cols, windows=(), expanding=True, how="sum")
    h2 = h.assign(season_key=h["season"].astype(str))
    sea = D.asof_rolling(h2, ["player_id", "season_key"], cols, windows=(), expanding=True, how="sum", prefix="s_")
    for s in STATS:
        for w in WINDOWS:
            out[f"{s}_p90_l{w}"] = D.per90(roll[f"{s}_l{w}"], roll[f"minutes_l{w}"])
        out[f"{s}_p90_career"] = D.per90(cum[f"{s}_cum"], cum["minutes_cum"])
        out[f"{s}_p90_season"] = D.per90(sea[f"s_{s}_cum"], sea["s_minutes_cum"])
    out["minutes_career"] = cum["minutes_cum"]
    out["minutes_l5_sum"] = roll["minutes_l5"]
    rate = pd.DataFrame({s: D.per90(h[s].astype(float), h["minutes"].astype(float).clip(lower=1)) for s in ("shots_on_target", "shots_total")}, index=h.index)
    ew = D.asof_rolling(pd.concat([h[["player_id", "date", "fixture_id"]], rate], axis=1), "player_id",
                        ["shots_on_target", "shots_total"], windows=(), ewm_spans=(5, 15))
    out.update({c.replace("_ewm", "_p90_ewm"): ew[c] for c in ew.columns})
    f = pd.DataFrame(out, index=h.index)
    FAMILIES["FORM_MH"] = list(f.columns)
    return f


def shrunk(h: pd.DataFrame, f: pd.DataFrame, k: float) -> pd.DataFrame:
    """n/(n+k) * recent + k/(n+k) * prior; prior = position x league per-90 on TRAIN rows only."""
    tr = h["date"] < pd.Timestamp(TRAIN_END)
    g = h[tr].groupby(["position", "league"])
    prior = {s: (g[s].sum() / g["minutes"].sum() * 90.0) for s in STATS}
    key = pd.MultiIndex.from_frame(h[["position", "league"]])
    out = {}
    for s in STATS:
        p = pd.Series(prior[s].reindex(key).to_numpy(), index=h.index)
        p = p.fillna(float((h.loc[tr, s].sum() / h.loc[tr, "minutes"].sum()) * 90.0))
        for w in ("l5", "l10", "career"):
            mins = f["minutes_career"] if w == "career" else f["minutes_l5_sum"] * (2 if w == "l10" else 1)
            n = (mins / 90.0).fillna(0)
            out[f"{s}_shr_{w}"] = (n / (n + k)) * f[f"{s}_p90_{w}"].fillna(p) + (k / (n + k)) * p
    s = pd.DataFrame(out, index=h.index)
    FAMILIES["FORM_SHRUNK"] = list(s.columns)
    return s


def usage(h: pd.DataFrame, tt: pd.DataFrame) -> pd.DataFrame:
    x = h[["fixture_id", "team", "player_id", "date", *SHARE]].merge(
        tt[["fixture_id", "team", *SHARE.values()]], on=["fixture_id", "team"], how="left")
    x.index = h.index
    cols = list(SHARE) + list(SHARE.values())
    roll = D.asof_rolling(x, "player_id", cols, windows=WINDOWS, how="sum")
    cum = D.asof_rolling(x, "player_id", cols, windows=(), expanding=True, how="sum")
    out = {}
    for s, t in SHARE.items():
        for w in WINDOWS:
            out[f"{s}_share_l{w}"] = roll[f"{s}_l{w}"] / roll[f"{t}_l{w}"].replace(0, np.nan)
        out[f"{s}_share_career"] = cum[f"{s}_cum"] / cum[f"{t}_cum"].replace(0, np.nan)
    # team environment the share multiplies into: the team's own recent SOT / shots per match
    tr = D.asof_rolling(tt, "team", ["team_sot", "team_shots", "opp_sot", "opp_shots"], windows=(5, 10))
    env = tt[["fixture_id", "team"]].join(tr).rename(columns=lambda c: c if c in ("fixture_id", "team") else f"env_{c}")
    opp_env = env.rename(columns={"team": "opponent", **{c: c.replace("env_", "oppenv_") for c in env.columns if c.startswith("env_")}})
    u = pd.DataFrame(out, index=h.index)
    e = h[["fixture_id", "team", "opponent"]].merge(env, on=["fixture_id", "team"], how="left") \
        .merge(opp_env, on=["fixture_id", "opponent"], how="left")
    e.index = h.index
    e = e.drop(columns=["fixture_id", "team", "opponent"])
    FAMILIES["USAGE_SHARE"] = list(u.columns)
    FAMILIES["TEAM_ENV"] = list(e.columns)
    return pd.concat([u, e], axis=1)


def personnel(h: pd.DataFrame) -> pd.DataFrame:
    """The opponent's projected defensive unit and goalkeeper, from THEIR previous match's starters,
    each carrying his post-match (therefore pre-target) last-10 rates."""
    cols = ["tackles_total", "interceptions", "dribbles_past", "fouls_committed", "duels_won", "duels_total",
            "minutes", "saves", "goals_conceded"]
    cols = [c for c in cols if c in h.columns]
    # post-match last-10 sums = shifted rolling of the NEXT row; computed as plain rolling incl. current
    order = h.sort_values(["date", "fixture_id"], kind="mergesort").index
    q = h.loc[order, ["player_id", *cols]]
    post = q.groupby("player_id")[cols].rolling(10, min_periods=1).sum().reset_index(level=0, drop=True)
    post = post.reindex(h.index)
    r = pd.DataFrame({
        "tkl90": D.per90(post["tackles_total"], post["minutes"]),
        "int90": D.per90(post["interceptions"], post["minutes"]),
        "dpast90": D.per90(post["dribbles_past"], post["minutes"]),
        "foul90": D.per90(post["fouls_committed"], post["minutes"]),
        "duelwin": post["duels_won"] / post["duels_total"].replace(0, np.nan),
        "gk_save": post["saves"] / (post["saves"] + post["goals_conceded"]).replace(0, np.nan),
        "gk_saves90": D.per90(post["saves"], post["minutes"]),
    }, index=h.index)
    st = pd.concat([h[["fixture_id", "team", "date", "position", "started", "height_cm"]], r], axis=1)
    st = st[st["started"] == 1]
    dfn = st[st["position"] == "D"].groupby(["fixture_id", "team"]).agg(
        date=("date", "first"), u_tkl90=("tkl90", "mean"), u_int90=("int90", "mean"),
        u_dpast90=("dpast90", "mean"), u_dpast90_max=("dpast90", "max"), u_foul90=("foul90", "mean"),
        u_duelwin=("duelwin", "mean"), u_height=("height_cm", "mean"), u_height_max=("height_cm", "max"))
    gk = st[st["position"] == "G"].groupby(["fixture_id", "team"]).agg(u_gk_save=("gk_save", "first"),
                                                                       u_gk_saves90=("gk_saves90", "first"))
    unit = dfn.join(gk, how="outer").reset_index()
    fx_date = h.groupby(["fixture_id", "team"])["date"].first().rename("fx_date").reset_index()
    unit = unit.merge(fx_date, on=["fixture_id", "team"], how="left").drop(columns=["date"])
    unit = unit.sort_values(["team", "fx_date", "fixture_id"], kind="mergesort")
    # project: the unit a team fielded in its PREVIOUS match is the unit expected in this one
    ucols = [c for c in unit.columns if c.startswith("u_")]
    unit[ucols] = unit.groupby("team")[ucols].shift(1)
    proj = unit.rename(columns={"team": "opponent", "fx_date": "date"})
    p = h[["fixture_id", "opponent"]].merge(proj.drop(columns=["date"]), on=["fixture_id", "opponent"], how="left")
    p.index = h.index
    p = p.drop(columns=["fixture_id", "opponent"]).add_prefix("opp_")
    FAMILIES["OPP_PERSONNEL"] = list(p.columns)
    return p


def matchup(f: pd.DataFrame, p: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    m = pd.DataFrame({
        "mu_drib_vs_dpast": f["dribbles_attempted_p90_l10"] * p["opp_u_dpast90"],
        "mu_fdrawn_vs_foul": f["fouls_drawn_p90_l10"] * p["opp_u_foul90"],
        "mu_sot_vs_gksave": f["shots_on_target_p90_l10"] * (1 - p["opp_u_gk_save"]),
        "mu_height_edge": h["height_cm"] - p["opp_u_height"],
        "mu_duel_vs_duel": f["duels_won_p90_l10"] * (1 - p["opp_u_duelwin"]),
    }, index=h.index)
    FAMILIES["MATCHUP_RAW"] = list(m.columns)
    return m


ROLE_COLS = ["shots_total", "shots_on_target", "key_passes", "dribbles_attempted", "fouls_drawn",
             "fouls_committed", "duels_total", "tackles_total", "interceptions", "passes_total", "offsides"]


def role(h: pd.DataFrame, k: int = 8) -> pd.DataFrame:
    """Latent role from the career per-90 profile; k-means fit on TRAIN rows only."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    cols = [c for c in ROLE_COLS if c in h.columns]
    cum = D.asof_rolling(h, "player_id", cols + ["minutes"], windows=(), expanding=True, how="sum")
    prof = pd.DataFrame({c: D.per90(cum[f"{c}_cum"], cum["minutes_cum"]) for c in cols}, index=h.index)
    ok = prof.notna().all(axis=1) & (cum["minutes_cum"] >= 450)
    tr = ok & (h["date"] < pd.Timestamp(TRAIN_END))
    sc = StandardScaler().fit(prof[tr])
    km = KMeans(n_clusters=k, n_init=5, random_state=0).fit(sc.transform(prof[tr].sample(min(200_000, int(tr.sum())), random_state=0)))
    lab = pd.Series(-1, index=h.index)
    lab[ok] = km.predict(sc.transform(prof[ok]))
    r = pd.get_dummies(lab, prefix="role").astype(float)
    r = r.drop(columns=[c for c in r.columns if c == "role_-1"], errors="ignore")
    FAMILIES["ROLE"] = list(r.columns)
    return r


def build(h: pd.DataFrame | None = None, k_shrink: float = 5.0) -> pd.DataFrame:
    base_cols = _v9_feature_cols()
    raw = D.RAW + [c for c in base_cols if c not in D.RAW] + ["target_sot", "target_sot2", "target_sot3",
                                                               "target_sot4", "target_goals", "n_prev_games"]
    raw = list(dict.fromkeys(raw))          # n_prev_games is also a v9 feature - load each column once
    h = D.load_history(cols=raw) if h is None else h
    h = h[h["n_prev_games"] >= 1].reset_index(drop=True) if "n_prev_games" in h.columns else h
    FAMILIES["BASE_V9"] = [c for c in base_cols if c in h.columns]
    tt = D.team_totals(h)
    f = form(h)
    s = shrunk(h, f, k_shrink)
    u = usage(h, tt)
    p = personnel(h)
    m = matchup(f, p, h)
    r = role(h)
    return pd.concat([h, f, s, u, p, m, r], axis=1)
