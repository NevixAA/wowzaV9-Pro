"""WOWZA Longshot Profit Engine - master plan evidence (owner brief 2026-10-18). PLAN ONLY.

    python -m src.analytics.longshot_plan      # -> output/longshot_plan/<date>/ (xlsx + md + proposed json)

"Longshot" = long-term profit, not long odds. The engine decides ONLY where real money may go:
BET_ENABLED per gate. It never changes what Wowza collects, predicts, settles, researches or retrains on:
every league keeps full tracking, and every bet a gate would block stays paper-tracked so the filter can
be judged (profit saved AND profit missed). Nothing here is wired into production.

GATES: league, model, market (model|market), side (model|market|side), odds band (model|market|band), cell
(league|model|market|side). A bet is real-money eligible only if EVERY gate it belongs to allows it.

RULES - fixed before results were looked at (2026-10-18):
  shrunk ROI      = N / (N + K) x ROI with K = 100, i.e. shrunk toward break-even (conservative)
  FALSE           N >= 30 and shrunk ROI <= 0 and shrunk recent ROI (since 2026-09-24) <= 0
                  OR N >= 15 and the 90% ROI interval (match-day bootstrap) is entirely below zero
  TRUE            N >= 30 and shrunk ROI > 0 (and not FALSE)
  REVIEW          otherwise - REVIEW never blocks: disabling money needs evidence ("fast to protect,
                  slow to add risk" applies to ADDING risk; an unknown gate keeps today's behaviour)
PROFIT_EVIDENCE_SCORE (0-100) = 50 + 50 x weighted sum of bounded components:
  0.35 shrunk ROI / 10%   0.15 shrunk recent ROI / 10%   0.15 CI sign (+1 above 0, -1 below)
  0.10 avg CLV / 3%       0.10 V11 toward-minus-placebo / 5pp (league gates)   0.05 V11 residual helps
  0.10 drawdown penalty (-1 when max drawdown > 25% of the gate's bets in units)
WALK-FORWARD: for each month M from 2026-09, every gate is decided on data BEFORE M only, frozen, and the
month's bets are scored kept vs blocked; baselines over the same months.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.analytics import core as C
from src.analytics import deep_wowza_snapshot as D

K = 100
RECENT_FROM = "2026-09-24"
GATES = {"league": ["league"], "model": ["model"], "market": ["model", "market"], "side": ["model", "market", "side"],
         "odds": ["model", "market", "odds_band"], "cell": ["league", "model", "market", "side"]}
STAKE_BANDS = [0, 0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175, 0.02]


def _ci_lo_hi(g: pd.DataFrame) -> tuple:
    if len(g) < 15 or g["day"].nunique() < 5:
        return (np.nan, np.nan)
    b = C._boot(g)
    return b.get("roi_ci_lo_90", np.nan), b.get("roi_ci_hi_90", np.nan)


def gate_table(s: pd.DataFrame, by: list[str], v11: pd.DataFrame | None = None, recent_from: str = RECENT_FROM) -> pd.DataFrame:
    rows = []
    for key, g in s.groupby(by, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        n, roi = len(g), float(g["pnl"].mean())
        r = g[g["date"] >= pd.Timestamp(recent_from)]
        sh = n / (n + K) * roi
        rsh = len(r) / (len(r) + K) * float(r["pnl"].mean()) if len(r) else 0.0
        lo, hi = _ci_lo_hi(g)
        dd = C.drawdown(g).get("max_drawdown_units", 0.0)
        clv = float(g["clv"].mean()) if g["clv"].notna().any() else np.nan
        if (n >= 30 and sh <= 0 and rsh <= 0) or (n >= 15 and hi == hi and hi < 0):
            flag = "FALSE"
        elif n >= 30 and sh > 0:
            flag = "TRUE"
        else:
            flag = "REVIEW"
        row = {**dict(zip(by, key)), "N": n, "days": g["day"].nunique(), "PnL": float(g["pnl"].sum()), "ROI": roi,
               "shrunk_ROI": sh, "recent_N": len(r), "recent_ROI": float(r["pnl"].mean()) if len(r) else np.nan,
               "shrunk_recent_ROI": rsh, "ROI_CI_LO_90": lo, "ROI_CI_HI_90": hi, "avg_CLV": clv,
               "max_drawdown_units": dd, "hit_rate": float(g["win"].mean()), "avg_odds": float(g["odds"].mean()),
               "candidate_BET_ENABLED": flag}
        tm = toward_res = np.nan
        if v11 is not None and by == ["league"] and len(v11):
            v = v11[v11["league"] == key[0]]
            if len(v):
                tm = v["toward_minus_placebo"].iloc[0]
                toward_res = 1.0 if bool(v["wowza_helps"].iloc[0]) is True else -1.0 if pd.notna(v["wowza_helps"].iloc[0]) else np.nan
                row.update({"V11_toward": v["toward_rate"].iloc[0], "V11_toward_minus_placebo": tm,
                            "V11_residual_helps": v["wowza_helps"].iloc[0], "V11_CLV": v["mean_clv_pct"].iloc[0],
                            "convergence_class": v["convergence_class"].iloc[0]})
        comp = (0.35 * np.clip(sh / 0.10, -1, 1) + 0.15 * np.clip(rsh / 0.10, -1, 1)
                + 0.15 * (1 if lo == lo and lo > 0 else -1 if hi == hi and hi < 0 else 0)
                + 0.10 * (np.clip(clv / 0.03, -1, 1) if clv == clv else 0)
                + 0.10 * (np.clip(tm / 0.05, -1, 1) if tm == tm else 0) + 0.05 * (toward_res if toward_res == toward_res else 0)
                + 0.10 * (-1 if dd > 0.25 * n else 0))
        row["PROFIT_EVIDENCE_SCORE"] = round(50 + 50 * comp, 1)
        row["confidence"] = C.confidence_label(n)
        row["candidate_stake_band"] = stake_band(row["PROFIT_EVIDENCE_SCORE"], flag)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("PROFIT_EVIDENCE_SCORE", ascending=False).reset_index(drop=True)


def stake_band(pes: float, flag: str) -> float:
    """Planned bounded stake (fraction of bankroll) by evidence score. 0 when FALSE; max 2%."""
    if flag == "FALSE":
        return 0.0
    i = int(np.clip(np.floor((pes - 40) / 7.5) + 1, 0, len(STAKE_BANDS) - 1))
    return STAKE_BANDS[i]


def prepare(s: pd.DataFrame) -> pd.DataFrame:
    s = s.copy()
    s["odds_band"] = C.band(s["odds"], C.ODDS_BANDS).fillna("unknown")
    s["side"] = s["side"].fillna("")
    return s


def eligible(s: pd.DataFrame, flags: dict[str, pd.DataFrame]) -> pd.Series:
    """True where every gate the bet belongs to is TRUE or REVIEW (i.e. not FALSE)."""
    ok = pd.Series(True, index=s.index)
    reason = pd.Series("", index=s.index)
    for name, by in GATES.items():
        f = flags[name]
        bad = f[f["candidate_BET_ENABLED"] == "FALSE"][by]
        if bad.empty:
            continue
        m = s[by].astype(str).merge(bad.astype(str).assign(_x=1), on=by, how="left")["_x"].notna().to_numpy()
        reason = reason.where(~(m & reason.eq("")), name)
        ok &= ~m
    return ok, reason


def flags_for(s: pd.DataFrame, v11: pd.DataFrame | None, recent_from: str) -> dict:
    return {n: gate_table(s, by, v11, recent_from) for n, by in GATES.items()}


def walk_forward(s: pd.DataFrame, v11: pd.DataFrame | None, months: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, bets = [], []
    for m in months:
        start = pd.Timestamp(m + "-01")
        end = start + pd.offsets.MonthEnd(0)
        train, test = s[s["date"] < start], s[(s["date"] >= start) & (s["date"] <= end)]
        if test.empty or len(train) < 100:
            continue
        recent = (start - pd.Timedelta(days=30)).strftime("%Y-%m-%d")          # "recent" = the month before
        F = flags_for(train, None, recent)                                     # no V11: it is not as-of
        ok, why = eligible(test, F)
        t = test.assign(kept=ok.to_numpy(), blocked_by=why.to_numpy(), month=m)
        bets.append(t)
        for lab, x in (("ALL", t), ("KEPT (real money)", t[t.kept]), ("BLOCKED (paper only)", t[~t.kept])):
            rows.append({"month": m, "subset": lab, "N": len(x), "PnL": float(x["pnl"].sum()),
                         "ROI": float(x["pnl"].mean()) if len(x) else np.nan,
                         "max_drawdown_units": C.drawdown(x).get("max_drawdown_units", np.nan) if len(x) else np.nan,
                         "avg_CLV": float(x["clv"].mean()) if x["clv"].notna().any() else np.nan})
    return pd.DataFrame(rows), (pd.concat(bets, ignore_index=True) if bets else pd.DataFrame())


def baselines(s: pd.DataFrame, wf_bets: pd.DataFrame, policy: dict, tip_ranker: dict, months: list[str]) -> pd.DataFrame:
    w = s[s["date"] >= pd.Timestamp(months[0] + "-01")]
    tracks = policy.get("tracks", {})

    def in_policy(r):
        t = tracks.get(f"{r['model']}|{r['market']}", {})
        return (t.get("state") in ("ACTIVE", "ACTIVE_LOW") and r["tier"] in C.CORE_TIERS
                and float(t.get("min_odds") or 1) <= r["odds"] <= float(t.get("max_odds") or 99))
    sets = {"ALL NON-MLS (all tiers)": w, "ALL CORE": w[w.tier.isin(C.CORE_TIERS)],
            "ALL NEW_FORMAT": w[w.model == "new_format"], "NEW_FORMAT BTTS": w[(w.model == "new_format") & (w.market == "BTTS")],
            "CURRENT BALANCED POLICY": w[w.apply(in_policy, axis=1)] if len(w) else w,
            "SNIPER ONLY": w[w.tier == "SNIPER"],
            "LONGSHOT ENGINE (walk-forward kept)": wf_bets[wf_bets.kept] if len(wf_bets) else wf_bets,
            "LONGSHOT ENGINE, core tiers only": wf_bets[wf_bets.kept & wf_bets.tier.isin(C.CORE_TIERS)] if len(wf_bets) else wf_bets}
    rows = []
    for name, x in sets.items():
        dd = C.drawdown(x).get("max_drawdown_units", np.nan) if len(x) else np.nan
        pnl = float(x["pnl"].sum())
        rows.append({"strategy": name, "window": f"{months[0]}-01 -> latest", "N": len(x), "PnL": pnl,
                     "ROI": float(x["pnl"].mean()) if len(x) else np.nan, "max_drawdown_units": dd,
                     "return_over_drawdown": pnl / dd if dd and dd == dd and dd > 0 else np.nan})
    for k in ("VALUE", "SHORTEST_ODDS"):
        e = (tip_ranker or {}).get("lists", {}).get(k)
        if e:
            rows.append({"strategy": f"Top Picks {k} (tip_ranker backtest, top 5/day, own window)", "window": "days with >=10 tips",
                         "N": e.get("picks"), "ROI": e.get("roi"), "PnL": (e.get("roi") or 0) * (e.get("picks") or 0)})
    return pd.DataFrame(rows)


def hypotheses(s: pd.DataFrame, v11: pd.DataFrame) -> pd.DataFrame:
    w = s[s["date"] >= pd.Timestamp("2026-08-26")]
    core = w[w.tier.isin(C.CORE_TIERS)]
    r = lambda x: (len(x), float(x["pnl"].mean()) if len(x) else np.nan, float(x["pnl"].sum()))  # noqa: E731
    out = []

    def add(h, text, a, b=None, verdict=""):
        out.append({"hypothesis": h, "statement": text, "N_a": a[0], "ROI_a": a[1], "PnL_a": a[2],
                    "N_b": b[0] if b else None, "ROI_b": b[1] if b else None, "verdict": verdict})
    nf, st = r(core[core.model == "new_format"]), r(core[core.model == "standard"])
    add("H1", "new_format stronger than standard (core)", nf, st, "SUPPORTED" if nf[1] > st[1] else "NOT SUPPORTED")
    mm = core.groupby(["model", "market"])["pnl"].agg(["size", "mean"]); big = mm[mm["size"] >= 100]
    add("H2", "new-format BTTS is the strongest large track", r(core[(core.model == "new_format") & (core.market == "BTTS")]),
        verdict="SUPPORTED" if len(big) and big["mean"].idxmax() == ("new_format", "BTTS") else "NOT SUPPORTED")
    nfou = core[(core.model == "new_format") & (core.market == "OU25")]
    a, b = r(nfou[nfou.date < RECENT_FROM]), r(nfou[nfou.date >= RECENT_FROM])
    add("H3", "new-format OU25 improved in the recent regime (before vs since 09-24)", a, b, "SUPPORTED" if b[1] > a[1] else "NOT SUPPORTED")
    sou = r(core[(core.model == "standard") & (core.market == "OU25")])
    add("H4", "standard OU25 is a major current drag", sou, verdict="SUPPORTED" if sou[2] < -5 else "NOT SUPPORTED")
    su, so = r(core[(core.model == "standard") & (core.market == "OU25") & (core.side == "UNDER")]), r(core[(core.model == "standard") & (core.market == "OU25") & (core.side == "OVER")])
    add("H5", "standard UNDER especially weak (vs standard OVER)", su, so, "SUPPORTED" if su[1] < so[1] else "NOT SUPPORTED")
    no, nu = r(nfou[nfou.side == "OVER"]), r(nfou[nfou.side == "UNDER"])
    add("H6", "new-format OVER outperforms new-format UNDER", no, nu, "SUPPORTED" if no[1] > nu[1] else "NOT SUPPORTED")
    b25 = r(nfou[(nfou.odds >= 2.25) & (nfou.odds < 2.50)])
    add("H7", "new-format OU25 at 2.25-2.49 especially strong (vs rest of NF OU25)", b25, r(nfou[(nfou.odds < 2.25) | (nfou.odds >= 2.50)]),
        "SUPPORTED" if b25[0] >= 20 and b25[1] > 0.10 else "WEAK/UNCLEAR")
    ou = w[w.market == "OU25"]
    l1, l2 = r(ou[ou.odds >= 2.75]), r(ou[ou.odds >= 3.00])
    add("H8", "OU25 at 2.75+ (a) / 3.00+ (b) destructive (all tiers)", l1, l2, "SUPPORTED" if l1[1] < -0.05 else "NOT SUPPORTED")
    conv = v11[v11["convergence_class"] == "STRONG_CONVERGENCE"]["league"].tolist() if len(v11) else []
    add("H9", f"Japan/Mexico/Finland/Serie B show outcome+market convergence; V11 STRONG_CONVERGENCE = {conv}", (0, np.nan, 0),
        verdict="PARTLY SUPPORTED" if conv else "NOT SUPPORTED")
    arg = v11[v11["league"] == "Argentina Primera Division"] if len(v11) else pd.DataFrame()
    add("H10", "Argentina profit without V11 movement confirmation", r(w[w.league == "Argentina Primera Division"]),
        verdict=(f"V11 class {arg['convergence_class'].iloc[0]}, toward-minus-placebo {arg['toward_minus_placebo'].iloc[0]:+.3f}" if len(arg) else "no V11 row"))
    eng = w[w.league.isin(["Championship", "League One", "League Two"]) & (w.model == "standard")]
    e = r(eng)
    add("H11", "Championship / League One / League Two standard markets: BET_ENABLED=FALSE candidates", e,
        verdict="SUPPORTED" if e[1] < 0 else "NOT SUPPORTED")
    return pd.DataFrame(out)


def build() -> dict:
    I = D.load_inputs()
    s = prepare(I["s"])
    U = C.universes(s, cfg.PAPER_LEAGUES, I["policy"])
    pool = U["NON_MLS"]                                                      # every prediction that could get money
    T = D.build_tables(I)
    v11 = T["V11_League"] if "convergence_class" in T["V11_League"].columns else pd.DataFrame()
    F = flags_for(pool, v11, RECENT_FROM)
    months = sorted(m for m in pool["month"].unique() if m >= "2026-09")
    wf, wf_bets = walk_forward(pool, v11, months)
    base = baselines(pool, wf_bets, I["policy"], I["tip_ranker"], months)
    ok, why = eligible(pool, F)
    paper = pool[~ok].assign(blocked_by=why[~ok])
    since = paper[paper.date >= pd.Timestamp(RECENT_FROM)]
    false_paper = (paper.groupby("blocked_by").agg(N=("pnl", "size"), PnL=("pnl", "sum"), ROI=("pnl", "mean"),
                                                   avg_CLV=("clv", "mean")).reset_index())
    reen = []
    for name, f in F.items():
        for _, row in f[f["candidate_BET_ENABLED"] == "FALSE"].iterrows():
            score = 50 + 50 * (0.5 * np.clip((row["shrunk_recent_ROI"] or 0) / 0.05, -1, 1)
                               + 0.3 * np.clip((row["recent_ROI"] if row["recent_ROI"] == row["recent_ROI"] else 0) / 0.10, -1, 1)
                               + 0.2 * (np.clip(row["avg_CLV"] / 0.03, -1, 1) if row["avg_CLV"] == row["avg_CLV"] else 0))
            gate = " | ".join(str(row[c]) for c in GATES[name])
            reen.append({"gate_level": name, "gate": gate, "N": row["N"], "ROI": row["ROI"], "recent_N": row["recent_N"],
                         "recent_paper_ROI": row["recent_ROI"], "avg_CLV": row["avg_CLV"], "re_enable_evidence_score": round(score, 1),
                         "RE_ENABLE_CANDIDATE": bool(row["recent_N"] >= 20 and (row["recent_ROI"] or -1) > 0.05),
                         "recommended_action": ("watch: recent paper ROI positive - review after next retrain" if (row["recent_ROI"] or -1) > 0
                                                else "keep FALSE, keep collecting and predicting")})
    R = pd.DataFrame(reen).sort_values("re_enable_evidence_score", ascending=False) if reen else pd.DataFrame()
    # stress: bootstrap season PnL of the CURRENTLY eligible pool by match days
    kept = pool[ok]
    days = kept.groupby("day")["pnl"].sum().to_numpy()
    rng = np.random.default_rng(20261018)
    n_days = int(round(len(days) / max(1, (kept["date"].max() - kept["date"].min()).days + 1) * C.SEASON_DAYS)) if len(days) else 0
    sims = rng.choice(days, size=(5000, max(1, n_days))).sum(1) if len(days) else np.array([0.0])
    top = kept.groupby("league")["pnl"].sum().idxmax() if len(kept) else ""
    stress = pd.DataFrame([{"test": "season PnL, bootstrap of eligible match days (5,000 seasons)", "p05": np.quantile(sims, 0.05),
                            "median": np.median(sims), "p95": np.quantile(sims, 0.95), "P(loss)": float((sims < 0).mean())},
                           {"test": f"eligible pool without top profit league ({top})",
                            "median": float(kept[kept.league != top]["pnl"].sum()), "P(loss)": np.nan},
                           {"test": "eligible pool without Argentina", "median": float(kept[kept.league != "Argentina Primera Division"]["pnl"].sum())}])
    seasons = pd.DataFrame([{"row": n, **C.projection(x, "2026-08-26", RECENT_FROM, I["end"])}
                            for n, x in (("eligible pool (Longshot candidates)", kept), ("all non-MLS (status quo, all tiers)", pool),
                                         ("core (status quo)", pool[pool.tier.isin(C.CORE_TIERS)]))])
    return {"I": I, "F": F, "wf": wf, "wf_bets": wf_bets, "base": base, "false_paper": false_paper, "reen": R,
            "stress": stress, "seasons": seasons, "hyp": hypotheses(s, v11), "paper_recent": since, "pool": pool, "ok": ok}


def to_md(P: dict) -> str:
    F, wf, base, R, hyp = P["F"], P["wf"], P["base"], P["reen"], P["hyp"]
    lst = lambda f, flag, cols: [" | ".join(str(r[c]) for c in cols) for _, r in f[f.candidate_BET_ENABLED == flag].iterrows()]  # noqa: E731
    t = {k: lst(F["league"], k, ["league"]) for k in ("TRUE", "FALSE", "REVIEW")}
    mm_false = lst(F["market"], "FALSE", ["model", "market"])
    side_false = lst(F["side"], "FALSE", ["model", "market", "side"])
    odds_false = lst(F["odds"], "FALSE", ["model", "market", "odds_band"])
    reen = R[R.RE_ENABLE_CANDIDATE]["gate"].tolist() if len(R) else []
    agg = wf.groupby("subset")[["N", "PnL"]].sum() if len(wf) else pd.DataFrame()
    blocked = float(agg.loc["BLOCKED (paper only)", "PnL"]) if "BLOCKED (paper only)" in agg.index else 0.0
    wfb = P["wf_bets"]
    saved = -float(wfb[~wfb.kept & (wfb.pnl < 0)]["pnl"].sum()) if len(wfb) else 0.0
    missed = float(wfb[~wfb.kept & (wfb.pnl > 0)]["pnl"].sum()) if len(wfb) else 0.0
    bb = base.set_index("strategy")
    rod = lambda k: float(bb.loc[k, "PnL"] / bb.loc[k, "max_drawdown_units"]) if k in bb.index and bb.loc[k, "max_drawdown_units"] else np.nan  # noqa: E731
    eng = rod("LONGSHOT ENGINE (walk-forward kept)")
    simple = {k: rod(k) for k in ("CURRENT BALANCED POLICY", "ALL NEW_FORMAT", "NEW_FORMAT BTTS", "SNIPER ONLY", "ALL CORE")}
    best_simple = max(simple, key=lambda k: simple[k] if simple[k] == simple[k] else -9)
    beats = eng == eng and all(eng > v for v in simple.values() if v == v)
    P["_verdict"] = {"FILTER_BEATS_SIMPLE_BASELINES": "YES" if beats else "NO", "best_simple": best_simple,
                     "engine_return_over_dd": eng, "best_simple_return_over_dd": simple[best_simple]}
    L = ["# WOWZA LONGSHOT PROFIT ENGINE — MASTER PLAN", "",
         f"Evidence to {P['I']['end'].date()} · first-sight bets · plan only, nothing wired into production.", "",
         "> NEVER STOP LEARNING. `BET_ENABLED` decides only where real money may go. Every league keeps collecting, "
         "predicting, settling, CLV, V11, Pro research and retraining data exactly as today, and every bet a gate blocks "
         "stays paper-tracked.", "",
         "## 1. Executive summary",
         f"- Walk-forward (flags set on data before each month, frozen, then scored): blocked bets made **{blocked:+.2f}u** "
         f"in total — gross losses avoided {saved:.2f}u, gross wins forgone {missed:.2f}u. A negative blocked total means the filter helped.",
         *[f"- {r.strategy}: N {int(r.N or 0)}, PnL {r.PnL:+.2f}u, ROI {r.ROI:+.1%}" + (f", max DD {r.max_drawdown_units:.1f}u" if r.max_drawdown_units == r.max_drawdown_units else "")
           for r in base.itertuples() if r.PnL == r.PnL and r.ROI == r.ROI],
         f"- **VERDICT: FILTER_BEATS_SIMPLE_BASELINES = {P['_verdict']['FILTER_BEATS_SIMPLE_BASELINES']}.** Return/drawdown: "
         f"engine {eng:.2f} vs best simple baseline '{best_simple}' {simple[best_simple]:.2f}. By section 32 the gate filter is "
         "NOT adopted; the flags below are candidates to keep evaluating monthly, not decisions.",
         "- Walk-forward covers only 2 months: treat it as the first check, not proof. NEXT STEP: keep the walk-forward running monthly before any real staking change.", "",
         "## 2-3. Profit map / loss map", "See CURRENT_WINNERS / CURRENT_LOSERS sheets (cells N>=30 ranked by evidence score).", "",
         "## 4. League bet eligibility", f"- TRUE candidates: {t['TRUE']}", f"- FALSE candidates: {t['FALSE']}", f"- REVIEW (not enough evidence; stays as today): {t['REVIEW']}", "",
         "## 5-8. Model / market / side / odds eligibility", f"- model|market FALSE: {mm_false}", f"- side FALSE: {side_false}",
         f"- odds band FALSE: {odds_false}", "",
         "## 9. Cell-level eligibility", "CELL_BET_FLAGS sheet: league x model x market x side, the narrowest justified restriction.", "",
         "## 10-11. Profit evidence score and shrinkage", "Documented in the module docstring and the PROFIT_EVIDENCE_SCORE sheet: "
         "shrunk ROI (K=100 toward break-even) leads, raw ROI never decides alone; +50% at n=10 scores far below +8% at n=300.", "",
         "## 12. V11 confirmation", "League gates add V11 toward-minus-placebo and residual; a league is not 'strong' because toward > 50%.", "",
         "## 13-14. Portfolio and staking bands", "One real position per fixture (highest evidence gate wins; the others stay paper). "
         "Stake bands 0-2% by evidence score (PORTFOLIO_PLAN). League rating (1-10) already scales stakes down; both stay under existing caps.", "",
         "## 15. Walk-forward", "WALK_FORWARD_PLAN sheet: month-by-month kept vs blocked; repeat every month; a filter that does not beat the simple baselines risk-adjusted is not adopted.", "",
         "## 16. Paper tracking of disabled bets", "FALSE_FLAG_PAPER_RESULTS: every blocked bet keeps probability, odds, result, flat PnL, CLV and the blocking gate.", "",
         "## 17. Retrain re-enable engine", f"RE_ENABLE_CANDIDATES (priority): {reen or 'none yet'}. After every meaningful retrain, re-score all FALSE gates on chronological OOS evidence; candidate -> shadow -> owner approval.", "",
         "## 18-19. Stress tests and season scenarios", "STRESS_TEST_PLAN and SEASON_SCENARIOS sheets. " + D.DISCLAIMER, "",
         "## 20. Implementation architecture", "Proposed `betting_eligibility.json` (one file, read by the staking layer only: v9 stake plan + wowza-exec). "
         "Collection, prediction, settlement, research and retraining never read it. Draft: betting_eligibility_PROPOSED.json.", "",
         "## 21. Owner approval gates", "Any TRUE/FALSE production change, any re-enable, any stake-band change: owner approval. The plan executes none.", "",
         "## Hypotheses", *[f"- {r.hypothesis}: {r.statement} — {r.verdict}" for r in hyp.itertuples()], "",
         "## Final summary", "```",
         "MASTER_PLAN_CREATED = YES", "PRODUCTION_CHANGES_EXECUTED = NO", "ALL_EXISTING_LEAGUES_CONTINUE_TRACKING = YES",
         "ALL_EXISTING_LEAGUES_CONTINUE_DATA_COLLECTION = YES", "ALL_EXISTING_LEAGUES_CONTINUE_RESEARCH = YES",
         "HISTORICAL_DATA_REMOVED = NO", "BET_ENABLED_FLAG_PLANNED = YES", "FALSE_BETS_CONTINUE_PAPER_TRACKING = YES",
         "FALSE_LEAGUES_CONTINUE_RETRAIN_DATA = YES", "RETRAIN_CAN_TRIGGER_REENABLE_REVIEW = YES", "MODEL_THRESHOLDS_CHANGED = NO",
         "PREDICTION_LOGIC_CHANGED = NO", "BANKROLL_CHANGED = NO", "",
         f"BET_ENABLED_TRUE_CANDIDATES = {t['TRUE']}", f"BET_ENABLED_FALSE_CANDIDATES = {t['FALSE']}",
         f"MODEL_MARKET_FALSE_CANDIDATES = {mm_false}", f"SIDE_FALSE_CANDIDATES = {side_false}",
         f"ODDS_BAND_FALSE_CANDIDATES = {odds_false}", f"RE_ENABLE_PRIORITY_CANDIDATES = {reen}",
         f"FILTER_BEATS_SIMPLE_BASELINES = {P['_verdict']['FILTER_BEATS_SIMPLE_BASELINES']} (best simple: {best_simple})",
         "NEXT_STEP = WALK_FORWARD VALIDATE BET_ENABLED FILTER BEFORE TOUCHING REAL STAKING", "```"]
    return "\n".join(L) + "\n"


def write(P: dict, out: Path) -> None:
    from openpyxl import Workbook
    F = P["F"]
    cells = F["cell"]
    sheets = {
        "EXEC_SUMMARY": pd.DataFrame({"line": to_md(P).splitlines()}),
        "LEAGUE_BET_FLAGS": F["league"].assign(current_BET_ENABLED="TRUE (no flag exists yet)",
                                               next_review="after next retrain / monthly walk-forward"),
        "MODEL_BET_FLAGS": F["model"], "MARKET_BET_FLAGS": F["market"], "SIDE_BET_FLAGS": F["side"],
        "ODDS_BET_FLAGS": F["odds"], "CELL_BET_FLAGS": cells,
        "CURRENT_WINNERS": cells[cells.N >= 30].nlargest(15, "PROFIT_EVIDENCE_SCORE"),
        "CURRENT_LOSERS": cells[cells.N >= 30].nsmallest(15, "PROFIT_EVIDENCE_SCORE"),
        "PROFIT_EVIDENCE_SCORE": pd.concat([f.assign(gate_level=k) for k, f in F.items()], ignore_index=True),
        "FALSE_FLAG_PAPER_RESULTS": P["false_paper"], "RE_ENABLE_CANDIDATES": P["reen"],
        "RETRAIN_IMPROVEMENT": D.retrain_table(P["I"]),
        "PORTFOLIO_PLAN": pd.DataFrame([("one real position per fixture", "highest PROFIT_EVIDENCE_SCORE gate wins; others paper"),
                                        ("stake bands", "0 / 0.25 / 0.50 / 0.75 / 1.00 / 1.25 / 1.50 / 1.75 / 2.00 % by evidence score; FALSE = 0"),
                                        ("max single position", "2% (existing hard cap)"),
                                        ("concentration", "league <= 3%/day, league x market <= 3%/day, daily <= 6% (existing policy caps)"),
                                        ("tier", "an input to the evidence score, never the stake by itself"),
                                        ("probability for EV", "future: logit(P) = logit(P_market) + validated Wowza residual; raw edge_pct display-only"),
                                        ("price ceilings", "market-specific MIN/MAX odds from the odds-band evidence, not one universal limit")],
                                       columns=["rule", "plan"]),
        "SEASON_SCENARIOS": P["seasons"], "WALK_FORWARD_PLAN": P["wf"], "BASELINES": P["base"],
        "STRESS_TEST_PLAN": P["stress"], "HYPOTHESES": P["hyp"],
        "IMPLEMENTATION_ROADMAP": pd.DataFrame([(1, "Monthly walk-forward of this filter (Pro, automated)", "no production change"),
                                                (2, "betting_eligibility.json in v9 config, read ONLY by stake plan + wowza-exec", "owner approval"),
                                                (3, "blocked bets logged as paper with blocking gate (already true: ledgers keep everything)", "none"),
                                                (4, "re-enable recheck after every retrain (chronological OOS old vs new)", "Pro study"),
                                                (5, "market-anchored EV replaces raw edge for staking", "separate validation"),
                                                (6, "any TRUE/FALSE flip in production", "owner approval each time")],
                                               columns=["step", "action", "gate"]),
    }
    wb = Workbook(); wb.remove(wb.active)
    from openpyxl.styles import Font, PatternFill
    for name, df in sheets.items():
        ws = wb.create_sheet(name[:31])
        df = df if df is not None and len(df) else pd.DataFrame([{"STATUS": "INSUFFICIENT_DATA"}])
        for j, c in enumerate(df.columns, 1):
            x = ws.cell(row=1, column=j, value=str(c)); x.font, x.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F2937")
            ws.column_dimensions[x.column_letter].width = min(40, max(10, len(str(c)) + 2))
        for i, row in enumerate(df.itertuples(index=False), 2):
            for j, v in enumerate(row, 1):
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    v = None
                elif isinstance(v, (np.integer, np.floating, np.bool_)):
                    v = v.item()
                elif isinstance(v, pd.Timestamp):
                    v = v.to_pydatetime().replace(tzinfo=None)
                c = ws.cell(row=i, column=j, value=v)
                col = df.columns[j - 1]
                if isinstance(v, float) and ("ROI" in col or "CLV" in col or "toward" in col):
                    c.number_format = "0.0%"
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    wb.save(out)


def main() -> int:
    P = build()
    day = str(P["I"]["end"].date())
    out = cfg.OUTPUT_DIR / "longshot_plan" / day
    out.mkdir(parents=True, exist_ok=True)
    write(P, out / f"WOWZA_Longshot_Profit_Engine_Plan_{day}.xlsx")
    md = to_md(P)
    (out / "WOWZA_LONGSHOT_PROFIT_ENGINE_MASTER_PLAN.md").write_text(md, encoding="utf-8")
    prop = {"_status": "PROPOSED - NOT WIRED. Read only by the staking layer (v9 stake plan, wowza-exec) once approved; "
                       "collection, prediction, settlement, research and retraining never read it.",
            "generated_from": day,
            "leagues": {r["league"]: {"bet_enabled": r["candidate_BET_ENABLED"] != "FALSE", "candidate": r["candidate_BET_ENABLED"],
                                      "reason": f"N {r['N']}, shrunk ROI {r['shrunk_ROI']:+.3f}, PES {r['PROFIT_EVIDENCE_SCORE']}",
                                      "review_after_retrain": True} for _, r in P["F"]["league"].iterrows()},
            "gates_false": {k: [" | ".join(str(r[c]) for c in GATES[k]) for _, r in f[f.candidate_BET_ENABLED == "FALSE"].iterrows()]
                            for k, f in P["F"].items()}}
    (out / "betting_eligibility_PROPOSED.json").write_text(json.dumps(prop, indent=1), encoding="utf-8")
    for k, f in P["F"].items():
        f.to_csv(out / f"flags_{k}.csv", index=False)
    P["wf"].to_csv(out / "walk_forward.csv", index=False)
    P["base"].to_csv(out / "baselines.csv", index=False)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
