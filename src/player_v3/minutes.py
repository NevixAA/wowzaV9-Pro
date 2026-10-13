"""H1 part 1 — a dedicated expected-minutes model.

    python -m src.player_v3.minutes          # -> output/player_v3/minutes_validation.csv

THE POPULATION PROBLEM. v9's player_history holds only APPEARANCES — a player left on the bench or
out of the squad simply has no row. A minutes model trained on it can never learn P(start), because
every row already played. So the panel is rebuilt: for each player x club TENURE (first to last
appearance for that club), every fixture the club played is a row, and a fixture with no appearance
is 0 minutes, started 0.

Caveat, stated not hidden: the tenure end (his last appearance for the club) is known only in
hindsight. It defines "squad member" the way a pre-match squad list would; it slightly flatters
every model equally, baselines included.

Targets: start, minutes, 60+, 75+, 90 (minutes >= 90).
Features: as-of only (shifted inside player x team): minutes/starts/appearances over the last
1/3/5/10 club fixtures INCLUDING absences, appearance-only means (the v9 view), starts since
joining and this season, days since last appearance, days since the club's previous match,
club matches in the previous 14 days, age, position, league, home.

Baselines (the current view): minutes_pg = mean minutes over prior APPEARANCES (v9 style),
starter_rate over appearances, simple last-5 (incl. absences), and the 60-minute eligibility rule
(minutes_pg >= 60 -> "plays 60"). Challengers: logistic, HGB. Fit on TRAIN only; reported on
VALIDATION and HOLDOUT; nothing is tuned on the holdout.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.player_v3 import CALC_VERSION, HOLDOUT_FROM, TRAIN_END, VALID_END
from src.player_v3 import data as D

OUT = cfg.OUTPUT_DIR / "player_v3"
THRESH = (60, 75, 90)


def build_panel(h: pd.DataFrame | None = None) -> pd.DataFrame:
    h = D.load_history() if h is None else h
    tt = D.team_totals(h)[["fixture_id", "team", "date", "league", "opponent"]]
    ten = (h.groupby(["player_id", "team"])["date"].agg(first="min", last="max").reset_index())
    rows = []
    for team, g in ten.groupby("team", sort=False):
        fx = tt[tt["team"] == team].sort_values("date")
        if fx.empty:
            continue
        dates = fx["date"].to_numpy()
        for r in g.itertuples(index=False):
            lo, hi = np.searchsorted(dates, r.first, "left"), np.searchsorted(dates, r.last, "right")
            if hi - lo < 2:
                continue
            part = fx.iloc[lo:hi]
            rows.append(pd.DataFrame({"player_id": r.player_id, "team": team,
                                      "fixture_id": part["fixture_id"].to_numpy(),
                                      "date": part["date"].to_numpy(),
                                      "league": part["league"].to_numpy(),
                                      "opponent": part["opponent"].to_numpy()}))
    p = pd.concat(rows, ignore_index=True)
    app = h[["player_id", "fixture_id", "minutes", "started", "position", "age", "is_home"]]
    p = p.merge(app, on=["player_id", "fixture_id"], how="left")
    p["appeared"] = p["minutes"].notna().astype(int)
    p["minutes"] = p["minutes"].fillna(0).clip(0, 120)
    p["started"] = p["started"].fillna(0).astype(int)
    # position / age: carry the last known value forward within the player (pre-match knowledge)
    p = p.sort_values(["player_id", "date", "fixture_id"], kind="mergesort").reset_index(drop=True)
    for c in ("position", "age"):
        p[c] = p.groupby("player_id")[c].ffill()
    home = h.groupby(["fixture_id", "team"])["is_home"].first().rename("home").reset_index()
    p = p.merge(home, on=["fixture_id", "team"], how="left")
    return p.drop(columns=["is_home"]).sort_values(["date", "fixture_id", "player_id"]).reset_index(drop=True)


def add_features(p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    key = ["player_id", "team"]
    p["app_minutes"] = p["minutes"].where(p["appeared"] == 1)          # NaN when absent
    p["app_started"] = p["started"].where(p["appeared"] == 1)
    for k in THRESH:
        p[f"m{k}"] = (p["minutes"] >= k).astype(int)
    roll = D.asof_rolling(p, key, ["minutes", "started", "appeared", "m60"], windows=(1, 3, 5, 10))
    cum = D.asof_rolling(p, key, ["minutes", "started", "appeared"], windows=(), expanding=True)
    # v9-style appearance-only views: rolling means skip NaN (absences) by construction
    appv = D.asof_rolling(p, key, ["app_minutes", "app_started"], windows=(10,), expanding=True)
    p = pd.concat([p, roll, cum, appv], axis=1)
    p["season"] = np.where(p["date"].dt.month >= 7, p["date"].dt.year, p["date"].dt.year - 1)
    sea = D.asof_rolling(p, key + ["season"], ["started"], windows=(), expanding=True, prefix="season_")
    p = pd.concat([p, sea], axis=1)
    # days since last appearance (as of this fixture) and club rhythm
    order = p.sort_values(["date", "fixture_id"], kind="mergesort").index
    q = p.loc[order]
    last_app = q["date"].where(q["appeared"] == 1).groupby([q["player_id"], q["team"]]).shift(1)
    last_app = last_app.groupby([q["player_id"], q["team"]]).ffill()
    p.loc[order, "days_since_app"] = (q["date"] - last_app).dt.days
    prev_fx = q.groupby([q["player_id"], q["team"]])["date"].shift(1)
    p.loc[order, "rest_days"] = (q["date"] - prev_fx).dt.days
    p["n_prior"] = p.groupby(key).cumcount()
    tf = (p[["team", "fixture_id", "date"]].drop_duplicates(["team", "fixture_id"])
            .sort_values(["team", "date"]).set_index("date"))
    tf["congestion14"] = (tf.groupby("team")["fixture_id"].transform(
        lambda s: s.rolling("14D", closed="left").count()))
    p = p.merge(tf.reset_index()[["team", "fixture_id", "congestion14"]], on=["team", "fixture_id"], how="left")
    return p[p["n_prior"] >= 1].reset_index(drop=True)


FEATS = ["minutes_l1", "minutes_l3", "minutes_l5", "minutes_l10", "started_l1", "started_l3",
         "started_l5", "started_l10", "appeared_l3", "appeared_l5", "appeared_l10", "m60_l5",
         "m60_l10", "minutes_cum", "started_cum", "appeared_cum", "app_minutes_l10",
         "app_minutes_cum", "app_started_l10", "app_started_cum", "season_started_cum",
         "days_since_app", "rest_days", "congestion14", "n_prior", "age", "home",
         "pos_D", "pos_M", "pos_F", "pos_G"]


def _design(p: pd.DataFrame) -> pd.DataFrame:
    X = p.copy()
    for c in "DMFG":
        X[f"pos_{c}"] = (X["position"] == c).astype(float)
    X["home"] = pd.to_numeric(X["home"], errors="coerce")
    X["days_since_app"] = X["days_since_app"].clip(upper=365)
    return X[FEATS].astype(float)


def _ece(p, y, bins=10):
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return e


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def _block_diff_ci(loss_a, loss_b, groups, n_boot=2000, seed=7):
    """95% CI of mean(loss_a - loss_b), resampling whole match dates."""
    d = pd.DataFrame({"x": np.asarray(loss_a) - np.asarray(loss_b), "g": np.asarray(groups)})
    s = d.groupby("g")["x"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    m = s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1)
    return float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def predictions(p: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Every model's P(start), E[minutes], P(60+/75+/90) for all rows. Challengers fit on TRAIN."""
    from sklearn.ensemble import HistGradientBoostingClassifier as HGC
    from sklearn.ensemble import HistGradientBoostingRegressor as HGR
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer

    tr, _, _ = D.chrono_split(p["date"], TRAIN_END, VALID_END, HOLDOUT_FROM)
    X = _design(p)
    out = {}
    # ── baselines: the current view ─────────────────────────────────────────────
    mpg = p["app_minutes_l10"].fillna(p["app_minutes_cum"])
    out["BASE_minutes_pg"] = pd.DataFrame({
        "start": p["app_started_l10"].fillna(p["app_started_cum"]),
        "minutes": mpg, **{f"m{k}": (mpg >= k).astype(float) * 0 + np.nan for k in THRESH}})
    # P(k+) from the same appearance-only history: share of prior appearances reaching k
    for k in THRESH:
        hit = (p["app_minutes"] >= k).astype(float).where(p["appeared"] == 1)
        tmp = p[["player_id", "team", "date", "fixture_id"]].assign(**{f"h{k}": hit})
        out["BASE_minutes_pg"][f"m{k}"] = D.asof_rolling(tmp, ["player_id", "team"], [f"h{k}"],
                                                         windows=(10,))[f"h{k}_l10"].to_numpy()
    out["BASE_last5"] = pd.DataFrame({"start": p["started_l5"], "minutes": p["minutes_l5"],
                                      "m60": p["m60_l5"], "m75": np.nan, "m90": np.nan})
    out["BASE_heuristic60"] = pd.DataFrame({"start": np.nan, "minutes": np.nan,
                                            "m60": (mpg >= 60).astype(float), "m75": np.nan, "m90": np.nan})
    # ── challengers ────────────────────────────────────────────────────────────
    y = {"start": p["started"].to_numpy(), **{f"m{k}": p[f"m{k}"].to_numpy() for k in THRESH}}
    lin = {}
    hgb = {}
    for t, yt in y.items():
        lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                           LogisticRegression(max_iter=500, C=1.0))
        lr.fit(X[tr], yt[tr])
        lin[t] = lr.predict_proba(X)[:, 1]
        hg = HGC(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=100,
                 early_stopping=False, random_state=0).fit(X[tr], yt[tr])
        hgb[t] = hg.predict_proba(X)[:, 1]
    lreg = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LinearRegression())
    lin["minutes"] = np.clip(lreg.fit(X[tr], p["minutes"][tr]).predict(X), 0, 95)
    hreg = HGR(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=100,
               early_stopping=False, random_state=0).fit(X[tr], p["minutes"][tr])
    hgb["minutes"] = np.clip(hreg.predict(X), 0, 95)
    out["LOGIT"] = pd.DataFrame(lin)
    out["HGB"] = pd.DataFrame(hgb)
    for k in out:
        out[k].index = p.index
    return out


