"""Pro readers against the v9 go-live prediction board (2026-11-19).

The go-live board (v9 main 99b7bfbe1) carries the new engine's tiers QUALIFIED / AVOID, the bar /
threshold columns (threshold_source, tier_reason, cell_status, ...) and the ledger / lineage
columns (fixture_id, model_version, retrain_batch_id, ...). Two Pro failures followed it:

* Pro Collect (run 44541273287) crashed in from_predictions: the fixture_key v2 bookkeeping
  columns were selected twice into feature_snapshots, so `fs[c]` was a DataFrame.
* The v9 direction gate must read QUALIFIED as a tip and AVOID (or a retired tier) as no tip.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# predictions.csv header on v9 main at go-live (99b7bfbe1, 216 columns), verbatim.
GOLIVE_HEADER = """
league date kickoff_utc home_team away_team odds_over25 odds_under25 best_over25 best_under25
odds_over15 odds_over35 odds_btts _oa_event_id _oa_sport_key odds_btts_no btts_books
btts_overround btts_fair_yes home_scored_last5 away_scored_last5 home_conceded_last5
away_conceded_last5 home_over25_last5 away_over25_last5 home_shots_last5 away_shots_last5
home_sot_last5 away_sot_last5 home_corners_pg_roll away_corners_pg_roll home_fouls_pg_roll
away_fouls_pg_roll home_xg_last5 away_xg_last5 home_insidebox_last5 away_insidebox_last5
home_ht_scored_last5 away_ht_scored_last5 home_ht_conceded_last5 away_ht_conceded_last5
home_ht_over05_rate away_ht_over05_rate home_ht_over15_rate away_ht_over15_rate
home_has_ht_history away_has_ht_history home_possession_last5 away_possession_last5
home_blocked_last5 away_blocked_last5 home_season_goals_h home_season_conceded_h home_cs_rate_h
away_season_goals_a away_season_conceded_a away_cs_rate_a home_advantage away_home_adv_factor
league_avg_goals home_attack_str away_attack_str home_defense_str away_defense_str
combined_ht_goals_avg home_ht_attack_str away_ht_attack_str home_ht_defense_str
away_ht_defense_str home_rest_days away_rest_days combined_corners_pg combined_fouls_pg
home_sot_ratio_last5 away_sot_ratio_last5 combined_sot_ratio key_attacker_absent_home
key_attacker_absent_away af_home_season_goals_h af_home_season_conceded_h af_home_cs_rate_h
af_away_season_goals_a af_away_season_conceded_a af_away_cs_rate_a api_implied_btts
api_implied_over35 api_implied_over15 api_implied_draw home_attack_formation
away_attack_formation combined_attack_intent home_forward_count away_forward_count
h2h_over25_rate h2h_avg_goals h2h_home_win_rate h2h_n api_implied_over25 api_overround
season_stage_ratio is_late_season home_coach_tenure_days home_coach_is_caretaker
away_coach_tenure_days away_coach_is_caretaker home_pitch_artificial home_sp_goals_pg
away_sp_goals_pg home_pen_goals_pg away_pen_goals_pg home_fk_goals_pg away_fk_goals_pg
referee_foul_avg implied_prob_over implied_prob_under bookmaker_overround p_over25_poisson_dc
home_table_pos away_table_pos home_gd_pg away_gd_pg home_form_pts away_form_pts home_win_rate_h
away_win_rate_a table_pos_gap p_over25 model_type p_over25_raw p_btts p_over15 p_over35
p_ht_over05 p_ht_over15 ht_lambda_home ht_lambda_away ht_lambda_total ht_p_over05_poisson
ht_p_over15_poisson ht_home_attack ht_home_defence ht_away_attack ht_away_defence ht_league_base
ht_league_over05_base ht_home_n ht_away_n ht_home_over05_ewm ht_away_over05_ewm
ht_home_scored_ewm ht_home_conceded_ewm ht_away_scored_ewm ht_away_conceded_ewm ht_h2h_over05
ht_h2h_n ht_ft_share_home ht_ft_share_away impl_prob_over impl_prob_under edge_over edge_under
kelly_over kelly_under ev_over ev_under both_losing tier_reason threshold_source stake_over
stake_under tier_over tier_under max_odds_blocked min_odds_blocked bet bet_stake best_edge
best_side signal_tier cell_status qualifying_bar bar_mode_over bar_mode_under bar_config_over
bar_config_under bar_verdict_over bar_verdict_under bar_measure_over bar_measure_under
ev_used_over ev_used_under p_used_over p_used_under cell_p_used edge_calibrated no_form_data
first_over_odds first_under_odds over_drift under_drift drift_signal odds_snapshots
drift_shadow_tier oddsapi_event_id fixture_id generated_at git_sha model_sha model_version
retrain_batch_id training_cutoff prediction_role model_version_btts model_version_over15
model_version_over35 model_version_ht_over05 model_version_ht_over15
""".split()


def _golive_board() -> pd.DataFrame:
    """Two rows on the go-live header: one QUALIFIED tip, one AVOID. Values are synthetic."""
    rows = []
    for home, away, tier, bet, src in (("Norwich City", "Cardiff City", "QUALIFIED", "OVER", "LEAGUE"),
                                       ("Southampton", "Derby County", "AVOID", "AVOID",
                                        "NO_LEAGUE_BAR")):
        r = {c: "" for c in GOLIVE_HEADER}
        r.update(league="Championship", date="2026-11-21", home_team=home, away_team=away,
                 kickoff_utc="2026-11-21T15:00:00Z", p_over25="0.55", p_btts="0.52",
                 home_xg_last5="1.4", model_type="xgb", signal_tier=tier, bet=bet,
                 tier_over=tier, tier_under="AVOID", threshold_source=src,
                 tier_reason="" if src == "LEAGUE" else src, fixture_id="123",
                 generated_at="2026-11-19T13:40:00Z", prediction_role="CHAMPION",
                 model_version="mv1")
        rows.append(r)
    d = pd.DataFrame(rows, columns=GOLIVE_HEADER).astype(str)
    return d.replace("", pd.NA)


def test_golive_header_has_no_duplicates():
    assert len(GOLIVE_HEADER) == 216
    assert len(set(GOLIVE_HEADER)) == len(GOLIVE_HEADER)


def test_from_predictions_reads_the_golive_board(monkeypatch):
    from src.data import entities as ent
    from src.importers import current_wowza as cw
    monkeypatch.setattr(cw, "fetch_csv", lambda *a, **k: _golive_board())
    monkeypatch.setattr(cw, "v9_model_version", lambda: {})
    out = dict(cw.from_predictions())

    assert set(out) >= {"fixtures", "model_snapshots", "feature_snapshots", "signals"}
    for name, frame in out.items():
        assert not frame.columns.duplicated().any(), (name, frame.columns[frame.columns.duplicated()])

    fs = out["feature_snapshots"]
    assert len(fs) == 2
    # The v2 key bookkeeping is identity, present exactly once - never a "feature".
    for c in ent.KEY_META:
        assert list(fs.columns).count(c) == 1
    # New board columns are kept as the values v9 wrote, not dropped.
    assert fs["threshold_source"].tolist() == ["LEAGUE", "NO_LEAGUE_BAR"]
    assert fs["home_xg_last5"].notna().all()

    sg = out["signals"]
    assert sg["signal_tier"].tolist() == ["QUALIFIED", "AVOID"]
    assert not sg["quality_flags"].str.contains("TIER_MISSING").any()


def test_v9_gate_reads_qualified_as_tip_and_avoid_as_none(monkeypatch):
    from src.combo import v9_direction as gate
    from src.data import v9_source
    bets = pd.DataFrame({
        "league": ["Championship"] * 4, "date": ["2026-11-21"] * 4,
        "home_team": ["A", "B", "C", "D"], "away_team": ["E", "F", "G", "H"],
        "bet": ["OVER", "UNDER", "OVER", "UNDER"],
        "signal_tier": ["QUALIFIED", "QUALIFIED", "AVOID", "SNIPER"],
    })
    monkeypatch.setattr(v9_source, "fetch_csv", lambda *a, **k: bets)
    d = gate.directions()
    assert d is not None
    assert d["home_team"].tolist() == ["A", "B"]
    assert d["bet"].tolist() == ["OVER", "UNDER"]


def test_v9_gate_without_tier_column_keeps_direction(monkeypatch):
    """A bets.csv without signal_tier still gates on its published direction."""
    from src.combo import v9_direction as gate
    from src.data import v9_source
    bets = pd.DataFrame({"league": ["Championship"], "date": ["2026-11-21"],
                         "home_team": ["A"], "away_team": ["E"], "bet": ["over"]})
    monkeypatch.setattr(v9_source, "fetch_csv", lambda *a, **k: bets)
    d = gate.directions()
    assert d["bet"].tolist() == ["OVER"]
