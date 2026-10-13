"""Monthly bankroll review — the entrypoint the workflow calls.

    python -m src.bankroll.run [--as-of YYYY-MM-DD]

Steps: evidence freshness -> current production policy (v9 config/bankroll_policy.json) ->
prospective record -> track evidence -> proposed adaptive policy -> 8 candidate policies replayed
and resampled -> stress tests -> walk-forward test of the allocator itself -> BEST_GROWTH,
BEST_SURVIVAL, RECOMMENDED -> versioned artifacts (+ the exact file a v9 PR would carry).

OBJECTIVE (documented, fixed 2026-10-13), per candidate on the full prospective record:
    score = log_growth - 1.0 * max_drawdown - 2.0 * P(maxDD > 20%) - 0.5 * concentration
            - 0.5 * instability
  concentration = share of staked P/L from the single best league (0..1, capped)
  instability   = standard deviation of monthly returns
SURVIVAL CONSTRAINTS (brief 25): P(maxDD>20%) <= 5%, P(bankroll<75) <= 5%, P(bankroll<50) <= 1%.
BEST_GROWTH  = highest median resampled ending bankroll among candidates passing survival.
BEST_SURVIVAL = lowest P(maxDD>10%) among candidates with positive median log growth.
RECOMMENDED: while the allocator is NOT walk-forward validated (>= 6 evaluated months beating flat
  and static Balanced on return/maxDD), it is the CURRENT policy with only the proposal's risk
  REDUCTIONS applied. After validation: the proposed policy if it passes survival, else SAFE.
"""
from __future__ import annotations

import argparse
import copy
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.bankroll import CALC_VERSION, PERFORMANCE_CUTOFF, RELIABLE_FROM, SURVIVAL
from src.bankroll import allocator as A
from src.bankroll import data as BD
from src.bankroll import simulate as S

OUT = cfg.OUTPUT_DIR / "bankroll"
MIN_WF_MONTHS = 6


def flat(base: dict, frac: float, name: str) -> dict:
    """Naive comparator: stake `frac` on every staked tip of every non-blocked track."""
    p = copy.deepcopy(base)
    p.update(policy_version=name, tier_multipliers={"SNIPER": 1.0, "MARKSMAN": 1.0},
             convergence={"multiplier": 1.0, "leagues": []})
    p["portfolio"] = {**p["portfolio"], "one_position_per_fixture": False, "daily_cap": 0.075,
                      "league_daily_cap": 0.04, "league_market_daily_cap": 0.03}
    for k, t in p["tracks"].items():
        if t.get("state") not in ("BLOCKED", "BLOCKED_FROM_REAL"):
            p["tracks"][k] = {"state": "ACTIVE", "base_fraction": frac, "max_odds": 2.75, "evidence_score": 0}
    return p


def safe(base: dict) -> dict:
    p = copy.deepcopy(base)
    p["policy_version"] = "safe"
    p["portfolio"]["daily_cap"] = 0.04
    for t in p["tracks"].values():
        if float(t.get("base_fraction", 0)) > 0:
            t["base_fraction"] = max(0.0025, A._down(float(t["base_fraction"]), 2))
    return p


BALANCED_PATH = None  # the initial owner policy = v9's committed file at the time of first install


def _score(m: dict, r: dict, conc: float, inst: float) -> float:
    return round(m.get("log_growth", 0) - 1.0 * m.get("max_dd", 0) - 2.0 * r.get("p_maxdd_gt_20", 0)
                 - 0.5 * conc - 0.5 * inst, 4)


def _conc_inst(bets: pd.DataFrame, pol: dict, path: pd.DataFrame) -> tuple[float, float]:
    plans = S.day_plans(bets, pol)
    s = pd.concat([x.assign(_f=plans[d][1.0]) for d, x in bets.groupby("date", sort=True)])
    pl = (s["_f"] * s["unit"]).groupby(s["league"]).sum()
    conc = float(min(1.0, pl.max() / pl[pl > 0].sum())) if (pl > 0).any() else 0.0
    if path.empty:
        return conc, 0.0
    p = path.assign(d=pd.to_datetime(path["date"]))
    b = np.r_[100.0, p["bankroll"].to_numpy(float)]
    p["r"] = np.diff(b) / b[:-1]
    mo = p.groupby(p["d"].dt.to_period("M"))["r"].apply(lambda x: float(np.prod(1 + x) - 1))
    return conc, float(mo.std()) if len(mo) > 1 else 0.0


