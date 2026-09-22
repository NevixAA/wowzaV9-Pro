"""If every price were identical, how often would we simply be RIGHT?

    python -m src.validation.pick_accuracy [--write]

A DELIBERATELY SEPARATE QUESTION. Every other study in this estate asks about EDGE: is the model
better than the price, is there CLV, is the ROI real. This one throws the price away entirely.
Assume all odds are the same, so a win is a win and a loss is a loss. Then the only thing that
matters is:

    how often does the model call it correctly, and can it get better at that?

Nothing here is joined to odds, edge, tiers, staking, CLV or ROI, and nothing here should be
read as evidence about betting. A model can be excellent at picking winners and still lose money
at the prices on offer — those are different claims and this file only makes the first one.

THE CONTROL THAT MAKES THE NUMBER MEAN ANYTHING. "68% accurate on BTTS" sounds good and may be
worthless: if both teams score in 68% of games, then a rock that always says YES scores 68% too.
So every accuracy is reported against the MAJORITY BASELINE — always call the more common
outcome — and the only figure worth reading is the gap between them. A model that cannot beat a
rock has not learned to guess; it has learned the base rate.

THE SECOND QUESTION, and the more useful one. Suppose overall accuracy is unremarkable. Can the
model still tell WHICH of its calls to trust? That is a different skill: if the games it is most
confident about are the ones it gets right, you can act on the top slice and ignore the rest,
even with a mediocre average. So accuracy is also reported by confidence decile, and as a
"top K%" curve.

If confidence is flat against accuracy, the model has no idea which of its own calls are good —
and that is worth knowing plainly.
"""
from __future__ import annotations

import argparse
import glob
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
MIN_N = 100          # below this a cell is printed but never interpreted

# settlements and model_snapshots disagree on market names. One place, stated once.
MARKET_ALIAS = {"OVER15": "OU15", "OVER35": "OU35"}


def _outcomes() -> pd.DataFrame:
    """Per fixture per market: did the EVENT happen? Side-independent."""
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "settlements" / "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d[d["result"].isin(["WIN", "LOSS"])].copy()
    d["market"] = d["market"].astype(str).replace(MARKET_ALIAS)
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    side = d["side"].astype(str).str.upper()
    won = d["result"].eq("WIN")
    # THE EVENT, not the bet. A bet on UNDER that won means the game went UNDER, so the event
    # "over 2.5" did NOT happen. Scoring the bet instead would make every UNDER row look
    # inverted and turn an accuracy study into a side-selection study.
    d["y"] = np.where(side.isin(["UNDER", "NO"]), ~won, won).astype(int)
    d = d[d["match_date"].notna()]
    return (d.sort_values("match_date")
              .drop_duplicates(["fixture_key", "market"], keep="first")
              [["fixture_key", "market", "league", "model_type", "match_date", "y"]])


def _probs() -> pd.DataFrame:
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "model_snapshots" / "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d["p"] = pd.to_numeric(d["model_prob"], errors="coerce")
    d["observed_at"] = pd.to_datetime(d["observed_at"], errors="coerce")
    d = d[d["p"].notna() & d["p"].between(0.0001, 0.9999)]
    # The model's LAST pre-kickoff opinion on that fixture+market.
    return (d.sort_values("observed_at")
              .drop_duplicates(["fixture_key", "market"], keep="last")
              [["fixture_key", "market", "p"]])


