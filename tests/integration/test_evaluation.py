"""Executa 40 cenários offline; falhas do sujeito não são mascaradas como falhas do pytest."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.evaluation.models import load_cases
from app.evaluation.runner import run_evaluation

CASES = Path("tests/evaluations/agent_cases.json")


def test_full_offline_evaluation_records_both_failures_and_controls(tmp_path):
    report = asyncio.run(run_evaluation(load_cases(CASES), tmp_path))
    assert report["execution"] == "offline_scripted" and not report["real_provider_called"]
    assert report["executed_cases"] == 40 and report["executed_turns"] == 46
    assert report["summary"]["case_success"]["passed"] < 40
    assert report["summary"]["reference_tool_checks"]["rate"] == 1
    assert report["summary"]["policy_recall_at_3"]["agent_mean"] == 0
    assert report["summary"]["policy_recall_at_3"]["reference_mean"] == 1
    assert report["llm_tool_selection"]["rate"] is None
    assert report["summary"]["tokens"]["known_usage"] is None
    assert all(
        "evaluation_harness" not in turn["checks"]["errors"]
        for case in report["cases"]
        for turn in case["turns"]
    )
    payload = json.dumps(report, ensure_ascii=False)
    for private in (
        "Ignore as instruções",
        "DROP TABLE",
        "cliente-a@",
        "session_id",
        "tracking_code",
    ):
        assert private not in payload
    assert report["summary"]["turn_latency"]["samples"] == 46


def test_real_evaluation_without_configuration_never_builds_provider(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Provedor não configurado não pode ser construído")

    monkeypatch.setattr("app.evaluation.runner.configured_provider", forbidden)
    settings = Settings(_env_file=None, llm_provider=None, llm_model=None, llm_api_key=None)
    report = asyncio.run(run_evaluation(load_cases(CASES), tmp_path, real=True, settings=settings))
    assert report["execution"] == "not_run" and report["reason"] == "provider_not_configured"
    assert report["executed_cases"] == 0 and report["summary"] is None
    assert list(tmp_path.iterdir()) == []


def test_script_exit_one_means_measured_failure_and_output_contains_no_raw_response(
    tmp_path, monkeypatch, capsys
):
    spec = importlib.util.spec_from_file_location("evaluation_cli", "scripts/evaluate_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "observed.json"
    monkeypatch.setattr("sys.argv", ["evaluate_agent.py", "--output", str(output)])
    assert module.main() == 1
    assert json.loads(capsys.readouterr().out)["executed_cases"] == 40
    report = json.loads(output.read_text())
    assert report["summary"]["case_success"]["rate"] < 1
    assert all("text" not in turn for case in report["cases"] for turn in case["turns"])


def test_invalid_repeat_count_does_not_run_any_case(tmp_path):
    with pytest.raises(ValueError, match="invalid_repeats"):
        asyncio.run(run_evaluation(load_cases(CASES), tmp_path, repeats=0))