def evaluate(p: pd.DataFrame, preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    _, va, ho = D.chrono_split(p["date"], TRAIN_END, VALID_END, HOLDOUT_FROM)
    rows = []
    for period, m in (("validation", va), ("holdout", ho)):
        for model, pr in preds.items():
            for t in ("start", "m60", "m75", "m90"):
                q = pr[t][m]
                ok = q.notna()
                if ok.sum() < 100:
                    continue
                yy = p.loc[m, "started" if t == "start" else t][ok].to_numpy(float)
                qq = q[ok].clip(0, 1).to_numpy(float)
                rows.append({"period": period, "model": model, "target": t, "n": int(ok.sum()),
                             "coverage": round(float(ok.mean()), 4),
                             "brier": round(float(((qq - yy) ** 2).mean()), 5),
                             "log_loss": round(_ll(qq, yy), 5), "ece": round(_ece(qq, yy), 5),
                             "base_rate": round(float(yy.mean()), 4)})
            q = pr["minutes"][m]
            ok = q.notna()
            if ok.sum() >= 100:
                err = q[ok].to_numpy(float) - p.loc[m, "minutes"][ok].to_numpy(float)
                rows.append({"period": period, "model": model, "target": "minutes", "n": int(ok.sum()),
                             "coverage": round(float(ok.mean()), 4),
                             "mae": round(float(np.abs(err).mean()), 3),
                             "rmse": round(float(np.sqrt((err ** 2).mean())), 3)})
    return pd.DataFrame(rows)


def head_to_head(p: pd.DataFrame, preds: dict, a: str, b: str, target: str) -> dict:
    """Holdout: challenger a vs baseline b on rows both cover. Negative diff = a better."""
    _, _, ho = D.chrono_split(p["date"], TRAIN_END, VALID_END, HOLDOUT_FROM)
    qa, qb = preds[a][target], preds[b][target]
    m = ho & qa.notna() & qb.notna()
    yv = p.loc[m, "started" if target == "start" else target].to_numpy(float)
    la = (qa[m].clip(0, 1).to_numpy(float) - yv) ** 2
    lb = (qb[m].clip(0, 1).to_numpy(float) - yv) ** 2
    lo, hi = _block_diff_ci(la, lb, p.loc[m, "date"].dt.strftime("%Y-%m-%d"))
    return {"challenger": a, "baseline": b, "target": target, "n": int(m.sum()),
            "brier_diff": round(float((la - lb).mean()), 5), "ci95": [round(lo, 5), round(hi, 5)]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    p = add_features(build_panel())
    print(f"[minutes] panel {len(p):,} rows | appeared {p['appeared'].mean():.1%} | "
          f"started {p['started'].mean():.1%}")
    preds = predictions(p)
    ev = evaluate(p, preds)
    ev.insert(0, "calculation_version", CALC_VERSION)
    ev["generated_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    ev.to_csv(OUT / "minutes_validation.csv", index=False)
    print(ev[ev.period == "holdout"].to_string(index=False))
    h2h = [head_to_head(p, preds, "HGB", "BASE_minutes_pg", t) for t in ("start", "m60", "m75", "m90")]
    h2h.append(head_to_head(p, preds, "HGB", "BASE_heuristic60", "m60"))
    for r in h2h:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
