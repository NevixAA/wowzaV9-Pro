"""
The served 1X2 model (owner 2026-11-09, P5 review): multinomial logistic on v9's clean features,
refit MONTHLY; plus a blend with the pre-kickoff price where a real price exists. PAPER only.

Design (every value comes from reports/P5_1X2_REVIEW.md or v9's Phase 2 config, none typed here
without a source):
  features   v9 config/phase2_retrain.json feature list (43 history-derived columns, built by v9's
             build_features through src/pipelines/onex2_v9_bridge.py) + elo_diff + league one-hot
  elo        per league, K = 25, a new club enters at the league's current mean (offset 0): the
             configuration P5 chose on the walk-forward region (out of K {15, 25, 40} x offset
             {0, 50, 100})
  logistic   C = 0.5 (v9 Phase 2 config candidates.logistic.C), train-window median imputer with
             missing indicators, standardised; a column with no training value is dropped
  window     the 3 years before the training date (P5's rolling window)
  blend      multinomial logistic on [log p_model, log p_market_entry] fitted on the model's
             OUT-OF-SAMPLE predictions for the last BLEND_MONTHS complete months (each month
             predicted by a fit on the 3 years before it), on rows with a real entry price
             (football-data pre-match Avg, else the sharp tracker's opening h2h; power de-vig)

A league the model was not trained on is NOT served (no league effect exists for it). A missing
input stays missing up to the model's own fitted imputer; nothing else is filled.
"""
from __future__ import annotations

import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "src" / "pipelines" / "onex2_v9_bridge.py"
MODEL_FILE = ROOT / "output" / "model_1x2_clean.pkl"
META_FILE = ROOT / "output" / "model_1x2_clean.json"
CELLS_CONFIG = ROOT / "config" / "onex2_research_cells.json"
CELLS_FILE = ROOT / "output" / "onex2_research_cells.json"

CALC_VERSION = "2.0.0"
MODEL_NAME = "mnlogit_clean"
ELO_K = 25.0
ELO_NEW_OFFSET = 0.0
LOGISTIC_C = 0.5
BLEND_C = 1.0
FIT_WINDOW_DAYS = 3 * 365
BLEND_MONTHS = 9
OUTCOMES = ("home", "draw", "away")


# ── bridge ──────────────────────────────────────────────────────────────────────────────────

