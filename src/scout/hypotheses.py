"""Scout multiple-testing control (owner brief 2026-10-26, E3).

    python -m src.scout.hypotheses            # review every registered hypothesis, print the board

THE PROBLEM. The scout watches ~200 leagues x 4 markets = ~800 league-market cells, and the weekly
review would eventually promote a league whose cell "looks good". Read off a leaderboard, the best
of 800 noisy cells always looks good: at n = 30 the top paper ROI on today's report is +500% on ONE
bet. Promotion feeds v9's auto-onboarding (owner decision: a league that passes is onboarded
automatically, no approval step), so the statistical control has to live IN the criteria.

WHAT THIS ADDS — every item the brief lists:

  explicit hypothesis registry  registry/scout_hypotheses.json, one hypothesis per watched
                                league x market (SCOUT-<league_id>-<market>), registered once,
                                with frozen criteria and their sha256. Changing the criteria is a
                                NEW registry version; a hash mismatch blocks every confirmation
                                (fail closed), so thresholds cannot be tuned after the fact.
  no raw ROI                    the statistic is information, not profit: per settled fixture
                                d = LL(p_close) - LL(p_blend), p_blend = sigmoid(0.75 logit(close)
                                + 0.25 logit(model)) — a PRE-REGISTERED blend, nothing fitted, so
                                no in-sample leakage. d > 0 means the frozen model adds information
                                to the genuine close. ROI is never an input anywhere here.
  genuine close                 the reference price must be OBSERVED within 60 min of kickoff
                                (Pinnacle, else the cross-book median with >= 3 books); a stale
                                carried-forward price is not a close and the fixture is not counted.
  minimum counts                discovery: >= 100 settled & >= 8 matchdays; confirmation: >= 150
                                settled & >= 10 matchdays, on fixtures after the forward start only.
  matchday block bootstrap      fixtures on one matchday share weather, refereeing and market
                                news; they are resampled together (2,000 draws, fixed seed).
                                p is one-sided: Phi-bar(mean / bootstrap SE).
  BH-FDR                        discovery: Benjamini-Hochberg over ALL registered hypotheses
                                (an untestable cell enters with p = 1 — it was on the leaderboard
                                too), q <= 0.20. Confirmation: BH over every hypothesis that has
                                ever entered confirmation, q <= 0.05.
  discovery vs confirmation     passing discovery only sets `confirmation_start` = the review
                                time, WRITE-ONCE. Confirmation uses fixtures kicking off at or
                                after it — data that did not exist when the hypothesis was
                                selected. A hypothesis is never confirmed on the data that
                                selected it.
  leave-one-period-out          the confirmation fixtures are cut into 4 contiguous matchday
                                blocks; the mean with each block left out must stay > 0.
  concentration                 no single matchday may carry > 25% of the summed improvement and
                                no single team > 35%: an "edge" that is one freak weekend or one
                                club's season is not a league property.

States: REGISTERED -> DISCOVERY -> CONFIRMING -> CONFIRMED, or REJECTED (confirmation data say the
model does not help: mean <= 0 once the minimums are met, or no confirmation by twice the minimum).
CONFIRMED is re-evaluated weekly on the growing forward set and can fall back to CONFIRMING.

The weekly promotion review (src/scout/promotion.py) requires >= 1 CONFIRMED market for a league to
reach SHADOW_APPROVED, and the auto-onboard queue requires it again — so a "top 10 leagues"
leaderboard can never be promoted automatically.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.scout import report as R

REGISTRY_FILE = cfg.REGISTRY_DIR / "scout_hypotheses.json"
MARKETS = tuple(R.SIDE)                     # ou15, ou25, ou35, btts

CRITERIA = {
    "version": "scout_mtc-1",
    "statistic": ("per settled fixture d = LL(p_close) - LL(p_blend); p_blend = sigmoid((1-w)*logit(p_close) "
                  "+ w*logit(p_model)); positive = the frozen model adds information to the genuine close; "
                  "the hypothesis is mean(d) > 0"),
    "blend_weight": 0.25,
    "raw_roi_is_an_input": False,
    "genuine_close": {"max_minutes_before_kickoff": 60, "reference": "pinnacle, else median with >= 3 books"},
    "model": "first frozen scout_model row per fixture, frozen before kickoff",
    "bootstrap": {"unit": "matchday (league x kickoff UTC date)", "draws": 2000, "seed": 7,
                  "p_value": "one-sided, normal approximation mean / block-bootstrap SE"},
    "discovery": {"min_settled": 100, "min_matchdays": 8, "bh_q": 0.20,
                  "family": "all registered hypotheses; untestable ones enter with p = 1"},
    "confirmation": {"min_settled": 150, "min_matchdays": 10, "bh_q": 0.05,
                     "family": "all hypotheses that ever entered confirmation; untestable ones p = 1",
                     "one_sided_95_lower_bound_gt_0": True, "lopo_blocks": 4,
                     "lopo_all_leave_one_out_means_gt_0": True,
                     "max_matchday_share": 0.25, "max_team_share": 0.35,
                     "reject_if_mean_le_0_at_minimums": True, "reject_after_settled": 300},
    "forward_start": "confirmation_start = review time when discovery passes; write-once, never backdated",
}


def criteria_sha256(c: dict | None = None) -> str:
    return hashlib.sha256(json.dumps(c or CRITERIA, sort_keys=True).encode("utf-8")).hexdigest()


# ── statistics ────────────────────────────────────────────────────────────────────────────────
def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def improvement(p_close, p_model, y, w: float | None = None) -> np.ndarray:
    w = CRITERIA["blend_weight"] if w is None else w
    blend = 1 / (1 + np.exp(-((1 - w) * _logit(p_close) + w * _logit(p_model))))
    return _ll(p_close, y) - _ll(blend, y)


def block_bootstrap(d: np.ndarray, blocks: np.ndarray, draws: int | None = None,
                    seed: int | None = None) -> dict:
    """Matchday block bootstrap of mean(d). Returns mean, SE, one-sided p (H0: mean <= 0),
    one-sided 95% lower bound and the 90% interval."""
    b = CRITERIA["bootstrap"]
    draws, seed = draws or b["draws"], b["seed"] if seed is None else seed
    df = pd.DataFrame({"d": d, "g": blocks}).groupby("g")["d"].agg(["sum", "count"])
    s, c = df["sum"].to_numpy(), df["count"].to_numpy()
    mean = float(s.sum() / c.sum())
    if len(df) < 2:
        return {"mean": mean, "se": None, "p": 1.0, "lower95": None, "ci90": [None, None]}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(df), size=(draws, len(df)))
    boot = s[idx].sum(1) / c[idx].sum(1)
    se = float(boot.std(ddof=1))
    p = 0.5 * math.erfc((mean / se) / math.sqrt(2)) if se > 0 else (0.0 if mean > 0 else 1.0)
    return {"mean": mean, "se": se, "p": float(p), "lower95": float(np.quantile(boot, 0.05)),
            "ci90": [float(np.quantile(boot, 0.05)), float(np.quantile(boot, 0.95))]}


def bh_qvalues(p: list[float] | np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q), step-up, monotone."""
    p = np.asarray(p, float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.clip(q, 0, 1)
    return out


def lopo(d: np.ndarray, matchdays: np.ndarray, k: int | None = None) -> dict:
    """Leave-one-period-out: k contiguous chronological blocks of matchdays; the mean of d with
    each block left out. Passes when every leave-one-out mean is > 0."""
    k = k or CRITERIA["confirmation"]["lopo_blocks"]
    days = np.array(sorted(set(matchdays)))
    if len(days) < k:
        return {"feasible": False, "pass": False, "leave_one_out_means": []}
    cut = np.array_split(days, k)
    block_of = {dd: i for i, blk in enumerate(cut) for dd in blk}
    b = np.array([block_of[x] for x in matchdays])
    means = [float(d[b != i].mean()) for i in range(k)]
    return {"feasible": True, "pass": bool(all(m > 0 for m in means)),
            "leave_one_out_means": [round(m, 6) for m in means]}


def concentration(d: np.ndarray, matchdays: np.ndarray, home: np.ndarray, away: np.ndarray) -> dict:
    tot = float(d.sum())
    if tot <= 0:
        return {"pass": False, "reason": "no positive total improvement", "top_matchday_share": None,
                "top_team_share": None}
    md = pd.Series(d).groupby(matchdays).sum()
    teams = pd.concat([pd.Series(d, index=home), pd.Series(d, index=away)]).groupby(level=0).sum()
    tm, tt = float(md.max() / tot), float(teams.max() / tot)
    c = CRITERIA["confirmation"]
    return {"pass": bool(tm <= c["max_matchday_share"] and tt <= c["max_team_share"]),
            "top_matchday_share": round(tm, 4), "top_team_share": round(tt, 4)}


# ── evidence table: one row per settled fixture x market with a genuine close and a model ─────
def evidence(res: pd.DataFrame, odds: pd.DataFrame, mdl: pd.DataFrame) -> pd.DataFrame:
    cols = ["fixture_id", "league_id", "market", "kickoff_ts", "matchday", "home_id", "away_id",
            "y", "p_close", "p_model", "d"]
    if res.empty or odds.empty or mdl.empty:
        return pd.DataFrame(columns=cols)
    g = CRITERIA["genuine_close"]
    close = R.closing(odds)
    close = close[close["minutes_to_kickoff"] <= g["max_minutes_before_kickoff"]]
    ok_book = (close["bookmaker"] == "pinnacle") | (
        (close["bookmaker"] == "median")
        & ~close.get("quality_flags", pd.Series("", index=close.index)).fillna("").str.contains("INSUFFICIENT_BOOKS"))
    fair = R.fair_prob(close[ok_book])
    if fair.empty:
        return pd.DataFrame(columns=cols)
    r = (res.sort_values("ingested_at").drop_duplicates("fixture_id", keep="last")
         .dropna(subset=["home_goals", "away_goals"]))
    m0 = mdl.sort_values("frozen_ts").drop_duplicates("fixture_id", keep="first")
    if "kickoff_ts" in m0.columns:
        fz = pd.to_datetime(m0["frozen_ts"], utc=True, errors="coerce")
        ko = pd.to_datetime(m0["kickoff_ts"], unit="s", utc=True, errors="coerce")
        m0 = m0[fz < ko]                                     # prospective only
    out = []
    for m in MARKETS:
        f = fair[fair["market"] == m]
        ref = f[f["bookmaker"] == "pinnacle"].set_index("fixture_id")["p"].combine_first(
            f[f["bookmaker"] == "median"].set_index("fixture_id")["p"])
        col = R.MODEL_COL[m]
        if col not in m0.columns:
            continue
        x = (r.set_index("fixture_id")[["league_id", "kickoff_ts", "home_id", "away_id", "home_goals", "away_goals"]]
             .join(ref.rename("p_close"), how="inner")
             .join(m0.set_index("fixture_id")[[col]].rename(columns={col: "p_model"}), how="inner")
             .dropna(subset=["p_close", "p_model"]))
        if x.empty:
            continue
        x["y"] = R.outcome(m, x["home_goals"].astype(float), x["away_goals"].astype(float))
        x["d"] = improvement(x["p_close"].to_numpy(), x["p_model"].to_numpy(), x["y"].to_numpy())
        x["market"] = m
        x["matchday"] = pd.to_datetime(x["kickoff_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
        out.append(x.reset_index())
    if not out:
        return pd.DataFrame(columns=cols)
    e = pd.concat(out, ignore_index=True)
    e["league_id"] = e["league_id"].astype(int)
    return e[cols]


def stage_stats(e: pd.DataFrame, stage: str) -> dict:
    """Counts, bootstrap and (for confirmation) LOPO + concentration for one hypothesis' rows."""
    c = CRITERIA[stage]
    n, md = int(len(e)), int(e["matchday"].nunique()) if len(e) else 0
    out = {"n": n, "matchdays": md, "testable": n >= c["min_settled"] and md >= c["min_matchdays"]}
    if not out["testable"]:
        out.update({"p": 1.0})
        return out
    d = e["d"].to_numpy()
    bs = block_bootstrap(d, e["matchday"].to_numpy())
    out.update({"mean_d": round(bs["mean"], 6), "se": None if bs["se"] is None else round(bs["se"], 6),
                "p": bs["p"], "lower95": bs["lower95"], "ci90": bs["ci90"]})
    if stage == "confirmation":
        out["lopo"] = lopo(d, e["matchday"].to_numpy())
        out["concentration"] = concentration(d, e["matchday"].to_numpy(),
                                             e["home_id"].to_numpy(), e["away_id"].to_numpy())
    return out


# ── registry ──────────────────────────────────────────────────────────────────────────────────
def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return {"registry": "scout_hypotheses", "version": 1, "criteria": CRITERIA,
            "criteria_sha256": criteria_sha256(), "created_at": cfg.utc_now_iso(),
            "change_policy": "Criteria are frozen by criteria_sha256. Changing any criterion is a NEW "
                             "registry version with new registrations; confirmation_start is write-once.",
            "hypotheses": []}


def save_registry(reg: dict) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, indent=1, sort_keys=False, default=str), encoding="utf-8")


def ensure_registered(reg: dict, leagues: list[dict], now_iso: str) -> int:
    have = {h["id"] for h in reg["hypotheses"]}
    added = 0
    for lg in leagues:
        for m in MARKETS:
            hid = f"SCOUT-{int(lg['id'])}-{m}"
            if hid in have:
                continue
            reg["hypotheses"].append({
                "id": hid, "league_id": int(lg["id"]),
                "league": f"{lg.get('country', '')} {lg.get('name', '')}".strip(), "market": m,
                "registered_at": now_iso, "state": "REGISTERED", "confirmation_start": None,
                "history": []})
            added += 1
    return added


def _set_state(h: dict, new: str, week: str, why: str) -> None:
    if h["state"] != new:
        h["history"].append({"week": week, "from": h["state"], "to": new, "reason": why})
        h["state"] = new


def review(res: pd.DataFrame, odds: pd.DataFrame, mdl: pd.DataFrame, *, leagues: list[dict] | None = None,
           now: pd.Timestamp | None = None, week: str | None = None, save: bool = True) -> dict:
    """Run both stages over every registered hypothesis. Returns {league_id: summary}."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    week = week or now.strftime("%G-W%V")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    reg = load_registry()
    if leagues is None:
        from src.scout import leagues as L
        leagues = L.load()
    ensure_registered(reg, leagues, now_iso)

    blocked = reg.get("criteria_sha256") != criteria_sha256()
    e = evidence(res, odds, mdl)
    hyps = reg["hypotheses"]
    by_key = {k: g for k, g in e.groupby(["league_id", "market"])} if len(e) else {}

    # ---- stage 1: discovery, BH over the WHOLE registered family ---------------------------
    disc = []
    for h in hyps:
        g = by_key.get((h["league_id"], h["market"]), e.iloc[0:0])
        if h.get("confirmation_start"):
            g = g[g["kickoff_ts"] < pd.Timestamp(h["confirmation_start"]).timestamp()]
        disc.append(stage_stats(g, "discovery"))
    q_disc = bh_qvalues([s["p"] for s in disc])
    for h, s, q in zip(hyps, disc, q_disc):
        s["bh_q"] = round(float(q), 6)
        h["discovery"] = s
        if blocked or h["state"] in ("CONFIRMING", "CONFIRMED", "REJECTED"):
            continue
        if s["testable"] and q <= CRITERIA["discovery"]["bh_q"] and s.get("mean_d", 0) > 0:
            h["confirmation_start"] = h.get("confirmation_start") or now_iso    # write-once
            _set_state(h, "CONFIRMING", week, f"discovery BH q={q:.4f} <= {CRITERIA['discovery']['bh_q']}")
        elif s["n"] > 0:
            _set_state(h, "DISCOVERY", week, "accruing discovery evidence")

    # ---- stage 2: confirmation, forward data only, BH over the confirmation family ---------
    fam = [h for h in hyps if h.get("confirmation_start")]
    conf = []
    for h in fam:
        g = by_key.get((h["league_id"], h["market"]), e.iloc[0:0])
        g = g[g["kickoff_ts"] >= pd.Timestamp(h["confirmation_start"]).timestamp()]
        conf.append(stage_stats(g, "confirmation"))
    q_conf = bh_qvalues([s["p"] for s in conf])
    cc = CRITERIA["confirmation"]
    for h, s, q in zip(fam, conf, q_conf):
        s["bh_q"] = round(float(q), 6)
        checks = {
            "min_settled": s["n"] >= cc["min_settled"],
            "min_matchdays": s["matchdays"] >= cc["min_matchdays"],
            "bh_q": bool(s["testable"] and q <= cc["bh_q"]),
            "lower95_gt_0": bool(s.get("lower95") is not None and s["lower95"] > 0),
            "lopo": bool((s.get("lopo") or {}).get("pass")),
            "concentration": bool((s.get("concentration") or {}).get("pass")),
            "criteria_unchanged": not blocked,
        }
        s["checks"] = checks
        h["confirmation"] = s
        if h["state"] == "REJECTED" or blocked:
            continue
        if all(checks.values()):
            _set_state(h, "CONFIRMED", week, f"all confirmation checks pass (BH q={q:.4f})")
        elif s["testable"] and s.get("mean_d", 0) <= 0:
            _set_state(h, "REJECTED", week, "confirmation mean improvement <= 0 at the minimums")
        elif s["n"] >= cc["reject_after_settled"]:
            _set_state(h, "REJECTED", week, f"not confirmed by {cc['reject_after_settled']} settled")
        else:
            _set_state(h, "CONFIRMING", week, "confirmation evidence accruing / checks not all met")

    reg["last_review"] = {"at": now_iso, "week": week, "blocked_criteria_changed": blocked,
                          "n_hypotheses": len(hyps), "evidence_rows": int(len(e)),
                          "state_counts": pd.Series([h["state"] for h in hyps]).value_counts().to_dict()}
    if save:
        save_registry(reg)
    return league_summary(reg)


def league_summary(reg: dict) -> dict:
    out: dict = {}
    for h in reg["hypotheses"]:
        s = out.setdefault(h["league_id"], {"confirmed_markets": [], "confirming_markets": [],
                                            "states": {}, "blocked": reg.get("last_review", {}).get(
                                                "blocked_criteria_changed", False)})
        s["states"][h["market"]] = h["state"]
        if h["state"] == "CONFIRMED" and not s["blocked"]:
            s["confirmed_markets"].append(h["market"])
        if h["state"] == "CONFIRMING":
            s["confirming_markets"].append(h["market"])
    return out


def leaderboard_verdicts(report: dict, summary: dict, top: int = 10) -> list[dict]:
    """What the controlled criteria say about the raw top-`top` cells of the scout report
    (by paper ROI) — the leaderboard that must never promote itself."""
    cells = [c for c in report.get("cells", []) if c.get("paper_roi") is not None]
    cells.sort(key=lambda c: -c["paper_roi"])
    out = []
    for c in cells[:top]:
        s = summary.get(int(c["league_id"]), {})
        out.append({"league": f"{c.get('country')} {c.get('league')}", "market": c["market"], "n": c["n"],
                    "paper_bets": c.get("paper_bets"), "paper_roi": c["paper_roi"],
                    "hypothesis_state": s.get("states", {}).get(c["market"], "UNREGISTERED"),
                    "promotable": c["market"] in s.get("confirmed_markets", [])})
    return out


def main() -> int:
    from src.data import season_store as store
    res, odds, mdl = store.read("scout_results"), store.read("scout_odds"), store.read("scout_model")
    summ = review(res, odds, mdl)
    reg = load_registry()
    print(json.dumps(reg["last_review"], indent=1, default=str))
    rep_f = cfg.OUTPUT_DIR / "scout" / "report.json"
    if rep_f.exists():
        lb = leaderboard_verdicts(json.loads(rep_f.read_text(encoding="utf-8")), summ)
        print("raw paper-ROI top 10 under the controlled criteria:")
        for r in lb:
            print(f"  {r['league']:45} {r['market']:5} n={r['n']:>3} bets={r['paper_bets']} "
                  f"roi={r['paper_roi']:+.2f} -> {r['hypothesis_state']} promotable={r['promotable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
