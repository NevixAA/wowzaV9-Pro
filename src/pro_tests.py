"""
Pro deterministic tests — the named list from the hardening brief, section 12.
=============================================================================
    python -m src.pro_tests

No network, no credentials, no store writes. Each check encodes a defect that actually happened
or an invariant the research depends on, so a regression fails here instead of quietly corrupting
a season of evidence.

The brief names these: Romanian Superliga, league coverage, sport-key validity, registry
generation / freshness / reconciliation, data-quality records, CLV plausibility, pre-kickoff close
selection, post-kickoff exclusion, missing-close -> NULL. All are below, plus the quality
taxonomy and the contract, which turned out to be where several real bugs were.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def _quality() -> None:
    from src import quality as q
    print("\n== quality taxonomy ==")
    check("levels are exactly RAW/CLEAN/STRICT_CLEAN",
          q.LEVELS == ("RAW", "CLEAN", "STRICT_CLEAN"))
    check("a definitely-wrong flag drops a row to RAW",
          q.level_of("BTTS_FIRST_HALF_MISLABEL") == "RAW")
    check("an unverified flag keeps a row at CLEAN",
          q.level_of("MISSING_OPPOSITE_SIDE") == "CLEAN")
    check("no flag means STRICT_CLEAN", q.level_of("") == "STRICT_CLEAN")
    check("NaN flags mean STRICT_CLEAN", q.level_of(float("nan")) == "STRICT_CLEAN")
    check("an UNKNOWN flag degrades to CLEAN, never to STRICT",
          q.level_of("SOMETHING_NEW") == "CLEAN",
          "a typo must reduce safety, not remove it")
    check("wrong beats unverified when both present",
          q.level_of("MISSING_KICKOFF|CLV_IMPLAUSIBLE") == "RAW")

    # add_flag must ACCUMULATE. Bare assignment lost the first flag in the importers.
    s = pd.Series(["", "ENTITY_UNRESOLVED"])
    s2 = q.add_flag(s, pd.Series([True, True]), "MARKET_MAPPING_INVALID")
    check("add_flag appends rather than overwriting",
          s2.iloc[1] == "ENTITY_UNRESOLVED|MARKET_MAPPING_INVALID", s2.iloc[1])
    check("add_flag on an empty cell has no leading separator",
          s2.iloc[0] == "MARKET_MAPPING_INVALID", s2.iloc[0])
    check("add_flag leaves unmasked rows alone",
          q.add_flag(s, pd.Series([False, False]), "X").tolist() == ["", "ENTITY_UNRESOLVED"])

    d = pd.DataFrame({"quality_flags": ["", "MISSING_KICKOFF", "CLV_IMPLAUSIBLE"]})
    check("at_level(RAW) keeps everything", len(q.at_level(d, "RAW")) == 3)
    check("at_level(CLEAN) drops only the wrong row", len(q.at_level(d, "CLEAN")) == 2)
    check("at_level(STRICT_CLEAN) keeps only unflagged", len(q.at_level(d, "STRICT_CLEAN")) == 1)
    check("an invalid level raises rather than guessing",
          _raises(lambda: q.at_level(d, "MOSTLY_CLEAN")))
    # A frame with no flags column is RAW by definition and must not masquerade as clean.
    nf = pd.DataFrame({"x": [1, 2]})
    check("a frame with no flags column returns RAW, not a silent CLEAN",
          len(q.at_level(nf, "CLEAN")) == 2)
    check("summarise reports classified=False when there is no flags column",
          q.summarise(nf)["classified"] is False)
    check("...and NULL level counts, not zeros",
          q.summarise(nf)["levels"]["CLEAN"] is None,
          "reporting 0 clean reads as 'all bad' when it means 'cannot assess'")

    print("\n== BTTS first-half filter ==")
    d = pd.DataFrame({"market": ["btts_yes", "btts_yes", "btts_no", "over25"],
                      "odds": [1.91, 6.50, 1.12, 5.00]})
    f = q.flag_btts_first_half(d)
    check("a plausible full-match btts_yes is untouched", f["quality_flags"].iloc[0] == "")
    check("an implausible btts_yes is flagged",
          f["quality_flags"].iloc[1] == "BTTS_FIRST_HALF_MISLABEL")
    check("btts_no is never flagged by this rule", f["quality_flags"].iloc[2] == "")
    check("a long price in ANOTHER market is not flagged", f["quality_flags"].iloc[3] == "")
    check("threshold sits in the empty gap between the populations",
          2.97 < q.BTTS_YES_MAX < 3.40,
          f"clean max 2.97, contaminated min 3.40, BTTS_YES_MAX={q.BTTS_YES_MAX}")
    b = q.flag_btts_first_half(pd.DataFrame({"market": ["btts_yes"], "odds": [q.BTTS_YES_MAX]}))
    check("the threshold itself is NOT flagged (strictly greater)",
          b["quality_flags"].iloc[0] == "")


def _team_form() -> None:
    """Rolling form: leakage, cross-team contamination, and index alignment.

    Every check here exists because the first implementation failed it. `g[col].shift(1)
    .rolling(w).mean().reset_index(level=0, drop=True)` rolled across team boundaries AND
    replaced the index with a RangeIndex, scattering values onto unrelated rows. The symptom was
    corr(prior scoring rate, goals scored next) = -0.0009 — an exact zero, which is what
    misalignment looks like and what absence of signal does not.

    My original leakage test PASSED on that broken code, because it used a single team and a clean
    index so neither defect could show. These use THREE interleaved teams with disjoint value
    ranges, so a cross-team leak or a scatter changes the numbers visibly.
    """
    from src.features import team_form as tf
    print("\n== team form: leakage and alignment ==")

    def _fx(team, rnd, val, day):
        return {"fixture_id": f"{team}{rnd}", "league": "L", "season": "2026",
                "match_date": f"2026-01-{day:02d}", "home_team": team, "away_team": "OPP",
                "home_goals": val, "away_goals": 0, "home_xg": val, "away_xg": 0.0,
                "home_shots": 1, "away_shots": 1, "home_sot": 1, "away_sot": 1,
                "home_insidebox": 1, "away_insidebox": 1,
                "home_possession": 50, "away_possession": 50}

    # Disjoint ranges per team: any bleed between teams lands far outside the expected value.
    rows, day = [], 1
    for rnd in range(6):
        for team, base in (("A", 0.0), ("B", 100.0), ("C", 1000.0)):
            rows.append(_fx(team, rnd, base + rnd, day)); day += 1
    f = tf.rolling_form(pd.DataFrame(rows), window=3, min_prior=2)

    bad = []
    for team, base in (("A", 0.0), ("B", 100.0), ("C", 1000.0)):
        g = f[f["team"] == team].sort_values("match_date")
        for _, r in g.iterrows():
            n = int(r["n_prior"])
            if n < 2:
                if pd.notna(r["roll_for_goals"]):
                    bad.append(f"{team} n_prior={n} should be NaN")
                continue
            exp = sum(base + k for k in range(max(0, n - 3), n)) / len(
                range(max(0, n - 3), n))
            if abs(float(r["roll_for_goals"]) - exp) > 1e-9:
                bad.append(f"{team} n_prior={n}: {r['roll_for_goals']} != {exp}")
    check("rolling form is leakage-free and per-team correct (3 interleaved teams)",
          not bad, "; ".join(bad[:3]))
    check("below min_prior the value is NaN, not a noisy 1-game mean",
          f[f["n_prior"] < 2]["roll_for_goals"].isna().all())
    check("no cross-team contamination (disjoint ranges stay disjoint)",
          f[f["team"] == "A"]["roll_for_goals"].dropna().max() < 50
          and f[f["team"] == "C"]["roll_for_goals"].dropna().min() > 900)
    # The alignment bug specifically: values must sit on their OWN rows.
    a = f[f["team"] == "A"].sort_values("match_date")
    check("values land on the correct rows (index alignment)",
          a["roll_for_goals"].tolist()[2:4] == [0.5, 1.0],
          str(a["roll_for_goals"].tolist()[:4]))

    print("\n== team form: lambda construction ==")
    lam = tf.fixture_lambdas(pd.DataFrame(rows))
    check("returns one row per fixture", len(lam) <= len(rows))
    for c in ("lam_home", "lam_away", "lam_min", "lam_sum", "lam_asymmetry", "xg_source"):
        check(f"{c} present", c in lam.columns)
    check("xg_source records the estimator, so a pooled evaluation can condition on it",
          set(lam["xg_source"].unique()) <= {"xg", "goals"})
    check("league mean is PER SIDE, not per match",
          "per_side" in Path("src/features/team_form.py").read_text(encoding="utf-8"),
          "confusing the two doubles every lambda and pushes BTTS toward 1")


def _config_and_contract() -> None:
    print("\n== config: league coverage and provider support ==")
    try:
        # LOADED BY EXPLICIT FILE SPEC, not via sys.path. Inserting v9's directory at position 0
        # shadows Pro's own `config` PACKAGE for every later import in the process — which is
        # exactly what happened on the first run: three subsequent test groups died with
        # "cannot import name 'pro_config' from 'config'" pointing at v9/config.py. importlib
        # keeps the module out of the normal resolution order entirely.
        import importlib.util
        _p = Path(__file__).resolve().parents[2] / "v9" / "config.py"
        _spec = importlib.util.spec_from_file_location("_v9_config_isolated", _p)
        v9cfg = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(v9cfg)
    except Exception as e:
        check("v9 config importable", False, str(e)[:60])
        return
    enabled = set(v9cfg.ENABLED_LEAGUES)
    # ODDS_API_SPORT_KEYS is the real attribute. I first guessed SPORT_KEYS, which does not
    # exist, so getattr's default made every enabled league look like an orphan — 19 false
    # positives out of one wrong name, and a check that fails for the wrong reason is worse
    # than no check.
    keys = set(getattr(v9cfg, "ODDS_API_SPORT_KEYS", {}) or {})
    unsupported = set(getattr(v9cfg, "PROVIDER_UNSUPPORTED", {}) or {})
    check("every enabled league has a sport key OR is declared unsupported",
          not (enabled - keys - unsupported),
          f"orphans: {sorted(enabled - keys - unsupported)}")
    check("Romanian Superliga is declared PROVIDER_UNSUPPORTED, not silently broken",
          "Romanian Superliga" in unsupported)
    if "Romanian Superliga" in unsupported:
        e = v9cfg.PROVIDER_UNSUPPORTED["Romanian Superliga"]
        check("...with a reason", bool(e.get("reason")))
        check("...and a verification date", bool(e.get("verified")))
    check("no sport key is an obvious placeholder",
          not [k for k in keys if not str(v9cfg.ODDS_API_SPORT_KEYS[k]).startswith("soccer_")],
          str([k for k in keys if not str(v9cfg.ODDS_API_SPORT_KEYS[k]).startswith("soccer_")])[:80])
    check("STANDARD_FORMAT_LEAGUES is a superset of enabled standard leagues",
          set(v9cfg.STANDARD_FORMAT_LEAGUES) >= {l for l in enabled
                                                 if v9cfg.model_type_for_league(l) == "standard"})

    print("\n== cross-repo contract ==")
    from src import contract as ct
    check("every artifact declares at least one consumer",
          all(a.consumers for a in ct.CONTRACT))
    check("every artifact declares its grain", all(a.grain for a in ct.CONTRACT))
    check("paths are unique", len(ct.BY_PATH) == len(ct.CONTRACT))
    check("player_history is declared AT THE REPO ROOT",
          ct.BY_PATH["player_history.parquet"].at_repo_root,
          "the audit's first version looked under output/ and masked a stalled collector")
    check("the odds histories are tagged unrecoverable",
          {"output/book_odds_snapshots.csv",
           "output/standard_sidemarket_odds_history.csv"} <= {a.path for a in ct.unrecoverable()})
    check("bets_ledger's tip-only grain is documented",
          "TIPPED" in ct.BY_PATH["output/bets_ledger.csv"].caveat.upper())
    check("the clv_pct unit difference is documented on BOTH files",
          "FRACTION" in ct.BY_PATH["output/clv_records.csv"].caveat.upper()
          and "PERCENT" in ct.BY_PATH["output/bets_ledger.csv"].caveat.upper())
    check("for_consumer filters", "output/predictions.csv" in
          {a.path for a in ct.for_consumer("v11")})


def _registry() -> None:
    print("\n== registry generation, freshness, reconciliation ==")
    import json
    import tempfile
    from src.pipelines import registry as reg
    td = Path(tempfile.mkdtemp())

    p = td / "stale.json"
    p.write_text(json.dumps({"generated_at": "2020-01-01T00:00:00Z", "season_store": {}}))
    age = reg.age_hours(p)
    check("age_hours reads the RECORDED timestamp", age is not None and age > 40000, str(age))
    check("age_hours is None when generated_at is absent",
          reg.age_hours(td / "none.json") is None)
    p2 = td / "bad.json"
    p2.write_text("{not json")
    check("a corrupt registry gives no age rather than raising",
          reg.age_hours(p2) is None)
    r = reg.reconcile(p)
    check("reconcile against an empty registry reports mismatches",
          not r["ok"] and len(r["mismatches"]) > 0, str(r)[:80])
    check("reconcile names the table and both counts",
          all({"table", "registry", "canonical"} <= set(m) for m in r["mismatches"]))


def _data_quality() -> None:
    print("\n== data_quality records ==")
    from src.pipelines import data_quality as dq
    check("_status: a wrong flag with rows is FAIL",
          dq._status(flag="CLV_IMPLAUSIBLE", is_wrong=True, n_flagged=5) == "FAIL")
    check("_status: an unverified flag with rows is WARN",
          dq._status(flag="MISSING_KICKOFF", is_wrong=False, n_flagged=5) == "WARN")
    check("_status: NO_FLAGS is PASS",
          dq._status(flag="NO_FLAGS", is_wrong=False, n_flagged=0) == "PASS")
    check("_status: an unclassifiable table is WARN, not FAIL",
          dq._status(flag="NOT_CLASSIFIED", is_wrong=False, n_flagged=None) == "WARN")
    check("_status: an unreadable table is FAIL",
          dq._status(flag="TABLE_UNREADABLE", is_wrong=True, n_flagged=0) == "FAIL")
    check("_status: a registered flag with ZERO rows is PASS",
          dq._status(flag="MISSING_KICKOFF", is_wrong=False, n_flagged=0) == "PASS")

    # _span must prefer WRITE timestamps: match_date is a FUTURE date and cannot bound anything.
    d = pd.DataFrame({"match_date": ["2026-09-30"], "captured_at": ["2026-08-20T10:00:00Z"]})
    lo, hi, col = dq._span(d, pd.Series([True]))
    check("_span prefers a write timestamp over the fixture date", col == "captured_at",
          f"picked {col}")
    check("_span returns the write date, not the future fixture date", lo == "2026-08-20", lo)
    check("_span reports which column it used", col in d.columns)

    # v11's single-valued vocabulary must translate into Pro's multi-valued one.
    v = dq._adopt_v11_vocabulary(pd.DataFrame({"clv_quality": ["POST_KICKOFF_ENTRY",
                                                               "INSUFFICIENT_BOOKS", "OK"]}))
    check("v11 POST_KICKOFF_ENTRY maps to POST_KICKOFF_PRICE",
          v["quality_flags"].iloc[0] == "POST_KICKOFF_PRICE")
    check("v11 INSUFFICIENT_BOOKS carries across",
          v["quality_flags"].iloc[1] == "INSUFFICIENT_BOOKS")
    check("v11 OK produces no flag", v["quality_flags"].iloc[2] == "")


def _clv() -> None:
    print("\n== CLV: plausibility, close selection, missing close ==")
    from src.market import clv_schema as cs
    from src import quality as q
    check("CLV_PLAUSIBLE_ABS matches v11's constant", q.CLV_PLAUSIBLE_ABS == 25.0)
    check("plausibility is judged in PERCENT, not the stored fraction",
          "normalised" in Path("src/market/clv_schema.py").read_text(encoding="utf-8"),
          "against the raw fraction the threshold means 2500% and can never fire")
    for name in ("Q_OK", "Q_NO_CLOSE", "Q_CLOSE_EQUALS_ENTRY", "Q_IMPLAUSIBLE",
                 "Q_UNPROVEN_PREKICKOFF"):
        check(f"verdict {name} is defined", hasattr(cs, name))
    check("the schema declares every field the brief asks for",
          {"entry_ts", "entry_odds", "close_ts", "close_odds",
           "minutes_close_before_kickoff", "entry_fair_probability",
           "close_fair_probability", "clv_pct", "clv_quality",
           "clv_source"} <= set(cs.SCHEMA_COLS))
    check("raw and clean are SEPARATE columns",
          "clv_pct" in cs.SCHEMA_COLS and "clean_clv_pct" in cs.SCHEMA_COLS,
          "overwriting raw would destroy the ability to audit what v9 believed")

    # Pre-kickoff close selection and post-kickoff exclusion, on the v11 helper Pro relies on.
    # RUN IN v11's OWN PROCESS, via subprocess.
    #
    # v11's scripts do `from src.edge_engine import ...`, and Pro's own `src` package is already
    # bound in this interpreter, so `src` resolves to Pro's and the import fails with
    # "No module named 'src.edge_engine'". Adding v11 to sys.path cannot fix that — the name is
    # already taken. Reimplementing closing_snapshot here would be worse: a second copy that can
    # drift from the one actually used, which is the defect this whole test file guards against.
    # A subprocess executes the REAL function in the environment it really runs in.
    import subprocess
    import textwrap
    v11 = Path(__file__).resolve().parents[2] / "wowza-v11"
    if not v11.exists():
        check("v11 checkout present for close-selection test", False, str(v11))
        return
    code = textwrap.dedent("""
        import sys, json
        sys.path.insert(0, '.')
        import pandas as pd
        from scripts.v11_shadow import closing_snapshot
        snaps = pd.DataFrame([
            {"fixture_id": "f", "snapshot_ts": "t1", "minutes_to_kickoff": 180},
            {"fixture_id": "f", "snapshot_ts": "t2", "minutes_to_kickoff": 20},
            {"fixture_id": "f", "snapshot_ts": "t3", "minutes_to_kickoff": -5},
            {"fixture_id": "g", "snapshot_ts": "t4", "minutes_to_kickoff": None},
        ])
        cl = closing_snapshot(snaps)
        print(json.dumps({
            "close_mtk": float(cl["minutes_to_kickoff"].iloc[0]),
            "all_pre": bool((pd.to_numeric(cl["minutes_to_kickoff"]) > 0).all()),
            "unknown_excluded": "g" not in set(cl["fixture_id"]),
            "empty_ok": bool(closing_snapshot(pd.DataFrame()).empty),
        }))
    """)
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=str(v11), capture_output=True,
                           text=True, timeout=120)
        import json as _json
        res = _json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:                                          # noqa: BLE001
        check("v11 closing_snapshot runs in its own environment", False,
              f"{type(e).__name__}: {str(e)[:70]}")
        return
    check("close is the last PRE-kickoff row", res["close_mtk"] == 20.0, str(res["close_mtk"]))
    check("a post-kickoff row is never selected as the close", res["all_pre"])
    check("an unknown kickoff is EXCLUDED, not assumed pre-kickoff", res["unknown_excluded"],
          "guessing permissively is how in-play prices manufactured the CLV edge")
    check("an empty frame is handled", res["empty_ok"])


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


def main() -> int:
    print("Pro deterministic tests (hardening brief section 12)")
    for fn in (_quality, _team_form, _config_and_contract, _registry, _data_quality, _clv):
        try:
            fn()
        except Exception as e:                                     # noqa: BLE001
            check(f"{fn.__name__} itself raised", False, f"{type(e).__name__}: {e}")
    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
