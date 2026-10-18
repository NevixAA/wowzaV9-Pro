"""MODEL LINEAGE — what each retrain and each champion actually did afterwards (owner 2026-10-18).

    python -m src.analytics.model_lineage --v9 ../v9            # local
    python -m src.analytics.model_lineage --v9 _v9              # CI (read-only v9 checkout)

v9 owns GOVERNANCE (champion gate, registry, lineage records). Pro owns EVALUATION:

    champion_live_performance.csv      each champion era: N, hit, LL, Brier, ROI, CLV, drawdown
    model_version_live_results.csv     per version x market x attribution method
    retrain_batch_results.csv          every retrain decision + what happened in its future window
    retrain_week_table.csv             the owner's Week 32 / 33 / 34 table, from real data
    challenger_shadow_results.csv      parked challenger vs champion on the SAME future fixtures
    weekly_model_performance.csv       ISO week x model x version (WEEKLY_RESULT_VARIANCE_HIGH)
    model_churn.csv                    attempts, promotions, churn rate, champion lifetimes
    promotion_vs_future.csv            did a promotion's holdout gain show up in live results?
    champion_health.csv                HEALTHY / WATCH / DEGRADED / STALE + the evidence
    current_champions_view.csv         dashboard view: champion, bar, challenger, next action
    answers.json, MODEL_LINEAGE_REPORT.md

ATTRIBUTION (brief §22). A bet belongs to the model that GENERATED it:
    RECORDED               the ledger row carries model_version (written since 2026-10-18)
    RECONSTRUCTED_BY_TIME  legacy row; generated_at falls inside one champion era (eras from v9's
                           git-reconstructed champion_history)
    AMBIGUOUS_BOUNDARY     legacy row within 60 min after an era started: a predict job that
                           checked out before the retrain commit still ran the old model.
                           Excluded from per-version results; counted.
    UNKNOWN_LEGACY         before the first recorded era
Nothing here writes a version into a v9 ledger.

READ ONLY against v9. No selection, threshold, stake or BET_ENABLED is read for a decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics import core
from src.data.entities import norm_name

OUT = Path(__file__).resolve().parents[2] / "output" / "model_lineage"
BOUNDARY = pd.Timedelta(minutes=60)
MATERIAL_LL = 0.001        # the v9 gate's bar (src/champion_gate.py)
WEEK_FLAG = "WEEKLY_RESULT_VARIANCE_HIGH"

#: ledger market -> v9 model type
MARKET_MODEL = {"BTTS": "btts", "OVER15": "over15", "OVER35": "over35"}
#: h2h market -> outcome from full-time goals (HT models cannot be graded: no HT scores in Pro)
OUTCOME = {"over25": lambda h, a: (h + a) > 2.5, "btts": lambda h, a: (h > 0) & (a > 0),
           "over15": lambda h, a: (h + a) > 1.5, "over35": lambda h, a: (h + a) > 3.5}


# ── loading ──────────────────────────────────────────────────────────────────────────────────
def _csv(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p, low_memory=False) if p.exists() else pd.DataFrame()
    except Exception:                                                  # noqa: BLE001
        return pd.DataFrame()


def _json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                                  # noqa: BLE001
        return {}


def load_v9(v9: Path) -> dict:
    lin = v9 / "output" / "model_lineage"
    return {"history": _csv(lin / "champion_history.csv"),
            "batches": _csv(lin / "retrain_batches.csv"),
            "replay": _csv(lin / "legacy_gate_replay.csv"),
            "h2h": _csv(lin / "shadow_h2h.csv"),
            "high_water": _json(lin / "high_water_mark.json"),
            "pointer": _json(v9 / "models" / "registry" / "current_champions.json")}


def model_of(row_market: str, row_model: str) -> str | None:
    m = str(row_market).upper()
    if m == "OU25":
        return "newformat" if str(row_model) == "new_format" else "standard"
    if m in MARKET_MODEL:
        return MARKET_MODEL[m]
    if m.startswith("HT_"):
        return "ht_over15" if m.endswith("15") else "ht_over05"
    return None


# ── eras and attribution ─────────────────────────────────────────────────────────────────────
def eras(history: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """One row per champion era. end = the next champion's start (append-only history)."""
    if history.empty:
        return pd.DataFrame(columns=["model_type", "champion_version", "start", "end"])
    h = history.copy()
    h["start"] = pd.to_datetime(h["start_at"], utc=True, errors="coerce")
    h = h.sort_values(["model_type", "start"], kind="mergesort")
    h["end"] = h.groupby("model_type")["start"].shift(-1).fillna(now)
    return h.reset_index(drop=True)