def run_bridge(mode: str, v9_root: str, *args: str) -> dict:
    """Run the v9-side bridge in v9's own interpreter environment; returns its meta.json."""
    out_dir = args[-1] if mode == "upcoming" else args[0]
    p = subprocess.run([sys.executable, str(BRIDGE), mode, v9_root, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"onex2 bridge ({mode}) failed: {p.stderr[-2000:]}")
    return json.loads((Path(out_dir) / "meta.json").read_text(encoding="utf-8"))


# ── Elo ─────────────────────────────────────────────────────────────────────────────────────

def elo_state(matches: pd.DataFrame, k: float, new_offset: float):
    """(pre-match Elo difference per row_id, final ratings {league: {club: rating}}).

    Per league, chronological. All matches of one DAY are rated before any of that day's results
    updates a rating. A club first seen in the league enters at the league's current mean minus
    `new_offset`; the very first clubs of a league start level (there is nothing to be relative to).
    """
    out, final = {}, {}
    for lg, g in matches.sort_values(["date", "row_id"]).groupby("league"):
        r: dict[str, float] = {}
        total = 0.0
        days = g["date"].to_numpy()
        rec = list(zip(g["row_id"], g["home_team"], g["away_team"], g["home_goals"], g["away_goals"]))
        i, n = 0, len(rec)
        while i < n:
            j = i
            while j < n and days[j] == days[i]:
                j += 1
            mean = total / len(r) if r else 0.0
            for _, h, a, _, _ in rec[i:j]:
                for t in (h, a):
                    if t not in r:
                        r[t] = mean - (new_offset if r else 0.0)
                        total += r[t]
            upd = []
            for rid, h, a, hg, ag in rec[i:j]:
                d0 = r[h] - r[a]
                out[rid] = d0
                e = 1.0 / (1.0 + 10 ** (-d0 / 400.0))
                s = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
                upd.append((h, a, k * (s - e)))
            for h, a, dlt in upd:                  # zero-sum: the league total is unchanged
                r[h] += dlt
                r[a] -= dlt
            i = j
        final[lg] = dict(r)
    return pd.Series(out, name="elo_diff"), final


def elo_diff_upcoming(final: dict, league: str, home: str, away: str, new_offset: float) -> float | None:
    """Pre-match Elo difference for a fixture after every stored result; a club the league has not
    seen enters at the league mean minus `new_offset` (the same entry rule as training). None when
    the league has no ratings at all."""
    r = final.get(league)
    if not r:
        return None
    entry = float(np.mean(list(r.values()))) - new_offset      # training's entry rule
    rh = r[home] if home in r else entry
    ra = r[away] if away in r else entry
    return float(rh - ra)


# ── logistic ────────────────────────────────────────────────────────────────────────────────

def design(F: pd.DataFrame, cols: list[str], leagues: list[str]) -> pd.DataFrame:
    """Numeric feature columns + elo_diff + one 0/1 column per TRAINING league (fixed order)."""
    X = F[cols + ["elo_diff"]].apply(pd.to_numeric, errors="coerce")
    for lg in leagues:
        X[f"lg_{lg}"] = (F["league"] == lg).astype(float)
    return X


def fit_mnlogit(F: pd.DataFrame, cols: list[str], lo: pd.Timestamp, hi: pd.Timestamp) -> dict | None:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    tr = F[(F["date"] >= lo) & (F["date"] < hi)]
    if len(tr) < 1000:
        return None
    leagues = sorted(tr["league"].astype(str).unique())
    X = design(tr, cols, leagues)
    keep = [c for c in X.columns if X[c].notna().any()]       # no training value -> dropped
    y = np.where(tr["home_goals"] > tr["away_goals"], 0,
                 np.where(tr["home_goals"] == tr["away_goals"], 1, 2))
    pipe = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(C=LOGISTIC_C, max_iter=2000))
    pipe.fit(X[keep], y)
    return {"pipe": pipe, "keep": keep, "leagues": leagues, "cols": list(cols),
            "classes": [int(c) for c in pipe.classes_], "n_train": int(len(tr)),
            "window": [str(lo.date()), str(hi.date())]}


def predict_mnlogit(m: dict, F: pd.DataFrame) -> pd.DataFrame:
    """p_home/p_draw/p_away for rows whose league the model knows; other rows are absent."""
    F = F[F["league"].astype(str).isin(m["leagues"])]
    if F.empty:
        return pd.DataFrame(columns=["row_key", "p_home", "p_draw", "p_away"])
    X = design(F, m["cols"], m["leagues"])[m["keep"]]
    p = m["pipe"].predict_proba(X)
    c = m["classes"]
    return pd.DataFrame({"row_key": F.index, "p_home": p[:, c.index(0)], "p_draw": p[:, c.index(1)],
                         "p_away": p[:, c.index(2)]})


# ── market ──────────────────────────────────────────────────────────────────────────────────

def power_devig3(o: np.ndarray) -> np.ndarray:
    """p_i = (1/o_i)^k with k such that the p_i sum to 1; NaN where any odd is not a price."""
    o = np.asarray(o, dtype=float).reshape(-1, 3)
    out = np.full(o.shape, np.nan)
    ok = np.all(np.isfinite(o) & (o > 1.0), axis=1)
    q = 1.0 / o[ok]
    lo, hi = np.full(len(q), 0.2), np.full(len(q), 5.0)
    for _ in range(80):
        mid = (lo + hi) / 2
        s = (q ** mid[:, None]).sum(1)
        lo = np.where(s > 1.0, mid, lo)
        hi = np.where(s > 1.0, hi, mid)
    p = q ** ((lo + hi) / 2)[:, None]
    out[ok] = p / p.sum(1, keepdims=True)
    return out


def entry_market(prices: pd.DataFrame) -> pd.DataFrame:
    """De-vigged ENTRY probability per row_id: football-data pre-match first, else sharp opening."""
    d = prices[prices["class"].isin(["FD_ENTRY", "SHARP_OPEN"])].copy()
    d["_r"] = (d["class"] != "FD_ENTRY").astype(int)
    d = d.sort_values("_r").drop_duplicates("row_id")
    p = power_devig3(d[["o_home", "o_draw", "o_away"]].to_numpy())
    m = pd.DataFrame({"row_id": d["row_id"].to_numpy()})
    for i, k in enumerate(OUTCOMES):
        m[f"m_{k}"] = p[:, i]
    return m.dropna()


