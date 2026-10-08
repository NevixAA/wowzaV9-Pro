"""Two O/U questions on EVERY fixture v9 priced, not only the ones it tipped.

    python -m src.studies.ou_studies

1. RESIDUAL TEST. Once the market's price is known, does adding Wowza's probability make the
   forecast better? Out of sample, in time order: fit `y ~ logit(market)` and
   `y ~ logit(market) + logit(model)` on earlier fixtures, score both on later ones, and compare
   log loss and Brier with a matchday-bootstrap interval. If the interval for the improvement
   does not clear zero, the model adds nothing the price did not already know, and that market
   stays PAPER whatever a short ROI window says. Run for OU25, and for OU15 / OU35 / BTTS too.

2. UNDER DIAGNOSIS. v9's staked O/U 2.5 UNDER bets lost -24.7u (CI below zero). Is the model's
   P(UNDER) overconfident, and if so where? Calibration of P(UNDER) and P(OVER) against the
   result and against the de-vigged market, split by how far the model leans from the market,
   by track, and by price. The fix belongs in the probability, not in another threshold.

Using the whole priced population avoids the selection bias of studying only tips: a tip exists
BECAUSE the model disagreed with the price, which is exactly the population where an
overconfident model looks worst.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data import v9_config
from src.studies import common as C

START = "2026-08-10"
#: Yesterday, so a weekly run always covers everything that has finished.
END = (pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def panel(market: str, R: pd.DataFrame) -> pd.DataFrame:
    M = C.model_panel(market)
    M = M[(M["match_date"] >= START) & (M["match_date"] <= END)]
    B = C.book_panel(market)
    D = M.merge(B, on="fixture_key", how="inner")
    j = C.match_frames(D, R)
    D = D[j.notna()].copy()
    rr = R.loc[j[j.notna()].astype(int).to_numpy()].reset_index(drop=True)
    D = D.reset_index(drop=True)
    D["y"] = C.outcome(market, rr["hg"], rr["ag"])
    D = D[(D["n_books"] >= 3) & D["p_market"].between(0.02, 0.98) & D["model_prob"].between(0.01, 0.99)]
    return D.sort_values("match_date").reset_index(drop=True)


def residual_test(D: pd.DataFrame, folds: int = 5) -> dict:
    """Expanding-window out-of-sample comparison, market-only vs market+model."""
    if len(D) < 100:
        return {"n": int(len(D)), "status": "TOO_FEW"}
    days = np.array(sorted(D["match_date"].unique()))
    edges = np.array_split(days, folds + 1)
    oos = []
    for k in range(1, folds + 1):
        train = D[D["match_date"].isin(np.concatenate(edges[:k]))]
        test = D[D["match_date"].isin(edges[k])]
        if len(train) < 50 or test.empty:
            continue
        b0, _ = C.fit_logistic(C.logit(train["p_market"])[:, None], train["y"])
        b1, _ = C.fit_logistic(np.column_stack([C.logit(train["p_market"]), C.logit(train["model_prob"])]), train["y"])
        p0 = C.predict_logistic(b0, C.logit(test["p_market"])[:, None])
        p1 = C.predict_logistic(b1, np.column_stack([C.logit(test["p_market"]), C.logit(test["model_prob"])]))
        oos.append(test.assign(p0=p0, p1=p1))
    O = pd.concat(oos)
    d_ll = C.logloss(O["p1"], O["y"]) - C.logloss(O["p0"], O["y"])
    d_br = C.brier(O["p1"], O["y"]) - C.brier(O["p0"], O["y"])
    b, cov = C.fit_logistic(np.column_stack([C.logit(D["p_market"]), C.logit(D["model_prob"])]), D["y"])
    ci_ll = C.block_ci(d_ll, O["match_date"])
    return {
        "n": int(len(D)), "n_oos": int(len(O)), "rate": round(float(D["y"].mean()), 4),
        "logloss_market_raw": round(float(C.logloss(D["p_market"], D["y"]).mean()), 5),
        "logloss_model_raw": round(float(C.logloss(D["model_prob"], D["y"]).mean()), 5),
        "brier_market_raw": round(float(C.brier(D["p_market"], D["y"]).mean()), 5),
        "brier_model_raw": round(float(C.brier(D["model_prob"], D["y"]).mean()), 5),
        "oos_delta_logloss": round(float(d_ll.mean()), 5), "oos_delta_logloss_ci90": ci_ll,
        "oos_delta_brier": round(float(d_br.mean()), 5),
        "in_sample_model_coef": round(float(b[2]), 3), "in_sample_model_z": round(float(b[2] / np.sqrt(cov[2, 2])), 2),
        "verdict": ("MODEL_ADDS_INFORMATION" if ci_ll[1] is not None and ci_ll[1] < 0 else
                    "MODEL_HURTS" if ci_ll[0] is not None and ci_ll[0] > 0 else "NO_DETECTABLE_GAIN"),
        "reading": "delta < 0 means adding the model IMPROVED the forecast; the 90% interval must sit below 0",
    }


def under_diagnosis(D: pd.DataFrame) -> dict:
    """Calibration of the model on each side, conditioned on how far it leans from the market."""
    D = D.copy()
    D["lean"] = D["model_prob"] - D["p_market"]          # >0 model more OVER than the market
    out = {"n": int(len(D)),
           "overall": {"rate_over": round(float(D["y"].mean()), 4),
                       "model_p_over": round(float(D["model_prob"].mean()), 4),
                       "market_p_over": round(float(D["p_market"].mean()), 4)}}
    bands = pd.cut(D["lean"], [-1, -0.10, -0.05, -0.02, 0.02, 0.05, 0.10, 1],
                   labels=["model UNDER by >10pp", "UNDER 5-10pp", "UNDER 2-5pp", "agrees (±2pp)",
                           "OVER 2-5pp", "OVER 5-10pp", "model OVER by >10pp"])
    rows = {}
    for lab, g in D.groupby(bands, observed=True):
        rows[str(lab)] = {"n": int(len(g)), "realised_over": round(float(g["y"].mean()), 4),
                          "model_p_over": round(float(g["model_prob"].mean()), 4),
                          "market_p_over": round(float(g["p_market"].mean()), 4),
                          "model_error_pp": round(float((g["model_prob"].mean() - g["y"].mean()) * 100), 1),
                          "market_error_pp": round(float((g["p_market"].mean() - g["y"].mean()) * 100), 1),
                          "realised_ci90": C.block_ci(g["y"], g["match_date"])}
    out["by_model_lean"] = rows
    # How much of the model's lean shows up in the result? 1.0 = all of it, 0 = none (market right).
    D["real_minus_mkt"] = D["y"] - D["p_market"]
    for side, g in (("leans_under", D[D["lean"] < -0.02]), ("leans_over", D[D["lean"] > 0.02])):
        if len(g) >= 30:
            follow = float(g["real_minus_mkt"].mean() / g["lean"].mean())
            out[f"{side}_share_of_lean_realised"] = round(follow, 3)
            out[f"{side}_n"] = int(len(g))
    out["by_track"] = {t: {"n": int(len(g)), "model_error_pp": round(float((g["model_prob"].mean() - g["y"].mean()) * 100), 1),
                           "market_error_pp": round(float((g["p_market"].mean() - g["y"].mean()) * 100), 1),
                           "brier_model": round(float(C.brier(g["model_prob"], g["y"]).mean()), 4),
                           "brier_market": round(float(C.brier(g["p_market"], g["y"]).mean()), 4)}
                       for t, g in D.groupby("model_type")}
    # Calibration slope of the model's lean: regress (y - market) on lean. Slope ~0 = lean is noise.
    b, cov = C.fit_logistic(np.column_stack([C.logit(D["p_market"]), D["lean"]]), D["y"])
    out["lean_coef"] = round(float(b[2]), 3)
    out["lean_z"] = round(float(b[2] / np.sqrt(cov[2, 2])), 2)
    return out


def run() -> dict:
    R = C.results(START, END, v9_config.league_ids())
    out = {"window": [START, END], "results_fixtures": int(len(R)), "residual": {}, "under": None}
    for m in ("OU25", "OU15", "OU35", "BTTS"):
        D = panel(m, R)
        res = {"all": residual_test(D)}
        for t, g in D.groupby("model_type"):
            res[t] = residual_test(g)
        out["residual"][m] = res
        if m == "OU25":
            out["under"] = under_diagnosis(D)
    return out


if __name__ == "__main__":
    import json
    r = run()
    C.write("ou_studies", r)
    print(json.dumps(r, indent=1, default=str)[:9000])
