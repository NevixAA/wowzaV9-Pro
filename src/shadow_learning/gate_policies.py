"""If the promotion gate is a coin flip, what should replace it? Backtest the candidates.

    python -m src.shadow_learning.gate_policies --write

The gate backtest established that v9's current rule promotes 95% of the time, is right barely
more than a coin flip when it does, and is wrong roughly 70% of the time when it refuses. That
is a finding about the rule, not a design for a better one. This tests designs.

THE MEASURE IS THE OUTCOME, NOT THE DECISION. "How often was the gate right?" is the wrong
scoreboard -- a rule that is right 90% of the time on trivial calls and wrong on the one that
matters is worse than the reverse. What matters is how the model that was ACTUALLY SERVING
performed on the months it had not seen. So every policy is scored on the realised log loss of
whatever model it had live, month after month, on identical fixtures.

ONE CHALLENGER, MANY POLICIES. Every policy sees the same monthly sequence of challengers, so
the expensive part -- fitting -- happens once per month and each policy simply replays its own
adopt-or-keep decision over that shared sequence. That makes eight policies cost barely more
than one, and it also removes a confound: no policy can look better because it happened to get
a luckier challenger.

THE TWO POLICIES THAT MUST BE IN THE COMPARISON are the trivial ones, because a gate has to beat
both to justify existing at all:

    always    adopt every challenger, no gate whatsoever
    never     keep the first model forever (the frozen control)

If no gate beats `always`, the honest recommendation is to delete the gate rather than tune it.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M
from src.shadow_learning import experiments as X

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")
MIN_TRAIN = 6000
START = "2022-08"


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Policy:
    name: str
    rule: str
    tol: float = 0.0
    val_months: int = 3
    note: str = ""
    # live state, per target
    champ: dict = field(default_factory=dict)

    def decide(self, *, ll_champ: float, ll_cand: float, ll_champ_prev: float | None,
               ll_cand_prev: float | None) -> bool:
        if self.rule == "always":
            return True
        if self.rule == "never":
            return False
        if not np.isfinite(ll_champ) or not np.isfinite(ll_cand):
            return True                       # nothing to compare against yet
        if self.rule == "not_worse":          # v9's current rule
            return ll_cand <= ll_champ + self.tol
        if self.rule == "must_improve":       # strictly better, by a margin
            return ll_cand <= ll_champ - self.tol
        if self.rule == "two_window":         # better on BOTH a recent and an earlier slice
            if ll_champ_prev is None or not np.isfinite(ll_cand_prev):
                return ll_cand <= ll_champ + self.tol
            return (ll_cand <= ll_champ + self.tol) and (ll_cand_prev <= ll_champ_prev + self.tol)
        raise KeyError(self.rule)


def policies() -> list[Policy]:
    return [
        Policy("always_promote", "always",
               note="no gate at all -- the bar every gate has to clear"),
        Policy("never_promote", "never",
               note="keep the first model forever -- the frozen control"),
        Policy("v9_current_tol005", "not_worse", tol=0.005, val_months=3,
               note="v9's live rule: promote unless log loss rises more than 0.005"),
        Policy("not_worse_tol000", "not_worse", tol=0.0, val_months=3,
               note="promote unless it got worse at all"),
        Policy("must_improve_tol000", "must_improve", tol=0.0, val_months=3,
               note="promote only on a strict improvement"),
        Policy("must_improve_tol002", "must_improve", tol=0.002, val_months=3,
               note="promote only on a clear improvement"),
        Policy("v9_rule_6m_window", "not_worse", tol=0.005, val_months=6,
               note="v9's rule but judged on six months of validation, not three"),
        Policy("two_window_tol005", "two_window", tol=0.005, val_months=3,
               note="must hold up on a recent AND an earlier validation slice"),
    ]


def _fit(X_, y, rows):
    zoo = FO.model_zoo(fast=True)
    keep = np.array([np.unique(X_[rows, j][np.isfinite(X_[rows, j])]).size >= 3
                     and np.isfinite(X_[rows, j]).sum() >= 200 for j in range(X_.shape[1])])
    if not keep.any() or len(np.unique(y[rows])) < 2:
        return None, None
    m = zoo["hgb"]()
    m.fit(X_[np.ix_(rows, np.flatnonzero(keep))], y[rows])
    return m, keep


def _pred(model, keep, X_, rows):
    return model.predict_proba(X_[np.ix_(rows, np.flatnonzero(keep))])[:, 1]


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    U = X.universes()
    base = X._prepare(U["_can_frame"])
    feat = F.build(base)
    cols = F.feature_columns(feat, F.FOOTBALL_FAMILIES)
    Xm = feat[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    dates = pd.to_datetime(feat["date"])
    months = [m for m in pd.PeriodIndex(dates.dt.to_period("M").unique()).sort_values()
              if m >= pd.Period(START, freq="M")]
    print(f"[gate] {len(feat):,} fixtures, {len(months)} months, "
          f"{len(policies())} policies x {len(TARGETS)} targets")

    rows, decisions = [], []
    for t in TARGETS:
        y = feat[t].to_numpy(dtype=int)
        pols = policies()
        for p in pols:
            p.champ = {}
        for mon in months:
            ms, me = mon.to_timestamp(), (mon + 1).to_timestamp()
            te = np.flatnonzero((dates >= ms) & (dates < me))
            tr = np.flatnonzero(dates < ms)
            if len(tr) < MIN_TRAIN or len(te) < 60 or len(np.unique(y[te])) < 2:
                continue
            cand, ckeep = _fit(Xm, y, tr)
            if cand is None:
                continue
            y_te = y[te]
            p_cand_test = _pred(cand, ckeep, Xm, te)
            ll_cand_test = M.log_loss(y_te, p_cand_test)

            # Validation slices, both strictly before this month.
            def slice_rows(k_from, k_to):
                a = ms - pd.DateOffset(months=k_from)
                b = ms - pd.DateOffset(months=k_to)
                return tr[(dates.to_numpy()[tr] >= np.datetime64(a))
                          & (dates.to_numpy()[tr] < np.datetime64(b))]

            for p in pols:
                va_recent = slice_rows(p.val_months, 0)
                va_earlier = slice_rows(p.val_months * 2, p.val_months)
                have = p.champ.get(t)
                if have is None:
                    adopt = True
                    ll_c = ll_k = ll_cp = ll_kp = float("nan")
                else:
                    km, kk = have
                    ll_k = (M.log_loss(y[va_recent], _pred(km, kk, Xm, va_recent))
                            if len(va_recent) >= 200 else float("nan"))
                    ll_c = (M.log_loss(y[va_recent], _pred(cand, ckeep, Xm, va_recent))
                            if len(va_recent) >= 200 else float("nan"))
                    ll_kp = (M.log_loss(y[va_earlier], _pred(km, kk, Xm, va_earlier))
                             if len(va_earlier) >= 200 else float("nan"))
                    ll_cp = (M.log_loss(y[va_earlier], _pred(cand, ckeep, Xm, va_earlier))
                             if len(va_earlier) >= 200 else float("nan"))
                    adopt = p.decide(ll_champ=ll_k, ll_cand=ll_c,
                                     ll_champ_prev=ll_kp, ll_cand_prev=ll_cp)
                if adopt:
                    p.champ[t] = (cand, ckeep)
                am, ak = p.champ[t]
                p_live = _pred(am, ak, Xm, te)
                ll_live = M.log_loss(y_te, p_live)
                rows.append({"policy": p.name, "target": t, "month": str(mon),
                             "n_test": int(len(te)), "live_log_loss": round(ll_live, 5),
                             "live_brier": round(M.brier(y_te, p_live), 5),
                             "challenger_log_loss": round(ll_cand_test, 5),
                             "adopted": bool(adopt)})
                decisions.append({"policy": p.name, "target": t, "month": str(mon),
                                  "adopted": bool(adopt),
                                  "val_champ": round(ll_k, 5) if np.isfinite(ll_k) else None,
                                  "val_cand": round(ll_c, 5) if np.isfinite(ll_c) else None,
                                  "next_month_live": round(ll_live, 5),
                                  "next_month_challenger": round(ll_cand_test, 5)})
        print(f"   {t} done")
    return pd.DataFrame(rows), pd.DataFrame(decisions)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    led, dec = run()
    if led.empty:
        print("nothing evaluated")
        return 1

    piv = led.pivot_table(index="policy", columns="target", values="live_log_loss")
    piv["mean_ll"] = piv.mean(axis=1)
    rate = led.groupby("policy")["adopted"].mean().rename("adopt_rate")
    piv = piv.join(rate).sort_values("mean_ll")
    print("\nREALISED PERFORMANCE OF WHATEVER MODEL WAS ACTUALLY LIVE")
    print("(lower is better — this is the outcome, not the decision accuracy)")
    print(piv.round(5).to_string())

    # Significance against the no-gate baseline, paired by month x target.
    from src.validation.multiple_testing import paired_bootstrap_p
    base = led[led.policy == "always_promote"].set_index(["target", "month"])["live_log_loss"]
    out = []
    for p in sorted(led.policy.unique()):
        if p == "always_promote":
            continue
        s = led[led.policy == p].set_index(["target", "month"])["live_log_loss"]
        common = base.index.intersection(s.index)
        pv, obs, ci = paired_bootstrap_p(s[common].to_numpy(), base[common].to_numpy(),
                                         n_boot=3000, block=4)
        out.append({"policy": p, "vs": "always_promote", "mean_diff": round(obs, 6),
                    "ci_lo": round(ci[0], 6), "ci_hi": round(ci[1], 6),
                    "p_value": round(pv, 4),
                    "significant": bool(ci[0] > 0 or ci[1] < 0),
                    "direction": "policy better" if obs < 0 else "no gate better"})
    b = pd.DataFrame(out)
    print("\nAGAINST NO GATE AT ALL (negative mean_diff = the policy beat 'promote everything')")
    print(b.to_string(index=False))

    best = piv.index[0]
    print(f"\n  best policy by realised log loss: {best}")
    print(f"  does ANY gate beat 'always promote'? "
          f"{'YES' if (b.significant & (b.mean_diff < 0)).any() else 'NO'}")

    if a.write:
        led.to_csv(O() / "gate_policy_performance.csv", index=False)
        b.to_csv(O() / "gate_policy_significance.csv", index=False)
        dec.to_csv(O() / "gate_policy_decisions.csv", index=False)
        print(f"\n[gate] wrote 3 artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
