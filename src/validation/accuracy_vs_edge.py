"""Does being ACCURATE make more money than hunting for EDGE — and can combos monetise it?

    python -m src.validation.accuracy_vs_edge [--write]

THE THESIS BEING TESTED, in Nevo's words: "if we have more accuracy, we can use combo bets to
achieve better odds and it might become profitable." That is a real and testable idea, and it is
NOT the same as the edge thesis. Edge asks "is the price wrong". Accuracy asks "am I right",
and combos are the mechanism for converting a high hit rate at short odds into a payout worth
having.

Run on the FULL history — 12,187 fixtures, 2022-09 to 2026-05, four seasons — not on the few
hundred live picks the earlier hit-rate study used.

THREE QUESTIONS, in order, because each only matters if the previous one survives.

  1. ACCURACY. How often is the model right, against a rock that always calls the more common
     outcome? Prices ignored entirely.
  2. MONEY. Does selecting bets by CONFIDENCE make more than selecting them by EDGE, at the
     same number of bets, on the same fixtures, at real prices?
  3. COMBOS. If you pair two confident picks, does the joint hit rate hold up — and do the
     multiplied odds turn a short price into a profitable one?

WHICH ODDS MAY BE USED FOR MONEY, and this is not negotiable. Measured on this very frame:
odds_over15 is the constant 1.40 on 12,186 of 12,187 rows and odds_over35 is present on 0.1%.
Both are fabricated or absent and CANNOT appear in any ROI or EV figure — that fabrication
already certified four live markets once. Only odds_over25/under25 (100% present, 223 distinct)
and odds_btts (49.7% present, 131 distinct) are real. Accuracy is reported for every market;
money is reported only for those two.

THE COMBO TRAP, stated up front because the arithmetic is seductive. Two independent 70% legs
at 1.55 each give 0.49 x 2.40 = 1.18, an 18% edge out of nothing. That is only true IF THE LEGS
ARE INDEPENDENT. Goals markets on the SAME fixture are the opposite of independent: a high-
scoring game makes over 2.5 AND both-teams-score true together. So the joint hit rate is
measured directly and compared against the product, and the gap between them is the finding.
Books also price correlated legs jointly or refuse them, which is a separate reason this can
fail even when the maths works.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import v9_source as v9

CALC_VERSION = "1.0.0"
MIN_N = 150
# The exact fallback constants src/backtest.py fills in when a real price is absent. Rows
# carrying these are NOT priced and must never reach a money figure.
#
# A COLUMN-LEVEL "does it vary" CHECK IS NOT ENOUGH, and my first version of this file proved
# it: odds_btts has 130 distinct values and passed, while 52.1% of its rows are the 1.85
# fallback. The combo section then reported +43% ROI built on half-invented prices. The guard
# has to drop ROWS, not bless columns.
FALLBACK_ODDS = {"odds_btts": 1.85, "odds_over15": 1.40, "odds_over35": 2.60}
MIN_DISTINCT_ODDS = 20


def _load(market: str) -> pd.DataFrame:
    d = v9.fetch_csv(f"output/backtest_results_{market}.csv", required=False)
    if d.empty:
        return d
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in d.columns:
        if c.startswith(("p_", "odds_")) or c in ("over25", "over15", "over35", "btts"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d[d["date"].notna()].sort_values("date")


def _odds_are_real(s: pd.Series) -> bool:
    v = pd.to_numeric(s, errors="coerce").dropna()
    return len(v) > 0 and v.nunique() >= MIN_DISTINCT_ODDS


def _real_priced(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """Drop rows whose price is the known fabricated fallback for that market."""
    fb = FALLBACK_ODDS.get(col)
    if fb is None or col not in d.columns:
        return d
    v = pd.to_numeric(d[col], errors="coerce")
    keep = v.notna() & (v != fb)
    dropped = int((~keep).sum())
    if dropped:
        print(f"  [real-price filter] {col}: dropped {dropped:,} row(s) at the {fb} fallback "
              f"({100*dropped/max(len(d),1):.1f}%), kept {int(keep.sum()):,}")
    return d[keep]


def accuracy_table(frames: dict) -> list[dict]:
    """Question 1 — how often is it right, against a rock? No prices involved."""
    out = []
    for mk, (d, pcol, ycol) in frames.items():
        sub = d.dropna(subset=[pcol, ycol])
        if len(sub) < MIN_N:
            continue
        p, y = sub[pcol].to_numpy(), sub[ycol].to_numpy().astype(int)
        base = float(y.mean())
        rock = max(base, 1 - base)
        call = (p >= 0.5).astype(int)
        acc = float((call == y).mean())
        conf = np.abs(p - 0.5)
        order = np.argsort(-conf)
        topk = {k: float((call[order[:max(1, len(y) * k // 100)]]
                          == y[order[:max(1, len(y) * k // 100)]]).mean())
                for k in (1, 5, 10, 25, 50, 100)}
        from scipy import stats as st
        q = pd.qcut(conf, 10, duplicates="drop", labels=False)
        dec = [float((call[q == b] == y[q == b]).mean()) for b in sorted(set(q))]
        rho, pv = st.spearmanr(range(len(dec)), dec)
        out.append({"market": mk, "n": int(len(sub)), "base_rate": base, "rock": rock,
                    "accuracy": acc, "lift_pp": (acc - rock) * 100,
                    "top_k": topk, "gradient_rho": float(rho), "gradient_p": float(pv),
                    "calc_version": CALC_VERSION})
    return out


def edge_vs_confidence(d: pd.DataFrame, *, n_boot: int = 3000, seed: int = 71) -> dict | None:
    """Question 2 — at the SAME bet count, does confidence beat edge? OU25, real prices only."""
    rng = np.random.default_rng(seed)
    need = ["p_over25", "over25", "odds_over25", "odds_under25"]
    if not all(c in d.columns for c in need):
        return None
    s = _real_priced(_real_priced(d.dropna(subset=need).copy(), "odds_over25"), "odds_under25")
    if not (_odds_are_real(s["odds_over25"]) and _odds_are_real(s["odds_under25"])):
        return {"status": "ODDS_NOT_REAL"}

    # Bet the side the model favours, at that side's real price.
    s["side_over"] = s["p_over25"] >= 0.5
    s["odds"] = np.where(s["side_over"], s["odds_over25"], s["odds_under25"])
    s["won"] = np.where(s["side_over"], s["over25"] == 1, s["over25"] == 0)
    s["pnl"] = np.where(s["won"], s["odds"] - 1.0, -1.0)
    # CONFIDENCE = distance from a coin flip. EDGE = model probability minus the de-vigged price.
    s["conf"] = (s["p_over25"] - 0.5).abs()
    fair = (1.0 / s["odds_over25"]) / ((1.0 / s["odds_over25"]) + (1.0 / s["odds_under25"]))
    s["edge"] = np.where(s["side_over"], s["p_over25"] - fair, (1 - s["p_over25"]) - (1 - fair))

    # CHRONOLOGICAL. Rank on the earlier 60%, act on the later 40% — otherwise "take the top 10%"
    # is chosen with hindsight and both strategies are flattered.
    cut = int(len(s) * 0.6)
    tr, te = s.iloc[:cut], s.iloc[cut:]
    res = {"status": "OK", "n_total": int(len(s)), "n_train": int(len(tr)),
           "n_test": int(len(te)),
           "test_from": str(te["date"].min().date()), "test_to": str(te["date"].max().date()),
           "strategies": []}
    for k in (5, 10, 25, 50):
        n_take = max(5, len(te) * k // 100)
        for name, col in (("confidence", "conf"), ("edge", "edge")):
            thr = tr[col].quantile(1 - k / 100)          # threshold learned on the past only
            sel = te[te[col] >= thr]
            if len(sel) < 5:
                continue
            roi = float(sel["pnl"].mean())
            bs = rng.choice(sel["pnl"].to_numpy(), size=(n_boot, len(sel)), replace=True).mean(axis=1)
            lo, hi = np.percentile(bs, [2.5, 97.5])
            res["strategies"].append({
                "select_by": name, "top_k_pct": k, "threshold": float(thr),
                "n_bets": int(len(sel)), "hit_rate": float(sel["won"].mean()),
                "mean_odds": float(sel["odds"].mean()), "roi": roi,
                "ci_lo": float(lo), "ci_hi": float(hi), "profitable": bool(lo > 0)})
    return res


def combos(std: pd.DataFrame, btts: pd.DataFrame, *, n_boot: int = 3000, seed: int = 73) -> dict:
    """Question 3 — do two confident legs on the same fixture stay independent, and pay?"""
    rng = np.random.default_rng(seed)
    key = ["date", "home_team", "away_team"]
    a = std.dropna(subset=["p_over25", "over25", "odds_over25"])[key + ["p_over25", "over25", "odds_over25"]]
    b = btts.dropna(subset=["p_btts", "btts", "odds_btts"])[key + ["p_btts", "btts", "odds_btts"]]
    a = _real_priced(a, "odds_over25")
    b = _real_priced(b, "odds_btts")
    m = a.merge(b, on=key, how="inner")
    if len(m) < MIN_N or not _odds_are_real(m["odds_btts"]):
        return {"status": "INSUFFICIENT_OR_SYNTHETIC", "n": int(len(m))}

    # Both legs taken in the direction the model favours, at that leg's real price.
    m = m[(m["p_over25"] >= 0.5) & (m["p_btts"] >= 0.5)].copy()   # both legs YES/OVER
    m["hit_a"] = (m["over25"] == 1)
    m["hit_b"] = (m["btts"] == 1)
    m["hit_both"] = m["hit_a"] & m["hit_b"]
    m["combo_odds"] = m["odds_over25"] * m["odds_btts"]
    m["conf"] = (m["p_over25"] - 0.5).abs() + (m["p_btts"] - 0.5).abs()

    rows = []
    for k in (10, 25, 50, 100):
        sel = m.nlargest(max(10, len(m) * k // 100), "conf")
        pa, pb = float(sel["hit_a"].mean()), float(sel["hit_b"].mean())
        joint = float(sel["hit_both"].mean())
        pnl = np.where(sel["hit_both"], sel["combo_odds"] - 1.0, -1.0)
        bs = rng.choice(pnl, size=(n_boot, len(pnl)), replace=True).mean(axis=1)
        lo, hi = np.percentile(bs, [2.5, 97.5])
        rows.append({
            "top_k_pct": k, "n": int(len(sel)),
            "hit_over25": pa, "hit_btts": pb,
            "independent_would_be": pa * pb, "actual_joint": joint,
            "correlation_gap_pp": (joint - pa * pb) * 100,
            "mean_combo_odds": float(sel["combo_odds"].mean()),
            "roi": float(pnl.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
            "profitable": bool(lo > 0),
            # What a single OU25 leg alone returned on the same fixtures, for comparison.
            "single_leg_roi": float(np.where(sel["hit_a"], sel["odds_over25"] - 1.0, -1.0).mean()),
        })
    return {"status": "OK", "n_matched": int(len(m)), "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=3000)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    std, btts = _load("standard"), _load("btts")
    o15, o35, nf = _load("over15"), _load("over35"), _load("newformat")
    frames = {}
    for mk, d, pc, yc in (("OU25 standard", std, "p_over25", "over25"),
                          ("OU25 new_format", nf, "p_over25", "over25"),
                          ("BTTS", btts, "p_btts", "btts"),
                          ("Over 1.5", o15, "p_over15", "over15"),
                          ("Over 3.5", o35, "p_over35", "over35")):
        if not d.empty and pc in d.columns and yc in d.columns:
            frames[mk] = (d, pc, yc)

    acc = accuracy_table(frames)
    print("=" * 100)
    print("1. ACCURACY on the FULL history — prices ignored. 'rock' = always call the common one.")
    print("=" * 100)
    print(f"  {'market':<18}{'n':>8}{'rock':>8}{'model':>8}{'lift':>9}   "
          f"{'top10%':>8}{'top5%':>8}{'top1%':>8}  confidence gradient")
    for r in sorted(acc, key=lambda x: -x["lift_pp"]):
        grad = ("TRACKS" if r["gradient_rho"] > 0.5 and r["gradient_p"] < 0.05 else "flat")
        print(f"  {r['market']:<18}{r['n']:>8,}{r['rock']:>8.3f}{r['accuracy']:>8.3f}"
              f"{r['lift_pp']:>+8.1f}pp   {r['top_k'][10]:>8.3f}{r['top_k'][5]:>8.3f}"
              f"{r['top_k'][1]:>8.3f}  rho={r['gradient_rho']:+.2f} {grad}")

    print("\n" + "=" * 100)
    print("2. DOES ACCURACY MAKE MORE MONEY THAN EDGE?  OU25, real prices, chronological")
    print("=" * 100)
    ev = edge_vs_confidence(std, n_boot=a.boot)
    if not ev or ev.get("status") != "OK":
        print(f"  unavailable: {ev}")
    else:
        print(f"  ranked on {ev['n_train']:,} earlier fixtures, acted on {ev['n_test']:,} later "
              f"({ev['test_from']}..{ev['test_to']})")
        print(f"  {'select by':<12}{'top':>5}{'bets':>7}{'hit':>8}{'odds':>7}{'ROI':>9}   95% CI")
        for s in ev["strategies"]:
            star = "  <-- PROFITABLE" if s["profitable"] else ""
            print(f"  {s['select_by']:<12}{s['top_k_pct']:>4}%{s['n_bets']:>7}{s['hit_rate']:>8.3f}"
                  f"{s['mean_odds']:>7.2f}{s['roi']:>+9.3f}   "
                  f"[{s['ci_lo']:+.3f},{s['ci_hi']:+.3f}]{star}")

    print("\n" + "=" * 100)
    print("3. COMBOS — do two confident legs stay independent, and do the odds save them?")
    print("=" * 100)
    cb = combos(std, btts, n_boot=a.boot)
    if cb.get("status") != "OK":
        print(f"  unavailable: {cb}")
    else:
        print(f"  {cb['n_matched']:,} fixtures where BOTH legs are real-priced and both favoured")
        print(f"  {'top':>5}{'n':>7}{'P(a)':>7}{'P(b)':>7}{'if indep':>10}{'actual':>8}"
              f"{'gap':>8}{'odds':>7}{'combo ROI':>11}{'1-leg ROI':>11}")
        for r in cb["rows"]:
            star = "  <-- PROFITABLE" if r["profitable"] else ""
            print(f"  {r['top_k_pct']:>4}%{r['n']:>7}{r['hit_over25']:>7.3f}{r['hit_btts']:>7.3f}"
                  f"{r['independent_would_be']:>10.3f}{r['actual_joint']:>8.3f}"
                  f"{r['correlation_gap_pp']:>+7.1f}pp{r['mean_combo_odds']:>7.2f}"
                  f"{r['roi']:>+11.3f}{r['single_leg_roi']:>+11.3f}{star}")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = cfg.OUTPUT_DIR / "accuracy_vs_edge.json"
        p.write_text(json.dumps({"generated_at": pd.Timestamp.utcnow().isoformat(),
                                 "accuracy": acc, "edge_vs_confidence": ev, "combos": cb},
                                indent=2, default=str), encoding="utf-8")
        print(f"\n[accuracy_vs_edge] wrote {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
