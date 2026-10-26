"""Correctness checks for the Standard repair programme (src/studies/standard_repair)."""
import numpy as np
import pandas as pd
from scipy.stats import poisson

from src.studies.standard_repair.candidates import pen_logit
from src.studies.standard_repair.data import _asof_roll, market_goal_split, power_devig, prop_devig
from src.studies.standard_repair.evaluate import bh


def test_power_devig_basic():
    p = power_devig(np.array([2.0, 1.9, 1.5]), np.array([2.0, 1.9, 0.9]))
    assert abs(p[0] - 0.5) < 1e-9 and abs(p[1] - 0.5) < 1e-9
    assert np.isnan(p[2])                                    # under price <= 1 is invalid
    assert np.isnan(power_devig(np.array([2.2]), np.array([2.2]))[0])   # overround < 1 = arbitrage
    q = prop_devig(np.array([1.8]), np.array([2.0]))[0]
    assert 0.5 < q < 0.55


def test_market_goal_split_recovers_lambdas():
    lh, la = 1.6, 1.1
    k = np.arange(15)
    joint = np.outer(poisson.pmf(k, lh), poisson.pmf(k, la))
    tot = np.add.outer(k, k)
    p_over = joint[tot > 2.5].sum()
    p_home = joint[np.subtract.outer(k, k) > 0].sum()
    p_away = joint[np.subtract.outer(k, k) < 0].sum()
    h, a = market_goal_split(np.array([p_over]), np.array([p_home]), np.array([p_away]))
    assert abs(h[0] - lh) < 0.02 and abs(a[0] - la) < 0.02


def test_asof_roll_excludes_same_date():
    d = pd.DataFrame({"league": ["L"] * 30, "date": pd.to_datetime(["2026-01-01"] * 20 + ["2026-01-08"] * 10),
                      "x": [0.0] * 20 + [100.0] * 10})
    r = _asof_roll(d, "x", n=80, minp=20)
    assert r.iloc[:20].isna().all()                          # nothing earlier than the first date
    assert (r.iloc[20:] == 0.0).all()                        # second date sees only first-date rows, never itself


def test_bh_and_pen_logit():
    q = bh({"a": 0.01, "b": 0.02, "c": 0.5})
    assert q["a"] == 0.03 and q["b"] == 0.03 and q["c"] == 0.5
    rng = np.random.default_rng(0)
    x = rng.normal(size=20000)
    y = (rng.random(20000) < 1 / (1 + np.exp(-(0.3 + 1.2 * x)))).astype(float)
    b = pen_logit(x[:, None], y, n_free=1)
    assert abs(b[0] - 0.3) < 0.08 and abs(b[1] - 1.2) < 0.08
