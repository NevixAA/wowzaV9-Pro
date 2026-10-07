"""Side markets must reach Pro's studies, not be dropped at load.

THE DEFECT THIS PINS. The side-market settlements frame omitted `edge_pct` while the
main-market frame carried it. threshold_curves.load() drops rows whose edge_pct is NaN, so every
BTTS / OVER15 / OVER35 row was discarded on load and Pro's threshold verdicts covered OU25 only:
0 of 4,891 settled BTTS rows reached any study.

The cost was concentrated exactly where it hurt most. Argentina BTTS carries v9's entire staked
book (+33.95u of new-format's +21.12u) and was the one cell with NO independent Pro read — so
the cross-check whose whole purpose is to disagree with v9 could not look at the most important
cell in the estate.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.importers.current_wowza import from_ledgers


@pytest.fixture(scope="module")
def side() -> pd.DataFrame:
    for table, df in from_ledgers():
        if table != "settlements":
            continue
        s = df[~df["market"].astype(str).str.upper().isin(["OU25"])]
        if len(s):
            return s
    pytest.skip("no side-market settlements available in this checkout")


def test_side_markets_carry_edge_pct(side):
    """Without it every row is dropped by threshold_curves.load()."""
    assert side["edge_pct"].notna().all(), (
        f"{int(side['edge_pct'].isna().sum())} of {len(side)} side rows have no edge_pct — "
        f"those are invisible to every study that filters on it")


def test_the_side_column_matches_the_market(side):
    """BTTS resolves YES/NO. It was hard-coded to OVER, which is not a side that market has."""
    btts = side[side["market"].astype(str).str.upper() == "BTTS"]
    if len(btts):
        assert set(btts["side"].unique()) <= {"YES", "NO"}, \
            f"BTTS rows carry side {sorted(set(btts['side']))}"
    overs = side[side["market"].astype(str).str.upper().isin(["OVER15", "OVER35"])]
    if len(overs):
        assert set(overs["side"].unique()) <= {"OVER"}


def test_the_frame_carries_the_same_columns_as_the_main_market_frame():
    """Two frames feeding one table must agree, or a study sees a column for one market and
    not the other and silently analyses half the data."""
    main = side_frame = None
    for table, df in from_ledgers():
        if table != "settlements":
            continue
        mk = df["market"].astype(str).str.upper()
        if (mk == "OU25").all():
            main = df
        elif not (mk == "OU25").any():
            side_frame = df
    if main is None or side_frame is None:
        pytest.skip("need both frames present")
    missing = (set(main.columns) - set(side_frame.columns)) - {"p_model_over"}
    assert not missing, f"side frame is missing columns the main frame has: {sorted(missing)}"


def test_the_markets_that_actually_matter_are_present(side):
    present = set(side["market"].astype(str).str.upper())
    assert "BTTS" in present, "BTTS missing — it carries the staked book"


def test_pro_research_stages_every_study_it_runs():
    """pick_accuracy ran daily with --write and its output was never staged, so the committed
    file sat at 2026-09-22 while the study ran 15 more times. Same shape as the defect that
    froze v9's per-league gates: a job that runs green and persists nothing."""
    from pathlib import Path
    wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pro_research.yml")
    txt = wf.read_text(encoding="utf-8")
    for mod in ("pick_accuracy", "accuracy_vs_edge"):
        assert f"src.validation.{mod}" in txt, f"{mod} is never invoked"
        assert f"output/{mod}.json" in txt, f"{mod}.json is computed but never staged"