def evaluate(bets: pd.DataFrame, cands: dict, n_paths: int = 2000) -> pd.DataFrame:
    rows = []
    for name, pol in cands.items():
        plans = S.day_plans(bets, pol)
        path, m = S.replay(bets, pol, plans=plans)
        r = S.risk(bets, pol, n_paths=n_paths, block="day", plans=plans)
        rw = S.risk(bets, pol, n_paths=max(500, n_paths // 4), block="week", plans=plans)
        conc, inst = _conc_inst(bets, pol, path)
        surv = (r.get("p_maxdd_gt_20", 1) <= SURVIVAL["p_dd20"] and r.get("p_below_75", 1) <= SURVIVAL["p_below75"]
                and r.get("p_below_50", 1) <= SURVIVAL["p_below50"])
        rows.append({"policy": name, "version": pol.get("policy_version"), **m,
                     **{f"risk_{k}": v for k, v in r.items() if k not in ("block", "paths")},
                     **{f"week_{k}": v for k, v in rw.items() if k not in ("block", "paths")},
                     "concentration": round(conc, 3), "instability": round(inst, 4),
                     "passes_survival": bool(surv), "score": _score(m, r, conc, inst)})
    return pd.DataFrame(rows)


def walk_forward(bets: pd.DataFrame, start_policy: dict, v11: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Month N policy chosen with evidence before month N only, then applied to month N."""
    months = sorted(bets["month"].unique())
    prev = copy.deepcopy(start_policy)
    rows, bank = [], {"ADAPTIVE": 100.0, "STATIC_BALANCED": 100.0, "FLAT_0.5": 100.0,
                      "FLAT_1": 100.0, "FLAT_2": 100.0}
    for m in months[1:]:
        as_of = pd.Period(m).start_time
        prop, _, _ = A.propose(prev, bets, as_of, v11)
        mb = bets[bets["month"] == m]
        pols = {"ADAPTIVE": prop, "STATIC_BALANCED": start_policy, "FLAT_0.5": flat(start_policy, 0.005, "f05"),
                "FLAT_1": flat(start_policy, 0.01, "f1"), "FLAT_2": flat(start_policy, 0.02, "f2")}
        for k, pol in pols.items():
            _, met = S.replay(mb, pol)
            bank[k] *= 1 + met.get("return_pct", 0) / 100
            rows.append({"month": m, "policy": k, "month_return_pct": met.get("return_pct"),
                         "month_max_dd": met.get("max_dd"), "bankroll": round(bank[k], 2),
                         "chosen_with_data_before": as_of.strftime("%Y-%m-%d")})
        prev = prop
    wf = pd.DataFrame(rows)
    n = len(months) - 1
    verdict = {"months_evaluated": n, "required": MIN_WF_MONTHS,
               "status": "VALIDATED" if n >= MIN_WF_MONTHS and _wf_beats(wf) else
                         ("NOT_VALIDATED_INSUFFICIENT_MONTHS" if n < MIN_WF_MONTHS else "NOT_VALIDATED_UNDERPERFORMS")}
    return wf, verdict


def _wf_beats(wf: pd.DataFrame) -> bool:
    last = wf.groupby("policy")["bankroll"].last()
    dd = wf.groupby("policy")["month_max_dd"].max()
    ra = (last - 100) / dd.replace(0, np.nan)
    others = ra.drop("ADAPTIVE", errors="ignore")
    return bool(ra.get("ADAPTIVE", -9) >= others.max() and dd.get("ADAPTIVE", 1) <= dd.get("STATIC_BALANCED", 1) + 0.02)


def _diff(a: dict, b: dict) -> list[str]:
    ch = []
    for k in sorted(set(a["tracks"]) | set(b["tracks"])):
        x, y = a["tracks"].get(k, {}), b["tracks"].get(k, {})
        for f in ("state", "base_fraction", "max_odds", "min_odds"):
            if x.get(f) != y.get(f):
                ch.append(f"{k}.{f}: {x.get(f)} -> {y.get(f)}")
    for f in ("daily_cap", "fixture_cap", "league_daily_cap", "league_market_daily_cap"):
        if a["portfolio"].get(f) != b["portfolio"].get(f):
            ch.append(f"portfolio.{f}: {a['portfolio'].get(f)} -> {b['portfolio'].get(f)}")
    if a.get("tier_multipliers") != b.get("tier_multipliers"):
        ch.append(f"tier_multipliers: {a.get('tier_multipliers')} -> {b.get('tier_multipliers')}")
    if sorted(a["convergence"]["leagues"]) != sorted(b["convergence"]["leagues"]):
        ch.append(f"convergence leagues: {a['convergence']['leagues']} -> {b['convergence']['leagues']}")
    return ch


def main(as_of: str | None = None, n_paths: int = 2000) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "history").mkdir(exist_ok=True)
    as_of = pd.Timestamp(as_of) if as_of else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    bets_all = BD.load_bets(PERFORMANCE_CUTOFF)
    bets = bets_all[bets_all["date"] < as_of]
    current = BD.production_policy()
    v11 = BD.v11_league_residual()

    # freshness: settlements and CLV must be recent, or no increase is allowed (fail closed)
    last_settled = bets["date"].max()
    fresh = {"last_settled": last_settled.strftime("%Y-%m-%d") if pd.notna(last_settled) else None,
             "settlement_fresh": bool(pd.notna(last_settled) and (as_of - last_settled).days <= 7),
             "clv_share_last_30d": round(float(bets[bets["date"] >= as_of - pd.Timedelta(days=30)]["clv"].notna().mean()), 3)
             if len(bets) else 0.0, "v11_rows": int(len(v11))}
    fresh["clv_fresh"] = fresh["clv_share_last_30d"] >= 0.5

    _, cur_m = S.replay(bets[bets["date"] >= as_of - pd.Timedelta(days=60)], current)
    # The production policy's own replayed bankroll path (start 100) - what the dashboard shows as
    # peak / drawdown / throttle until a real bankroll ledger exists.
    prod_path, _ = S.replay(bets, current)
    dd_warning = cur_m.get("max_dd", 0) >= 0.08 or not fresh["settlement_fresh"] or not fresh["clv_fresh"]
    proposed, decisions, ev = A.propose(current, bets, as_of, v11, dd_warning=dd_warning)
    # Previous MONTH's latest proposal, ordered by the name (month, re-run number) - never by file
    # mtime, which a CI checkout resets on every run.
    def _key(f):
        stem = f.stem.split("-proposed")
        r = stem[1].lstrip("-r") if len(stem) > 1 else ""
        return stem[0], int(r) if r.isdigit() else 1
    prev_hist = sorted((f for f in (OUT / "history").glob("*-proposed*.json")
                        if f.stem[:7] < f"{as_of:%Y-%m}"), key=_key)
    prev_prop = json.loads(prev_hist[-1].read_text(encoding="utf-8")) if prev_hist else current

    cands = {"A_CURRENT": current, "B_FLAT_0.5": flat(current, 0.005, "flat-0.5"),
             "C_FLAT_1": flat(current, 0.01, "flat-1"), "D_FLAT_2": flat(current, 0.02, "flat-2"),
             "E_SAFE": safe(current), "F_BALANCED_STATIC": current,
             "G_PROPOSED_ADAPTIVE": proposed, "H_PREVIOUS_PROPOSED": prev_prop}
    table = evaluate(bets, cands, n_paths=n_paths)
    wf, wf_verdict = walk_forward(bets, current, v11)

    passing = table[table["passes_survival"]]
    growth = passing.sort_values("risk_end_median", ascending=False).iloc[0]["policy"] if len(passing) else "E_SAFE"
    grow_pos = table[table["log_growth"] > 0]
    survival = (grow_pos.sort_values(["risk_p_maxdd_gt_10", "score"], ascending=[True, False]).iloc[0]["policy"]
                if len(grow_pos) else "E_SAFE")
    g_ok = bool(table.set_index("policy").loc["G_PROPOSED_ADAPTIVE", "passes_survival"])
    if wf_verdict["status"] == "VALIDATED":
        recommended, rec_name = (proposed, "G_PROPOSED_ADAPTIVE") if g_ok else (cands["E_SAFE"], "E_SAFE")
    else:
        recommended, rec_name = A.reduce_only(current, proposed), "CURRENT_WITH_RISK_REDUCTIONS_ONLY"
    recommended = copy.deepcopy(recommended)
    recommended.update(policy_version=f"{current.get('policy_version', 'policy')}+review-{as_of:%Y-%m}"
                       if rec_name.startswith("CURRENT") else proposed["policy_version"],
                       generated_at=proposed["generated_at"], evidence_cutoff=proposed["evidence_cutoff"],
                       status="RECOMMENDED_NOT_WIRED")
    violations = A.validate(recommended)
    if violations:
        recommended, rec_name = copy.deepcopy(current), "CURRENT (recommendation violated hard bounds)"
    changes = _diff(current, recommended)
    stress_rows = S.stress(bets, recommended)

    verdict = {"calculation_version": CALC_VERSION, "as_of": as_of.strftime("%Y-%m-%d"),
               "evidence_cutoff": proposed["evidence_cutoff"], "freshness": fresh,
               "drawdown_warning": dd_warning, "walk_forward": wf_verdict,
               "BEST_GROWTH_POLICY": growth, "BEST_SURVIVAL_POLICY": survival,
               "RECOMMENDED_POLICY": rec_name, "recommended_violations": violations,
               "POLICY_CHANGE_RECOMMENDED": "YES" if changes else "NO", "changes": changes,
               "PRODUCTION_SELECTION_LOGIC_CHANGED": "NO", "PREDICTION_THRESHOLDS_CHANGED": "NO",
               "PLAYER_PROP_REAL_STAKING_ENABLED": "NO"}

    stamp = f"{as_of:%Y-%m}"
    (OUT / "current_policy_recommendation.json").write_text(
        json.dumps({**recommended, "review": verdict, "decisions": decisions}, indent=2, default=str), encoding="utf-8")
    # History is append-only: the month's first review keeps its file; a re-run gets -r2, -r3, ...
    def _free(kind: str):
        f, k = OUT / "history" / f"{stamp}-{kind}.json", 2
        while f.exists():
            f, k = OUT / "history" / f"{stamp}-{kind}-r{k}.json", k + 1
        return f
    _free("policy").write_text(json.dumps(recommended, indent=2, default=str), encoding="utf-8")
    _free("proposed").write_text(json.dumps(proposed, indent=2, default=str), encoding="utf-8")
    (OUT / "v9_bankroll_policy.json").write_text(json.dumps(
        {k: v for k, v in recommended.items() if k not in ("review", "decisions")}, indent=2, default=str), encoding="utf-8")
    table.insert(0, "as_of", as_of.strftime("%Y-%m-%d"))
    table.to_csv(OUT / "policy_candidates.csv", index=False)
    pd.DataFrame(stress_rows).to_csv(OUT / "stress_tests.csv", index=False)
    wf.to_csv(OUT / "walk_forward.csv", index=False)
    prod_path.assign(peak=prod_path["bankroll"].cummax(),
                     drawdown=lambda x: 1 - x["bankroll"] / x["peak"]).to_csv(OUT / "production_policy_path.csv", index=False)
    pd.DataFrame(decisions).to_csv(OUT / "track_decisions.csv", index=False)
    pd.DataFrame(ev["convergence"]).to_csv(OUT / "convergence_leagues.csv", index=False)
    (OUT / "track_evidence.json").write_text(json.dumps(ev["tracks"], indent=2, default=str), encoding="utf-8")
    summary = render_summary(verdict, current, recommended, decisions, table, stress_rows)
    (OUT / "MONTHLY_REVIEW.md").write_text(summary, encoding="utf-8")
    (OUT / "pr_body.md").write_text(pr_body(verdict, current, recommended, decisions, table, stress_rows),
                                    encoding="utf-8")
    print(summary)
    return 0


def _pct(x):
    return "0" if not x else f"{100 * float(x):.2f}%"


def render_summary(v, cur, rec, decisions, table, stress) -> str:
    t = table.set_index("policy")
    lines = ["WOWZA MONTHLY BANKROLL REVIEW", "", f"Evidence cutoff: {v['evidence_cutoff']}",
             f"Current policy: {cur.get('policy_version')}", f"Recommended policy: {rec.get('policy_version')} ({v['RECOMMENDED_POLICY']})",
             f"Walk-forward: {v['walk_forward']['status']} ({v['walk_forward']['months_evaluated']} of {v['walk_forward']['required']} months)",
             "", "Portfolio:"]
    for f in ("daily_cap", "fixture_cap", "league_daily_cap", "league_market_daily_cap"):
        lines.append(f"- {f}: {_pct(cur['portfolio'][f])} -> {_pct(rec['portfolio'][f])}")
    lines += ["", "Tracks:"]
    for d in decisions:
        lines.append(f"- {d['track']}: {_pct(d['previous_fraction'])} -> {_pct(rec['tracks'][d['track']].get('base_fraction'))} "
                     f"{d['decision']} ({rec['tracks'][d['track']].get('state')})")
    lines += ["", f"Convergence leagues: {rec['convergence']['leagues'] or 'none qualify'}", "",
              "Expected historical / stress profile (recommended policy):"]
    for s in stress:
        lines.append(f"- {s['scenario']}: return {s.get('return_pct', 0):+.1f}%, max DD {100 * s.get('max_dd', 0):.1f}%")
    r = t.loc["G_PROPOSED_ADAPTIVE"] if "G_PROPOSED_ADAPTIVE" in t.index else None
    if r is not None:
        lines.append(f"- proposed adaptive: P(DD>20%) {r['risk_p_maxdd_gt_20']:.1%}, median end {r['risk_end_median']}")
    lines += ["", f"BEST_GROWTH_POLICY = {v['BEST_GROWTH_POLICY']}", f"BEST_SURVIVAL_POLICY = {v['BEST_SURVIVAL_POLICY']}",
              f"POLICY_CHANGE_RECOMMENDED = {v['POLICY_CHANGE_RECOMMENDED']}"]
    if v["changes"]:
        lines += ["Changes:"] + [f"  - {c}" for c in v["changes"]]
    lines += ["", "PRODUCTION_SELECTION_LOGIC_CHANGED = NO", "PREDICTION_THRESHOLDS_CHANGED = NO",
              "PLAYER_PROP_REAL_STAKING_ENABLED = NO"]
    return "\n".join(lines) + "\n"


def pr_body(v, cur, rec, decisions, table, stress) -> str:
    unchanged = [d["track"] for d in decisions if abs(d["previous_fraction"] - float(rec["tracks"][d["track"]].get("base_fraction", 0))) < 1e-12]
    body = [f"Monthly bankroll evidence review, evidence cutoff {v['evidence_cutoff']}.", "",
            "**Only `config/bankroll_policy.json` changes.** No model, threshold, selection or prediction change.",
            "Human approval required before this policy is used.", "",
            f"- Current policy: `{cur.get('policy_version')}`", f"- Proposed policy: `{rec.get('policy_version')}` ({v['RECOMMENDED_POLICY']})",
            f"- Allocator walk-forward: {v['walk_forward']['status']}", "", "### Changes"]
    body += [f"- {c}" for c in v["changes"]] or ["- none"]
    body += ["", "### Evidence by changed track"]
    for d in decisions:
        if d["track"] not in unchanged:
            body.append(f"- **{d['track']}** {d['decision']}: n={d.get('n')}, ROI {d.get('roi')}, shrunk {d.get('shrunk_roi')}, "
                        f"90% [{d.get('roi_lo90')}, {d.get('roi_hi90')}], CLV {d.get('clv_median')}; " + "; ".join(d.get("reasons", [])))
    body += ["", f"### Unchanged tracks", ", ".join(unchanged) or "none", "", "### Stress (recommended)"]
    body += [f"- {s['scenario']}: {s.get('return_pct', 0):+.1f}%, max DD {100 * s.get('max_dd', 0):.1f}%" for s in stress]
    body += ["", "Source: wowzaV9-Pro `output/bankroll/` (current_policy_recommendation.json, policy_candidates.csv, "
             "stress_tests.csv, walk_forward.csv).", "",
             "PRODUCTION_SELECTION_LOGIC_CHANGED = NO · PREDICTION_THRESHOLDS_CHANGED = NO · PLAYER_PROP_REAL_STAKING_ENABLED = NO"]
    return "\n".join(body) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of")
    ap.add_argument("--paths", type=int, default=2000)
    a = ap.parse_args()
    raise SystemExit(main(a.as_of, a.paths))