def attribute(bets: pd.DataFrame, er: pd.DataFrame) -> pd.DataFrame:
    b = bets.copy()
    b["model_key"] = [model_of(m, t) for m, t in zip(b["market"], b["model"])]
    rec = b.get("model_version", pd.Series("", index=b.index)).fillna("").astype(str)
    rec = rec.where(~rec.isin(["nan", "UNKNOWN_LEGACY"]), "")
    b["version"], b["attribution_method"] = rec, np.where(rec != "", "RECORDED", "")
    by_type = {k: g for k, g in er.groupby("model_type")}
    for i in b.index[b["attribution_method"] == ""]:
        g = by_type.get(b.at[i, "model_key"])
        t = b.at[i, "generated_at"]
        if g is None or pd.isna(t):
            b.at[i, "attribution_method"] = "UNKNOWN_LEGACY"
            continue
        hit = g[(g["start"] <= t) & (t < g["end"])]
        if hit.empty:
            b.at[i, "attribution_method"] = "UNKNOWN_LEGACY"
            continue
        e = hit.iloc[-1]
        prev_exists = (g["start"] < e["start"]).any()
        if prev_exists and t - e["start"] < BOUNDARY:
            b.at[i, "attribution_method"] = "AMBIGUOUS_BOUNDARY"
        else:
            b.at[i, "attribution_method"] = "RECONSTRUCTED_BY_TIME"
        b.at[i, "version"] = e["champion_version"]
    return b