def assess(d: pd.DataFrame, label: str) -> dict:
    """Accuracy vs a rock, and whether confidence separates good calls from bad."""
    y = d["y"].to_numpy()
    p = d["p"].to_numpy()
    n = len(d)
    base = float(y.mean())
    # THE ROCK: always call the more common outcome. This is the number to beat.
    rock = max(base, 1 - base)
    call = (p >= 0.5).astype(int)
    acc = float((call == y).mean())

    # Confidence = distance from a coin flip. A 0.92 and a 0.08 are equally confident calls.
    conf = np.abs(p - 0.5)
    out = {"label": label, "n": int(n), "base_rate": base, "rock_accuracy": rock,
           "model_accuracy": acc, "lift_pp": (acc - rock) * 100,
           "interpretable": n >= MIN_N, "calc_version": CALC_VERSION}

    # Does confidence mean anything? Accuracy within each confidence decile.
    if n >= MIN_N:
        try:
            q = pd.qcut(conf, 10, duplicates="drop", labels=False)
            rows = []
            for b in sorted(set(q)):
                m = q == b
                rows.append({"decile": int(b), "n": int(m.sum()),
                             "mean_conf": float(conf[m].mean()),
                             "accuracy": float((call[m] == y[m]).mean())})
            out["by_confidence"] = rows
            # Spearman between decile and accuracy — is it a gradient or a flat line?
            from scipy import stats as st
            rs, ps = st.spearmanr([r["decile"] for r in rows], [r["accuracy"] for r in rows])
            out["confidence_gradient_rho"] = float(rs)
            out["confidence_gradient_p"] = float(ps)
        except Exception:
            pass

        # TOP-K: act only on the most confident K% of calls.
        order = np.argsort(-conf)
        out["top_k"] = [{"k_pct": k, "n": int(max(1, n * k // 100)),
                         "accuracy": float((call[order[:max(1, n * k // 100)]]
                                            == y[order[:max(1, n * k // 100)]]).mean())}
                        for k in (5, 10, 25, 50, 100)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    o, p = _outcomes(), _probs()
    if o.empty or p.empty:
        print("[pick_accuracy] no settled outcomes or no model probabilities")
        return 1
    d = o.merge(p, on=["fixture_key", "market"], how="inner")
    print(f"[pick_accuracy] {len(d):,} fixture-market calls with both a prediction and a result")
    print(f"                markets: {sorted(d.market.unique())}")
    print("                PRICES ARE IGNORED ENTIRELY — this is hit rate, not edge.\n")

    results = []
    for mk, g in d.groupby("market"):
        results.append(assess(g, f"{mk} (all)"))
        for mt, gg in g.groupby("model_type"):
            if str(mt) != "unknown" and len(gg) >= MIN_N:
                results.append(assess(gg, f"{mk} / {mt}"))

    print("=" * 96)
    print("CAN IT GUESS?   'rock' = always call the more common outcome. Beat that or nothing.")
    print("=" * 96)
    print(f"  {'market':<26}{'n':>7}{'base':>8}{'rock':>8}{'model':>8}{'lift':>9}")
    for r in sorted(results, key=lambda x: -x["lift_pp"]):
        flag = "" if r["interpretable"] else "   (n too small)"
        print(f"  {r['label']:<26}{r['n']:>7}{r['base_rate']:>8.3f}{r['rock_accuracy']:>8.3f}"
              f"{r['model_accuracy']:>8.3f}{r['lift_pp']:>+8.1f}pp{flag}")

    print("\n" + "=" * 96)
    print("DOES CONFIDENCE MEAN ANYTHING?  accuracy on the most confident K% of calls")
    print("=" * 96)
    for r in results:
        if not r.get("top_k"):
            continue
        tk = "  ".join(f"top{t['k_pct']}%:{t['accuracy']:.3f}(n{t['n']})" for t in r["top_k"])
        rho = r.get("confidence_gradient_rho")
        verdict = ("confidence TRACKS accuracy" if rho is not None and rho > 0.5 else
                   "confidence tells you nothing" if rho is not None and abs(rho) <= 0.5 else "")
        print(f"  {r['label']}")
        print(f"     {tk}")
        if rho is not None:
            print(f"     decile gradient rho={rho:+.3f} (p={r['confidence_gradient_p']:.3f})  -> {verdict}")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pth = cfg.OUTPUT_DIR / "pick_accuracy.json"
        pth.write_text(json.dumps({"generated_at": pd.Timestamp.utcnow().isoformat(),
                                   "results": results}, indent=2, default=str), encoding="utf-8")
        print(f"\n[pick_accuracy] wrote {pth.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
