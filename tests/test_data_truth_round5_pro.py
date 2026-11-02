"""Data Truth round 5 (Pro, 2026-11-02): round-4 follow-ups. One focused test per item; each failed
on the code at origin/data-truth-100 b06c34ed before its fix."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)


# ── 1. pro_research.yml: ml_learning_health needs v9's real history ──────────────────────────────
def test_pro_research_checks_v9_out_with_full_history():
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pro_research.yml").read_text(encoding="utf-8"))
    steps = [s for job in wf["jobs"].values() for s in job["steps"]]
    v9 = [s for s in steps if (s.get("with") or {}).get("repository") == "NevixAA/wowza-betting"]
    assert len(v9) == 1
    w = v9[0]["with"]
    assert int(w.get("fetch-depth", 1)) == 0                 # depth 1 dates every model "today"
    assert w.get("filter") == "blob:none"                    # history without every old blob
    # the step that dates the models reads exactly this checkout
    mh = [s for s in steps if s.get("id") == "mlhealth"][0]
    assert "--v9 _v9" in mh["run"] and w.get("path") == "_v9"


# ── 2. Bet Builder: a run that builds nothing leaves no stale candidates behind ──────────────────
def test_generate_that_builds_nothing_writes_empty_candidate_file(tmp_path, monkeypatch):
    from src.combo import canonical as cc
    from src.pipelines import bet_builder as bb
    monkeypatch.setattr(bb, "OUT", tmp_path)
    monkeypatch.setattr(bb, "CAND_FILE", tmp_path / "bet_builder_candidates.csv")
    monkeypatch.setattr(bb, "CAND_META_FILE", tmp_path / "bet_builder_candidates_meta.json", raising=False)
    stale = pd.DataFrame({"generated_at": ["2026-11-01T16:01:00Z"], "fixture_key": ["fk_old"],
                          "kickoff_utc": ["2026-11-01T18:00:00Z"], "match": ["A vs B"],
                          "combo_id": ["fk_old|abc"]})
    stale.to_csv(bb.CAND_FILE, index=False)
    monkeypatch.setattr(bb, "generate", lambda days=3, **k: pd.DataFrame())
    monkeypatch.setattr(cc, "import_builder_outputs", lambda *a, **k: {})
    monkeypatch.setattr(sys, "argv", ["bet_builder", "--mode", "generate"])
    assert bb.main() == 0
    after = pd.read_csv(bb.CAND_FILE)
    assert len(after) == 0                                    # the stale row can never be re-sent
    assert list(after.columns) == list(stale.columns)         # readable header, not a 0-byte file
    meta = json.loads((tmp_path / "bet_builder_candidates_meta.json").read_text(encoding="utf-8"))
    assert meta["rows"] == 0 and re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", meta["generated_at"])


# ── 3. naive v9 snapshot_ts: UTC (verified), and a local-time stamp cannot pass as one ───────────
def test_naive_provider_stamp_later_than_import_is_not_an_observation_time():
    from src.data import observation_time as otm
    # 12:00 UTC import. 10:55 naive = UTC capture (kept). 14:00 naive = what Israel local time
    # (UTC+2) would write for a 12:00 UTC capture: in the future, so not an observation time.
    r = otm.provider_observed_at(pd.Series(["2026-11-02T10:55:35", "2026-11-02T14:00:00"]),
                                 "v9_snapshot_ts", now=pd.Timestamp(NOW))
    assert list(r["observed_at"]) == ["2026-11-02T10:55:35Z", None]
    assert list(r["observed_at_source"]) == ["provider:v9_snapshot_ts", "ingest_time"]


# ── 4. v9's first-half-contaminated CLV list in every bets_ledger clv_pct reader ─────────────────
_LIST = pd.DataFrame({"match_date": ["2026-07-16"], "league": ["Brazil Serie A"],
                      "home_team": ["Botafogo"], "away_team": ["Santos"], "side": ["UNDER"]})


def _v9_dir(tmp_path: Path) -> Path:
    out = tmp_path / "v9" / "output"
    (out / "corrections").mkdir(parents=True)
    _LIST.to_csv(out / "corrections" / "clv_first_half_contaminated.csv", index=False)
    base = {"source": "live", "generated_at": "2026-07-09 22:47", "match_date": "2026-07-16",
            "league": "Brazil Serie A", "home_team": "Botafogo", "away_team": "Santos",
            "signal_tier": "SNIPER", "model_type": "new_format", "result": "LOSS", "pnl": -1.0,
            "edge_pct": 5.0}
    pd.DataFrame([{**base, "side": "UNDER", "odds": 1.96, "closing_odds": 1.20, "clv_pct": 63.33},
                  {**base, "side": "OVER", "odds": 1.90, "closing_odds": 1.85, "clv_pct": 2.7}]
                 ).to_csv(out / "bets_ledger.csv", index=False)
    # side ledger: Over 1.5 on the same fixture - must NOT be hit by the O/U 2.5 list
    pd.DataFrame([{**base, "market": "over15", "side": "UNDER", "odds": 1.3, "closing_odds": 1.25,
                   "clv_pct": 4.0, "model_prob": 0.8}]).to_csv(out / "side_bets_ledger.csv", index=False)
    return tmp_path / "v9"


def test_bets_ledger_clv_readers_drop_first_half_contaminated_closes(tmp_path, monkeypatch):
    from src.analytics import core
    from src.data import v9_config
    monkeypatch.setattr(v9_config, "model_type", lambda lg: "new_format")
    d = core.load_raw(_v9_dir(tmp_path))
    ou = d[d["ledger"] == "ou25"].set_index("side")
    assert pd.isna(ou.loc["UNDER", "clv"]) and pd.isna(ou.loc["UNDER", "closing_odds"])
    assert ou.loc["OVER", "clv"] == pytest.approx(0.027)
    assert d.loc[d["ledger"] == "side", "clv"].iloc[0] == pytest.approx(0.04)   # other market kept
    led = pd.read_csv(tmp_path / "v9" / "output" / "bets_ledger.csv")
    assert led["clv_pct"].tolist() == [63.33, 2.7]                               # v9's ledger unchanged


def test_settlement_flag_or_list_quarantines_clv_on_mixed_market_frames():
    from src.data import v9_corrections as v9c
    s = pd.DataFrame({"match_date": ["2026-07-16"] * 3, "league": ["Brazil Serie A"] * 3,
                      "home_team": ["Botafogo", "Botafogo", "X"], "away_team": ["Santos", "Santos", "Y"],
                      "side": ["UNDER", "UNDER", "OVER"], "market": ["OU25", "OU15", "OU25"],
                      "clv_pct": [63.33, 4.0, 9.0],
                      "quality_flags": ["", "", "CLV_FIRST_HALF_CONTAMINATED"]})
    out = v9c.quarantine_first_half_clv(s, listing=_LIST)
    assert out["clv_pct"].isna().tolist() == [True, False, True]
    assert out["clv_quarantine"].tolist() == [v9c.FLAG, "", v9c.FLAG]


#: Files that mention bets_ledger and clv_pct but do not average the ledger's clv_pct.
_NOT_CLV_READERS = {
    "src/contract.py": "schema documentation",
    "src/pro_tests.py": "contract checks on documentation",
    "src/data/v9_corrections.py": "the loader itself",
    "src/importers/current_wowza.py": "flags CLV_FIRST_HALF_CONTAMINATED at import",
    "src/market/clv_schema.py": "marks FIRST_HALF_CLOSE_CONTAMINATED through the loader's mask",
    "src/market/curve.py": "docstring only; computes clv from prices",
    "src/monitoring/weekly_audit.py": "reads bets_ledger for tip grading only, not clv_pct",
}


def test_every_bets_ledger_clv_reader_applies_the_v9_list():
    missing = []
    for p in sorted((ROOT / "src").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        t = p.read_text(encoding="utf-8")
        if re.search(r"(?<!side_)bets_ledger", t) and re.search(r"\bclv_pct\b", t):
            if rel not in _NOT_CLV_READERS and "quarantine_first_half_clv" not in t:
                missing.append(rel)
    assert missing == []


# ── 5. Bet Builder: a rescheduled match is found across dates, then the 48h rule ─────────────────
def _patch_resolver(monkeypatch):
    from src.data import v9_config

    class _TN:
        @staticmethod
        def resolve_result(name, candidates):
            return name if name in candidates else None
    monkeypatch.setattr(v9_config, "canonical_league", lambda lg: lg)
    monkeypatch.setattr(v9_config, "team_names", lambda: _TN)


def _cand(**kw) -> dict:
    base = {"fixture_key": "fk_orig", "league": "L", "match": "A vs B", "match_date": "2026-10-25",
            "kickoff_utc": "2026-10-25T15:00:00Z", "leg1_market": "O25"}
    base.update(kw)
    return base


def _score(day: str, ko: str) -> pd.DataFrame:
    return pd.DataFrame({"fixture_key": ["fk_new"], "league": ["L"], "match_date": [day],
                         "home_team": ["A"], "away_team": ["B"], "home_goals": [3], "away_goals": [1],
                         "kickoff_utc": [ko]})


def test_bet_builder_finds_rescheduled_match_on_another_date(monkeypatch):
    from src.combo import settle as cs
    _patch_resolver(monkeypatch)
    # moved 24h (new date, new fixture_key): settles on the match played
    out = cs.settle(pd.DataFrame([_cand()]), _score("2026-10-26", "2026-10-26T15:00:00+00:00"), pd.DataFrame())
    assert out["combo_result"].iloc[0] == "WON"
    assert out["settle_note"].iloc[0] == "OK:RESOLVER_DAY+1"
    # moved 72h: found, then VOID under the 48h rule
    out = cs.settle(pd.DataFrame([_cand()]), _score("2026-10-28", "2026-10-28T15:00:00+00:00"), pd.DataFrame())
    assert out["combo_result"].iloc[0] == "VOID" and out["settle_note"].iloc[0] == "VOID_RESCHEDULED_GT_48H"
    # found on another day but the combo has no kickoff: the 48h rule cannot run -> waits
    out = cs.settle(pd.DataFrame([_cand(kickoff_utc=None)]),
                    _score("2026-10-26", "2026-10-26T15:00:00+00:00"), pd.DataFrame())
    assert out["combo_result"].iloc[0] == "UNKNOWN" and out["settle_note"].iloc[0] == "RESCHEDULE_KICKOFF_UNKNOWN"
    # beyond +-3 days: not searched
    out = cs.settle(pd.DataFrame([_cand()]), _score("2026-10-29", "2026-10-29T15:00:00+00:00"), pd.DataFrame())
    assert out["settle_note"].iloc[0] == "NO_SCORELINE"