def fit_blend(oos: pd.DataFrame) -> dict | None:
    """oos: p_*, m_*, y. Multinomial logistic on log probabilities."""
    from sklearn.linear_model import LogisticRegression
    d = oos.dropna(subset=[f"p_{k}" for k in OUTCOMES] + [f"m_{k}" for k in OUTCOMES])
    if len(d) < 300 or d["y"].nunique() < 3:
        return None
    X = np.log(np.clip(d[[f"p_{k}" for k in OUTCOMES] + [f"m_{k}" for k in OUTCOMES]].to_numpy(),
                       1e-6, 1))
    lr = LogisticRegression(C=BLEND_C, max_iter=2000).fit(X, d["y"].to_numpy())
    return {"lr": lr, "classes": [int(c) for c in lr.classes_], "n_fit": int(len(d)),
            "coef": lr.coef_.round(4).tolist()}


def predict_blend(b: dict, p: np.ndarray, m: np.ndarray) -> np.ndarray:
    X = np.log(np.clip(np.hstack([np.asarray(p).reshape(-1, 3), np.asarray(m).reshape(-1, 3)]),
                       1e-6, 1))
    q = b["lr"].predict_proba(X)
    c = b["classes"]
    return np.column_stack([q[:, c.index(0)], q[:, c.index(1)], q[:, c.index(2)]])


# ── training ────────────────────────────────────────────────────────────────────────────────

def _labels(F: pd.DataFrame) -> np.ndarray:
    return np.where(F["home_goals"] > F["away_goals"], 0,
                    np.where(F["home_goals"] == F["away_goals"], 1, 2))


def train(extract_dir: str | Path, asof: pd.Timestamp) -> tuple[dict, dict]:
    """(artifact, report) from a bridge `history` extract, using only results dated before `asof`."""
    ex = Path(extract_dir)
    meta = json.loads((ex / "meta.json").read_text(encoding="utf-8"))
    M = pd.read_parquet(ex / "matches.parquet")
    M["date"] = pd.to_datetime(M["date"])
    M = M[M["date"] < asof]
    F = pd.read_parquet(ex / "features.parquet")
    F["date"] = pd.to_datetime(F["date"])
    F = F[F["date"] < asof]
    req = meta.get("require_present") or []
    if req:
        F = F.dropna(subset=req)
    cols = list(meta["feature_columns"])
    elo, final = elo_state(M, ELO_K, ELO_NEW_OFFSET)
    F = F.join(elo, on="row_id").set_index("row_id", drop=False)

    model = fit_mnlogit(F, cols, asof - pd.Timedelta(days=FIT_WINDOW_DAYS), asof)
    if model is None:
        raise RuntimeError("fewer than 1,000 training rows in the window - no model")

    # blend: out-of-sample predictions month by month for the last BLEND_MONTHS complete months
    start = (asof.to_period("M") - BLEND_MONTHS).to_timestamp()
    oos = []
    for mo in pd.date_range(start, asof.to_period("M").to_timestamp() - pd.Timedelta(days=1), freq="MS"):
        mm = fit_mnlogit(F, cols, mo - pd.Timedelta(days=FIT_WINDOW_DAYS), mo)
        te = F[(F["date"] >= mo) & (F["date"] < mo + pd.offsets.MonthBegin(1))]
        if mm is None or te.empty:
            continue
        p = predict_mnlogit(mm, te)
        oos.append(p.assign(y=_labels(te.loc[p["row_key"]]), date=te.loc[p["row_key"], "date"].to_numpy()))
    O = pd.concat(oos, ignore_index=True) if oos else pd.DataFrame()
    prices = pd.read_parquet(ex / "prices.parquet")
    mk = entry_market(prices)
    blend, oos_rep = None, {}
    if len(O):
        J = O.merge(mk, left_on="row_key", right_on="row_id", how="inner")
        blend = fit_blend(J)
        if len(J):
            y = J["y"].to_numpy().astype(int)
            P = J[[f"p_{k}" for k in OUTCOMES]].to_numpy()
            Mk = J[[f"m_{k}" for k in OUTCOMES]].to_numpy()
            ll = lambda Q: float(-np.log(np.clip(Q[np.arange(len(y)), y], 1e-12, None)).mean())  # noqa: E731
            oos_rep = {"rows_priced": int(len(J)), "logloss_model": ll(P), "logloss_market_entry": ll(Mk),
                       "months": BLEND_MONTHS}
    import sklearn
    artifact = {"model": model, "blend": blend, "elo": {"k": ELO_K, "new_offset": ELO_NEW_OFFSET},
                "sklearn_version": sklearn.__version__,
                "calc_version": CALC_VERSION, "name": MODEL_NAME, "asof": str(asof.date()),
                "v9_commit": meta.get("v9_commit"), "frame_hash": meta.get("frame_hash"),
                "feature_fingerprint": meta["feature_fingerprint"]}
    report = {"name": MODEL_NAME, "calc_version": CALC_VERSION, "asof": str(asof.date()),
              "v9_commit": meta.get("v9_commit"), "frame_hash": meta.get("frame_hash"),
              "feature_fingerprint": meta["feature_fingerprint"], "n_train": model["n_train"],
              "train_window": model["window"], "leagues": model["leagues"],
              "features_kept": len(model["keep"]), "elo": artifact["elo"],
              "blend": ({"n_fit": blend["n_fit"], "coef": blend["coef"]} if blend else None),
              "oos_last_months": oos_rep, "design": __doc__.split("Design")[1].split("A league")[0].strip()}
    return artifact, report


