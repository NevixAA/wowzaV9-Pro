"""
Phase 4 remainder: drift monitoring, experiment provenance, system registry.

    python -m tests.test_drift_experiment
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.features.imputers import fit_imputer  # noqa: E402
from src.monitoring.drift import (feature_drift, health_summary,  # noqa: E402
                                  ks_statistic, prediction_drift, psi)
from src.pipelines.experiment import (Experiment, ExperimentManifest,  # noqa: E402
                                      experiment_id, write_system_registry)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def main() -> int:
    rng = np.random.default_rng(5)

    print("\n== PSI and KS detect what they are supposed to ==")
    base = rng.normal(0, 1, 5000)
    same = rng.normal(0, 1, 5000)
    shifted = rng.normal(1.5, 1, 5000)
    check("identical distributions -> PSI near 0", psi(base, same) < 0.05, str(psi(base, same)))
    check("shifted distribution -> PSI large", psi(base, shifted) > 0.25,
          str(psi(base, shifted)))
    check("identical -> KS small", ks_statistic(base, same) < 0.05)
    check("shifted -> KS large", ks_statistic(base, shifted) > 0.15)
    check("PSI of a constant training feature is 0, not an error",
          psi(np.zeros(100), rng.normal(0, 1, 100)) == 0.0)
    check("empty input -> nan rather than a crash", np.isnan(psi(np.array([]), base)))

    print("\n== feature drift against the training manifest ==")
    train = pd.DataFrame({
        "match_date": pd.date_range("2025-01-01", periods=2000).astype(str),
        "stable": rng.normal(0, 1, 2000),
        "will_shift": rng.normal(0, 1, 2000),
        "will_break": rng.normal(5, 2, 2000),
        "will_vanish": rng.normal(0, 1, 2000),
    })
    man = fit_imputer(train, ["stable", "will_shift", "will_break", "will_vanish"],
                      required=["will_break"])

    serve = pd.DataFrame({
        "stable": rng.normal(0, 1, 500),
        "will_shift": rng.normal(2.0, 1, 500),      # distribution moved
        "will_break": np.full(500, 5.0),            # constant: enrichment stopped arriving
        # will_vanish absent entirely
    })
    dd = feature_drift(serve, man, train_reference=train)
    by = {r["feature"]: r for _, r in dd.iterrows()}

    check("a stable feature is OK", by["stable"]["severity"] == "OK",
          str(by["stable"]["severity"]))
    check("a shifted feature is flagged",
          "PSI_SIGNIFICANT" in by["will_shift"]["flags"], by["will_shift"]["flags"])
    check("a feature that went constant is flagged",
          "DEGENERATE_AT_SERVE" in by["will_break"]["flags"], by["will_break"]["flags"])
    check("a REQUIRED feature going constant is CRITICAL, not a warning",
          by["will_break"]["severity"] == "CRITICAL", by["will_break"]["severity"])
    check("a vanished feature is flagged missing",
          "MISSING_AT_SERVE" in by["will_vanish"]["flags"], by["will_vanish"]["flags"])
    check("worst severity is sorted first", dd.iloc[0]["severity"] == "CRITICAL")
    check("PSI and KS both reported", by["will_shift"]["psi"] is not None
          and by["will_shift"]["ks"] is not None)

    print("\n== out-of-range serving values are their own signal ==")
    oor = pd.DataFrame({"stable": np.r_[rng.normal(0, 1, 400), np.full(100, 99.0)],
                        "will_shift": rng.normal(0, 1, 500),
                        "will_break": rng.normal(5, 2, 500)})
    d2 = feature_drift(oor, man, train_reference=train)
    row = d2[d2.feature == "stable"].iloc[0]
    check("out-of-range percentage measured", row["out_of_range_pct"] > 0.05,
          str(row["out_of_range_pct"]))
    check("and flagged", "OUT_OF_RANGE" in row["flags"], row["flags"])

    print("\n== drift works from the manifest alone (no training sample shipped) ==")
    d3 = feature_drift(serve, man)          # no train_reference
    check("still runs", len(d3) == 4)
    check("still catches the constant feature",
          "DEGENERATE_AT_SERVE" in d3[d3.feature == "will_break"].iloc[0]["flags"])
    check("PSI omitted rather than invented",
          pd.isna(d3[d3.feature == "will_shift"].iloc[0]["psi"]))

    print("\n== health summary ==")
    hs = health_summary(dd)
    check("status reflects the worst finding", hs["status"] == "CRITICAL", str(hs))
    check("counts present", hs["critical"] >= 1)
    check("worst features named", "will_break" in hs["worst_features"], str(hs))

    print("\n== prediction drift catches an inert model ==")
    # v9's HT model sat in 0.68-0.72 against thresholds of >=0.75 and <=0.30: every feature
    # healthy, and the model structurally unable to fire.
    inert = prediction_drift(rng.uniform(0.2, 0.9, 2000), rng.uniform(0.68, 0.72, 300))
    check("collapsed prediction range flagged",
          "PREDICTION_RANGE_COLLAPSED" in inert["flags"], inert["flags"])
    healthy = prediction_drift(rng.uniform(0.2, 0.9, 2000), rng.uniform(0.2, 0.9, 300))
    check("a healthy spread is not flagged", healthy["flags"] == "", healthy["flags"])
    const = prediction_drift(rng.uniform(0.2, 0.9, 500), np.full(200, 0.5))
    check("constant predictions flagged", "PREDICTIONS_CONSTANT" in const["flags"])
    check("no data handled", prediction_drift([], []).get("flags") == "NO_DATA")

    print("\n== experiment ids are deterministic ==")
    a = experiment_id(name="ou25", git="abc", config_hash="c1", when="2026-08-18T00:00:00Z")
    b = experiment_id(name="ou25", git="abc", config_hash="c1", when="2026-08-18T00:00:00Z")
    c = experiment_id(name="ou25", git="abc", config_hash="c2", when="2026-08-18T00:00:00Z")
    check("same inputs -> same id", a == b)
    check("a different config -> a different id", a != c)
    check("id carries the name", a.startswith("ou25-"))

    print("\n== an experiment directory is immutable ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mf = ExperimentManifest(experiment_id=a, name="ou25", model_id="m1",
                                validation_type="chronological_4block",
                                odds_policy="REAL_ONLY", rows={"train": 100, "holdout": 50})
        ex = Experiment(mf, root=root)
        out = ex.save(metrics={"logloss_improvement": 0.004, "brier_improvement": 0.001},
                      by_league=pd.DataFrame([{"league": "A", "n": 120}]),
                      calibration=pd.DataFrame([{"bin": 1, "expected": 0.2, "observed": 0.19}]),
                      bets=pd.DataFrame([{"fixture_key": "k1", "odds": 1.9, "pnl": 0.9}]))
        for f in ("manifest.json", "metrics.json", "by_league.csv", "calibration.csv",
                  "bets.parquet"):
            check(f"{f} written", (out / f).exists())
        try:
            ex.save(metrics={"logloss_improvement": 999})
            check("re-saving the same experiment is refused", False, "it was allowed")
        except FileExistsError:
            check("re-saving the same experiment is refused", True)

        m2, met = Experiment.load(out)
        check("manifest round-trips", m2.experiment_id == a
              and m2.validation_type == "chronological_4block")
        check("metrics round-trip", met["logloss_improvement"] == 0.004)
        check("bets are recomputable from the parquet",
              len(pd.read_parquet(out / "bets.parquet")) == 1)

        idx = Experiment.index(root)
        check("index lists the experiment", len(idx) == 1 and idx.iloc[0]["name"] == "ou25")

        print("\n== system registry is one canonical answer ==")
        reg_tbl = pd.DataFrame([
            {"model_id": "m_live", "status": "LIVE", "market": "OU25", "scope": "new_format"},
            {"model_id": "m_old", "status": "RETIRED", "market": "OU25", "scope": "new_format"},
        ])
        p = write_system_registry(registry_table=reg_tbl,
                                  store_stats={"model_snapshots": {"rows": 7028}},
                                  drift_health=hs, path=root / "system_registry.json")
        reg = json.loads(p.read_text(encoding="utf-8"))
        check("only LIVE models listed", reg["n_live_models"] == 1
              and reg["live_models"][0]["model_id"] == "m_live", str(reg["n_live_models"]))
        check("staking is stated explicitly, not implied", reg["pro_may_stake"] is False)
        check("notification is stated explicitly", reg["pro_may_notify"] is False)
        check("feature health carried through", reg["feature_health"]["status"] == "CRITICAL")
        check("store stats carried through",
              reg["season_store"]["model_snapshots"]["rows"] == 7028)
        check("season recorded", reg["season"].startswith("season_"))
        check("git sha recorded", bool(reg["git_sha"]))

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
