"""R2 finding 27: research workflow status classes; infra failure never reads as model failure.

    python -m pytest tests/test_run_status.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.monitoring import run_status as RS  # noqa: E402


def _c(*specs):
    return RS.classify([RS.parse_step(s) for s in specs])["status"]


def test_all_green_is_success():
    assert _c("infra:install=success", "test:t=success", "data:d=success", "model:m=success") == "SUCCESS"


def test_install_failure_is_infra_even_when_later_steps_also_fail():
    assert _c("infra:install=failure", "test:t=skipped", "model:m=failure") == "INFRA_FAILURE"


def test_cancelled_step_is_infra_not_model():
    assert _c("infra:install=success", "model:experiments=cancelled") == "INFRA_FAILURE"


def test_test_failure_beats_data_and_model():
    assert _c("infra:i=success", "test:t=failure", "data:d=failure", "model:m=failure") == "TEST_FAILURE"


def test_data_gate_failure_is_data():
    assert _c("infra:i=success", "test:t=success", "data:leakage=failure", "model:m=skipped") == "DATA_FAILURE"


def test_crashed_experiment_is_model_failure():
    assert _c("infra:i=success", "test:t=success", "data:d=success", "model:m=failure") == "MODEL_FAILURE"


def test_nothing_ran_is_not_success():
    assert _c("model:m=skipped", "data:d=") == "INFRA_FAILURE"


def test_unknown_class_is_rejected():
    with pytest.raises(ValueError):
        RS.parse_step("science:m=failure")


def test_cli_writes_json_and_summary_and_says_not_a_verdict(tmp_path, monkeypatch):
    summ = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    out = tmp_path / "s.json"
    rc = RS.main(["--workflow", "w", "--step", "infra:install=failure", "--out", str(out)])
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1 and rec["status"] == "INFRA_FAILURE" and rec["is_scientific_verdict"] is False
    assert "not a scientific verdict" in summ.read_text(encoding="utf-8")


@pytest.mark.parametrize("wf", ["pro_prediction_lab.yml", "pro_research.yml", "pro_studies.yml"])
def test_research_workflows_install_pytest_and_classify(wf):
    text = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
    yaml.safe_load(text)
    assert "pytest" in text
    assert "src.monitoring.run_status" in text
    assert "requirements.txt" in text or " pytest" in text