# ── metrics ──────────────────────────────────────────────────────────────────────────────────
def _ll(y, p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def bet_metrics(g: pd.DataFrame) -> dict:
    """Flat 1u, first-sight bets. LL/Brier here are on SELECTED bets (the probability of the bet
    side) — a biased sample; the unbiased model score is the graded h2h log."""
    n = len(g)
    if n == 0:
        return {"N": 0}
    wl = g[g["result"].isin(["WIN", "LOSS"])]
    p = pd.to_numeric(wl["model_p"], errors="coerce")
    ok = p.between(0.001, 0.999)
    y = (wl["result"] == "WIN").astype(float)
    clv = g["clv"].dropna()
    dd = core.drawdown(g)
    return {"N": n, "W": int(g["win"].sum()), "L": int(g["loss"].sum()),
            "accuracy": float(g["win"].sum() / max(1, g["win"].sum() + g["loss"].sum())),
            "logloss_bets": float(_ll(y[ok], p[ok]).mean()) if ok.any() else np.nan,
            "brier_bets": float(((p[ok] - y[ok]) ** 2).mean()) if ok.any() else np.nan,
            "pnl_units": float(g["pnl"].sum()), "roi": float(g["pnl"].sum() / n),
            "clv_n": int(len(clv)), "avg_clv": float(clv.mean()) if len(clv) else np.nan,
            "positive_clv_share": float((clv > 0).mean()) if len(clv) else np.nan,
            "league_count": int(g["league"].nunique()), "market_count": int(g["market"].nunique()),
            "max_drawdown": dd.get("max_drawdown_units", np.nan),
            "first_prediction": str(g["generated_at"].min())[:16],
            "last_prediction": str(g["generated_at"].max())[:16]}


# ── h2h grading ──────────────────────────────────────────────────────────────────────────────
def _tokens(s) -> set:
    return {t for t in norm_name(s).split() if len(t) > 2}


def grade_h2h(h2h: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Attach the full-time outcome to each h2h row. League-scoped, same date (±1 day), both
    clubs must share identity tokens. Unmatched rows stay ungraded and are counted."""
    if h2h.empty or results.empty:
        return h2h.assign(y=np.nan, graded=False)
    r = results.dropna(subset=["home_goals", "away_goals"]).copy()
    r["d"] = pd.to_datetime(r["match_date"], errors="coerce").dt.normalize()
    r["ht"], r["at"] = r["home_team"].map(_tokens), r["away_team"].map(_tokens)
    by = {k: g for k, g in r.groupby("league")}
    out = h2h.copy()
    ys = []
    for row in out.itertuples(index=False):
        f = OUTCOME.get(str(row.market))
        g = by.get(row.league)
        y = np.nan
        if f is not None and g is not None:
            d = pd.Timestamp(str(row.match_date)[:10])
            c = g[(g["d"] - d).abs() <= pd.Timedelta(days=1)]
            th, ta = _tokens(row.home_team), _tokens(row.away_team)
            c = c[[bool(th & x) and bool(ta & z) for x, z in zip(c["ht"], c["at"])]]
            if len(c) == 1:
                y = float(f(c["home_goals"].iloc[0], c["away_goals"].iloc[0]))
        ys.append(y)
    out["y"] = ys
    out["graded"] = out["y"].notna()
    return out


def _day_boot_ci(delta: np.ndarray, days: np.ndarray, seed: int = 20261018) -> tuple:
    by = pd.DataFrame({"d": days, "x": delta}).groupby("d")["x"].agg(["sum", "size"])
    if len(by) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(by), size=(2000, len(by)))
    m = by["sum"].to_numpy()[idx].sum(1) / by["size"].to_numpy()[idx].sum(1)
    return (float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975)))


def shadow_results(graded: pd.DataFrame) -> pd.DataFrame:
    """Champion vs challenger on the identical graded fixtures, per parked challenger."""
    rows = []
    if graded.empty or "challenger_version" not in graded.columns:
        return pd.DataFrame()
    g0 = graded[graded["challenger_version"].fillna("").astype(str) != ""]
    for (mt, ch), g in g0.groupby(["model_type", "challenger_version"]):
        gg = g[g["graded"] & g["p_champion_raw"].notna() & g["p_challenger"].notna()]
        r = {"model_type": mt, "challenger_version": ch,
             "champion_version": g["champion_version"].iloc[0],
             "fixtures_logged": len(g), "graded_n": len(gg)}
        if len(gg):
            y = gg["y"].to_numpy(float)
            pc, pn = gg["p_champion_raw"].to_numpy(float), gg["p_challenger"].to_numpy(float)
            dl = _ll(y, pn) - _ll(y, pc)
            lo, hi = _day_boot_ci(dl, gg["match_date"].astype(str).to_numpy())
            r.update(ll_champion=float(_ll(y, pc).mean()), ll_challenger=float(_ll(y, pn).mean()),
                     delta_logloss=float(dl.mean()), delta_ci_lo=lo, delta_ci_hi=hi,
                     delta_brier=float(((pn - y) ** 2).mean() - ((pc - y) ** 2).mean()),
                     calib_gap_champion=float(pc.mean() - y.mean()),
                     calib_gap_challenger=float(pn.mean() - y.mean()),
                     delta_roi_sim="NOT_AVAILABLE: h2h rows carry no price",
                     verdict_so_far=("CHALLENGER_AHEAD" if hi < 0 else "CHAMPION_AHEAD" if lo > 0
                                     else "UNRESOLVED") if hi == hi else "TOO_FEW_DAYS")
        rows.append(r)
    return pd.DataFrame(rows)


# ── main ─────────────────────────────────────────────────────────────────────────────────────
def _chg(a, c, k):
    """Change in metric k from era a to era c; NaN unless both eras have bets."""
    if not (a.get("N", 0) or 0) or not (c.get("N", 0) or 0):
        return np.nan
    return float(c.get(k)) - float(a.get(k))


def build(v9: Path, results: pd.DataFrame | None = None, now: pd.Timestamp | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    src = load_v9(v9)
    er = eras(src["history"], now)

    raw = core.load_raw(v9)
    first, _stats = core.first_sight(raw)
    s = core.settle(first)
    s = s[s["tier"].isin(list(core.TIERS) + ["HT"])]
    b = attribute(s, er) if len(s) else s.assign(model_key=None, version="", attribution_method="")

    # champion live performance (strict: RECORDED + RECONSTRUCTED_BY_TIME)
    strict = b[b["attribution_method"].isin(["RECORDED", "RECONSTRUCTED_BY_TIME"])]
    champ_rows = []
    for e in er.itertuples(index=False):
        g = strict[(strict["model_key"] == e.model_type) & (strict["version"] == e.champion_version)]
        r = {"model_type": e.model_type, "model_version": e.champion_version,
             "champion_start": str(e.start)[:16], "champion_end": "" if e.end == now
             else str(e.end)[:16], "era_days": round((e.end - e.start).total_seconds() / 86400, 2),
             "reconstructed": e.reconstructed}
        r.update(bet_metrics(g))
        r["notes"] = ("eras before 2026-10-18 are reconstructed from git commit times"
                      if str(e.reconstructed) in ("True", "true") else "")
        champ_rows.append(r)
    champ = pd.DataFrame(champ_rows)

    ver_rows = []
    for (mk, v, am, mkt), g in b.groupby(["model_key", "version", "attribution_method", "market"],
                                         dropna=False):
        r = {"model_type": mk, "model_version": v or "UNKNOWN_LEGACY", "attribution_method": am,
             "market": mkt}
        r.update(bet_metrics(g))
        ver_rows.append(r)
    by_version = pd.DataFrame(ver_rows)

    # retrain decisions -> future windows
    bt = src["batches"].copy()
    rb_rows = []
    if not bt.empty:
        bt["t"] = pd.to_datetime(bt["decided_at"], utc=True, errors="coerce")
        bt = bt.sort_values(["model_type", "t"], kind="mergesort")
        bt["t_next"] = bt.groupby("model_type")["t"].shift(-1)
        for r in bt.itertuples(index=False):
            end = r.t_next if pd.notna(r.t_next) else now
            g = strict[(strict["model_key"] == r.model_type) & (strict["generated_at"] >= r.t)
                       & (strict["generated_at"] < end)]
            m = bet_metrics(g)
            rb_rows.append({
                "retrain_batch_id": r.retrain_batch_id, "iso_week": r.t.strftime("%G-W%V")
                if pd.notna(r.t) else "", "decided_at": str(r.t)[:16], "model_type": r.model_type,
                "challenger_version": r.challenger_version, "verdict": r.verdict,
                "promoted": r.promoted, "champion_after": r.champion_after,
                "ll_delta_at_decision": r.ll_delta, "ll_ci_lo": r.ll_ci_lo, "ll_ci_hi": r.ll_ci_hi,
                "training_rows": r.training_rows, "future_result_start": str(r.t)[:16],
                "future_result_end": "" if pd.isna(r.t_next) else str(r.t_next)[:16],
                "future_N": m.get("N", 0), "future_W": m.get("W"), "future_L": m.get("L"),
                "future_accuracy": m.get("accuracy"), "future_logloss_bets": m.get("logloss_bets"),
                "future_brier_bets": m.get("brier_bets"), "future_roi": m.get("roi"),
                "future_clv": m.get("avg_clv"), "future_positive_clv_share": m.get("positive_clv_share"),
                "status": "OPEN" if pd.isna(r.t_next) else "CLOSED", "source": r.source})
    rb = pd.DataFrame(rb_rows)
    if not rb.empty:
        rb["rows_added_since_prior"] = rb.groupby("model_type")["training_rows"].diff()

    # the owner's week table
    week = pd.DataFrame()
    if not rb.empty:
        dec = {"LEGACY_PROMOTED": "PROMOTED (old rule)", "LEGACY_BLOCKED": "BLOCKED (old rule)",
               "PROMOTE": "PROMOTE", "KEEP_CHAMPION": "KEEP", "SHADOW_MORE": "SHADOW"}
        week = rb.assign(decision=rb["verdict"].map(dec).fillna(rb["verdict"]))[
            ["iso_week", "decided_at", "model_type", "challenger_version", "verdict", "decision",
             "ll_delta_at_decision", "future_N", "future_accuracy", "future_logloss_bets",
             "future_roi", "future_clv", "champion_after", "status"]]

    # h2h
    graded = grade_h2h(src["h2h"], results if results is not None else pd.DataFrame())
    shadow = shadow_results(graded)

    # weekly snapshot
    wk_rows = []
    if len(strict):
        st = strict.assign(iso_week=strict["date"].dt.strftime("%G-W%V"))
        for (w, mk, v), g in st.groupby(["iso_week", "model_key", "version"]):
            m = bet_metrics(g)
            h = graded[(graded.get("champion_version", pd.Series(dtype=str)) == v)] if len(graded) else graded
            wk_rows.append({"iso_week": w, "model_type": mk, "version_active": v,
                            "predictions_logged": int(len(h)) if len(h) else 0,
                            "settled": m["N"], "wins": m.get("W"), "losses": m.get("L"),
                            "accuracy": m.get("accuracy"), "logloss_bets": m.get("logloss_bets"),
                            "brier_bets": m.get("brier_bets"), "roi": m.get("roi"),
                            "clv": m.get("avg_clv"), "flag": WEEK_FLAG})
    weekly = pd.DataFrame(wk_rows)

    # churn
    churn_rows = []
    if not bt.empty:
        for (mt, regime), g in bt.assign(regime=np.where(bt["source"].astype(str).str.startswith(
                "LEGACY"), "LEGACY_RULE", "CHAMPION_GATE")).groupby(["model_type", "regime"]):
            d = pd.to_numeric(g["ll_delta"], errors="coerce")
            prom = g["promoted"].astype(str).str.lower().isin(["true", "1"])
            e = er[er["model_type"] == mt]
            life = (e["end"] - e["start"]).dt.total_seconds() / 86400
            churn_rows.append({
                "model_type": mt, "regime": regime, "retrain_attempts": len(g),
                "promotions": int(prom.sum()),
                "keep_or_blocked": int(g["verdict"].isin(["KEEP_CHAMPION", "LEGACY_BLOCKED"]).sum()),
                "shadow": int((g["verdict"] == "SHADOW_MORE").sum()),
                "MODEL_CHURN_RATE": float(prom.mean()),
                "mean_ll_delta": float(d.mean()), "median_ll_delta": float(d.median()),
                "materially_worse": int((d > MATERIAL_LL).sum()),
                "statistically_tied_pointwise": int((d.abs() <= MATERIAL_LL).sum()),
                "promoted_while_worse": int((prom & (d > 0)).sum()),
                "MEAN_CHAMPION_LIFETIME_DAYS": float(life.mean()) if len(life) else np.nan,
                "MEDIAN_CHAMPION_LIFETIME_DAYS": float(life.median()) if len(life) else np.nan})
    churn = pd.DataFrame(churn_rows)

    # promotion vs future
    pvf_rows = []
    if not champ.empty:
        for mt, g in champ.sort_values("champion_start").groupby("model_type"):
            g = g.reset_index(drop=True)
            for i in range(1, len(g)):
                a, c = g.iloc[i - 1], g.iloc[i]
                pvf_rows.append({"model_type": mt, "promoted_version": c["model_version"],
                                 "prior_version": a["model_version"],
                                 "prior_N": a.get("N", 0), "new_N": c.get("N", 0),
                                 "roi_change": _chg(a, c, "roi"),
                                 "accuracy_change": _chg(a, c, "accuracy"),
                                 "evidence": "INSUFFICIENT" if min(a.get("N", 0) or 0,
                                                                   c.get("N", 0) or 0) < 50 else "USABLE"})
    pvf = pd.DataFrame(pvf_rows)

    # health
    hw, ptr = src["high_water"], src["pointer"]
    health_rows, view_rows = [], []
    for mt, p in sorted(ptr.items()):
        v = p.get("model_version", "")
        since = pd.to_datetime(p.get("champion_since"), utc=True, errors="coerce")
        hg = graded[(graded.get("model_type", pd.Series(dtype=str)) == mt) & graded["graded"]
                    & (graded.get("champion_version", pd.Series(dtype=str)) == v)] if len(graded) else graded
        hg = hg.drop_duplicates(["match_date", "home_team", "away_team"]) if len(hg) else hg
        n = int(len(hg))
        cal = float(hg["p_served"].astype(float).mean() - hg["y"].mean()) if n else np.nan
        pll = float(_ll(hg["y"], hg["p_served"].astype(float)).mean()) if n else np.nan
        ref = ((hw.get(mt) or {}).get("current_regime") or {}).get("log_loss")
        gap = pll - ref if (n and ref is not None) else np.nan
        age = (now - since).days if pd.notna(since) else None
        sh = shadow[shadow["model_type"] == mt] if len(shadow) else shadow
        ahead = bool(len(sh) and (sh.get("verdict_so_far") == "CHALLENGER_AHEAD").any())
        if n < 150:
            state, why = "HEALTHY", f"not assessable yet: {n} graded prospective fixtures (< 150)"
        elif n >= 300 and ((gap == gap and gap > 0.02) or abs(cal) > 0.05):
            state, why = "DEGRADED", f"prospective LL gap {gap:+.4f}, calibration gap {cal:+.3f}"
        elif (gap == gap and gap > 0.01) or abs(cal) > 0.03:
            state, why = "WATCH", f"prospective LL gap {gap:+.4f}, calibration gap {cal:+.3f}"
        elif age is not None and age > 90 and ahead:
            state, why = "STALE", f"champion {age} days old and a shadow challenger is ahead"
        else:
            state, why = "HEALTHY", f"n={n}, LL gap {gap:+.4f}, calibration gap {cal:+.3f}"
        health_rows.append({"model_type": mt, "champion_version": v, "champion_age_days": age,
                            "prospective_graded_n": n, "prospective_logloss": pll,
                            "holdout_logloss_ref": ref, "logloss_gap": gap,
                            "calibration_gap": cal, "challenger_ahead": ahead,
                            "CHAMPION_HEALTH": state, "evidence": why})
        live = champ[(champ["model_type"] == mt) & (champ["model_version"] == v)] if len(champ) else champ
        last = (src["batches"][src["batches"]["model_type"] == mt].tail(1)
                if not src["batches"].empty else pd.DataFrame())
        lc = (hw.get(mt) or {}).get("last_challenger") or {}
        cur = (hw.get(mt) or {}).get("current_regime") or {}
        status = lc.get("verdict") or (last["verdict"].iloc[0] if len(last) else "")
        view_rows.append({
            "model_type": mt, "current_champion": v, "champion_since": p.get("champion_since"),
            "training_cutoff": p.get("training_cutoff") or "unknown (legacy)",
            "validated_ll": cur.get("log_loss"), "brier": cur.get("brier"),
            "fresh_oos_ll": cur.get("log_loss"),
            "prospective_n": n, "live_N": int(live["N"].iloc[0]) if len(live) and "N" in live else 0,
            "live_roi": float(live["roi"].iloc[0]) if len(live) and "roi" in live and live["N"].iloc[0] else np.nan,
            "live_clv": float(live["avg_clv"].iloc[0]) if len(live) and "avg_clv" in live and live["N"].iloc[0] else np.nan,
            "current_challenger": lc.get("version", ""), "challenger_status": status,
            "delta_vs_champion": lc.get("ll_delta"),
            "champion_health": state,
            "next_action": {"SHADOW_MORE": "shadow: collect graded head-to-head fixtures",
                            "KEEP_CHAMPION": "keep champion; next retrain tries again",
                            "PROMOTE": "new champion serving; watch health"}.get(
                status, "first CHAMPION_GATE retrain pending (next Sunday)")
            if state not in ("DEGRADED", "STALE") else "owner review: champion health " + state})
    health, view = pd.DataFrame(health_rows), pd.DataFrame(view_rows)

    # answers
    attempts = len(bt)
    prom = int(bt["promoted"].astype(str).str.lower().isin(["true", "1"]).sum()) if attempts else 0
    rej = int(bt["verdict"].isin(["KEEP_CHAMPION", "LEGACY_BLOCKED"]).sum()) if attempts else 0
    shd = int((bt["verdict"] == "SHADOW_MORE").sum()) if attempts else 0
    rp = src["replay"]
    proven = pd.DataFrame()
    if not rp.empty:
        proven = rp[(pd.to_numeric(rp["ci_hi"], errors="coerce") < 0)
                    & (pd.to_numeric(rp["delta"], errors="coerce") <= -MATERIAL_LL)]
    best = ("NONE — no promotion so far was backed by a same-holdout CI excluding zero"
            if proven.empty or not proven["legacy_promoted"].astype(str).str.lower().eq("true").any()
            else proven.sort_values("delta").iloc[0].to_dict())
    if isinstance(best, str) and not proven.empty:
        x = proven.sort_values("delta").iloc[0]
        best += (f"; strongest CI-backed gain was {x['model_type']} {x['date']} "
                 f"{float(x['delta']):+.5f} (CI hi {float(x['ci_hi']):+.5f}), "
                 f"{'promoted' if str(x['legacy_promoted']).lower() == 'true' else 'NOT promoted by the old rule'}")
    attr = b["attribution_method"].value_counts().to_dict() if len(b) else {}
    answers = {
        "CURRENT_CHAMPION_BY_MODEL": {k: v.get("model_version") for k, v in sorted(ptr.items())},
        "RETRAIN_ATTEMPTS_ANALYZED": attempts, "PROMOTIONS": prom, "REJECTIONS": rej,
        "SHADOW_DECISIONS": shd,
        "MODEL_CHURN_RATE": round(prom / attempts, 3) if attempts else None,
        "BEST_PROVEN_CHAMPION_IMPROVEMENT": best,
        "LEGACY_GATE_REPLAY": (rp.groupby(["legacy_promoted", "new_gate_replay"]).size()
                               .rename("n").reset_index().to_dict("records") if not rp.empty else []),
        "BET_ATTRIBUTION": attr,
        "H2H_ROWS": int(len(graded)), "H2H_GRADED": int(graded["graded"].sum()) if len(graded) else 0,
        "CHAMPION_HEALTH": dict(zip(health.get("model_type", []), health.get("CHAMPION_HEALTH", []))),
        "GENERATED_AT": str(now)[:19],
    }
    return {"eras": er, "champion_live_performance": champ, "model_version_live_results": by_version,
            "retrain_batch_results": rb, "retrain_week_table": week,
            "challenger_shadow_results": shadow, "weekly_model_performance": weekly,
            "model_churn": churn, "promotion_vs_future": pvf, "champion_health": health,
            "current_champions_view": view, "champion_history": src["history"],
            "answers": answers}


def load_results() -> pd.DataFrame:
    """Pro's own settled scorelines (season store). Empty if unavailable — grading then waits."""
    root = Path(__file__).resolve().parents[2] / "data"
    parts = []
    for p in sorted(root.glob("season_*/team_match_stats")):
        try:
            parts.append(pd.read_parquet(p, columns=["league", "match_date", "home_team",
                                                     "away_team", "home_goals", "away_goals"]))
        except Exception:                                              # noqa: BLE001
            continue
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _md(df: pd.DataFrame) -> str:
    """Markdown table without the optional `tabulate` dependency (not installed in CI)."""
    cols = [str(c) for c in df.columns]
    fmt = lambda v: "" if (v is None or (isinstance(v, float) and v != v)) else str(v)  # noqa: E731
    rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    rows += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(rows)


def report_md(r: dict) -> str:
    a = r["answers"]
    L = ["# Model lineage — champion high-water mark", "",
         f"Generated {a['GENERATED_AT']} UTC. Read-only against v9.", "",
         "Weekly realised results swing with football. What must not regress is the validated "
         "quality of the model in production. One week never demotes a champion "
         f"(`{WEEK_FLAG}`).", "", "## Current champions", ""]
    v = r["current_champions_view"]
    if len(v):
        L += [v[["model_type", "current_champion", "champion_since", "challenger_status",
                 "champion_health", "next_action"]].pipe(_md), ""]
    L += ["## Retrain decisions", "",
          f"- attempts analysed: **{a['RETRAIN_ATTEMPTS_ANALYZED']}**, promotions "
          f"**{a['PROMOTIONS']}**, kept/blocked **{a['REJECTIONS']}**, shadow "
          f"**{a['SHADOW_DECISIONS']}**, churn rate **{a['MODEL_CHURN_RATE']}**",
          f"- best proven champion improvement: {a['BEST_PROVEN_CHAMPION_IMPROVEMENT']}", ""]
    c = r["model_churn"]
    if len(c):
        L += [c[["model_type", "regime", "retrain_attempts", "promotions", "MODEL_CHURN_RATE",
                 "promoted_while_worse", "MEDIAN_CHAMPION_LIFETIME_DAYS"]].round(3)
              .pipe(_md), ""]
    w = r["retrain_week_table"]
    if len(w):
        L += ["## Retrain → future results (latest 21)", "",
              w.tail(21).round(4).pipe(_md), ""]
    L += ["## Bet attribution", "", json.dumps(a["BET_ATTRIBUTION"]), "",
          "Legacy rows are attributed by timestamp to git-reconstructed champion eras. Rows "
          "within 60 minutes after an era started are AMBIGUOUS_BOUNDARY and excluded.", "",
          "## Head-to-head shadow", "",
          f"{a['H2H_ROWS']} logged rows, {a['H2H_GRADED']} graded. The log started 2026-10-18.", ""]
    s = r["challenger_shadow_results"]
    if len(s):
        L += [s.round(5).pipe(_md), ""]
    return "\n".join(L)


def write(r: dict, out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for k, v in r.items():
        if isinstance(v, pd.DataFrame) and k not in ("eras", "champion_history"):
            v.to_csv(out / f"{k}.csv", index=False)
    (out / "answers.json").write_text(json.dumps(r["answers"], indent=2, default=str),
                                      encoding="utf-8")
    (out / "MODEL_LINEAGE_REPORT.md").write_text(report_md(r), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", default="_v9")
    args = ap.parse_args()
    res = build(Path(args.v9), results=load_results())
    write(res)
    print(json.dumps(res["answers"], indent=2, default=str))