def save(artifact: dict, report: dict) -> None:
    MODEL_FILE.parent.mkdir(exist_ok=True)
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(artifact, f)
    META_FILE.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")


def load() -> dict | None:
    if not MODEL_FILE.exists():
        return None
    with open(MODEL_FILE, "rb") as f:
        return pickle.load(f)


# ── serving ─────────────────────────────────────────────────────────────────────────────────

def serve(artifact: dict, up_dir: str | Path) -> tuple[pd.DataFrame, dict]:
    """Probabilities for the bridge's `upcoming` output. Refuses (empty frame, reason) when the
    v9 feature code differs from the one the model was trained under."""
    up = Path(up_dir)
    meta = json.loads((up / "meta.json").read_text(encoding="utf-8"))
    info = {"bridge": meta.get("reasons", {}), "fingerprint_serving": meta.get("feature_fingerprint"),
            "fingerprint_model": artifact.get("feature_fingerprint")}
    if meta.get("feature_fingerprint") != artifact.get("feature_fingerprint"):
        info["refused"] = "FEATURE_CODE_CHANGED (retrain the 1X2 model on this v9)"
        return pd.DataFrame(), info
    import sklearn
    if sklearn.__version__.split(".")[:2] != str(artifact.get("sklearn_version")).split(".")[:2]:
        info["refused"] = (f"SKLEARN_VERSION_CHANGED (model {artifact.get('sklearn_version')}, "
                           f"here {sklearn.__version__})")
        return pd.DataFrame(), info
    U = pd.read_parquet(up / "upcoming_features.parquet")
    if U.empty:
        return pd.DataFrame(), info
    M = pd.read_parquet(up / "matches.parquet")
    M["date"] = pd.to_datetime(M["date"])
    _, final = elo_state(M, artifact["elo"]["k"], artifact["elo"]["new_offset"])
    U = U.copy()
    U["elo_diff"] = [elo_diff_upcoming(final, lg, h, a, artifact["elo"]["new_offset"])
                     for lg, h, a in zip(U["league"], U["home_team"], U["away_team"])]
    known = U["league"].astype(str).isin(artifact["model"]["leagues"])
    info["league_not_in_training"] = int((~known).sum())
    U = U[known].reset_index(drop=True)
    if U.empty:
        return pd.DataFrame(), info
    p = predict_mnlogit(artifact["model"], U)
    out = U[["fixture_key", "league", "home_team", "away_team"]].loc[p["row_key"]].reset_index(drop=True)
    for k in OUTCOMES:
        out[f"p_{k}"] = p[f"p_{k}"].to_numpy()
    return out, info


def blend_row(artifact: dict, p3, odds3) -> list[float] | None:
    """Blend probabilities for one fixture from its model probabilities and a REAL 3-way price."""
    if not artifact.get("blend"):
        return None
    m = power_devig3(np.asarray(odds3, dtype=float))
    if not np.isfinite(m).all():
        return None
    return predict_blend(artifact["blend"], np.asarray(p3, dtype=float), m)[0].tolist()
