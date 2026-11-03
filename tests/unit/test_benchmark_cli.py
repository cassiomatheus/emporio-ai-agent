"""Guardas do benchmark real: testes offline não podem iniciar inferência."""

import importlib.util
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "benchmark_cli", PROJECT / "scripts/benchmark_agent.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_report_is_published_complete_and_exclusively(tmp_path):
    import json

    output = tmp_path / "report.json"
    benchmark._write_report_exclusive(output, {"complete": True})
    assert json.loads(output.read_text()) == {"complete": True}
    with pytest.raises(FileExistsError):
        benchmark._write_report_exclusive(output, {"replacement": True})
    assert json.loads(output.read_text()) == {"complete": True}
    assert list(tmp_path.iterdir()) == [output]


def test_serialization_failure_leaves_no_partial_report(tmp_path):
    with pytest.raises(TypeError):
        benchmark._write_report_exclusive(tmp_path / "report.json", {"invalid": object()})
    assert list(tmp_path.iterdir()) == []


def test_benchmark_never_overwrites_existing_evidence(tmp_path, monkeypatch):
    previous = tmp_path / "report.json"
    previous.write_text('"previous evidence"')
    monkeypatch.setattr(
        benchmark.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network")
    )
    with pytest.raises(ValueError, match="use_new_output_path"):
        benchmark.main(["--tag", "test", "--output", str(previous)])
    assert previous.read_text() == '"previous evidence"'


def test_benchmark_rejects_external_inference_before_any_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in list(benchmark.Settings.model_fields):
        monkeypatch.delenv("EMPORIO_" + name.upper(), raising=False)
    monkeypatch.setenv("EMPORIO_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMPORIO_LLM_MODEL", "fixture")
    monkeypatch.setenv("EMPORIO_LLM_API_KEY", "unit-test")
    monkeypatch.setenv("EMPORIO_LLM_BASE_URL", "https://external.invalid/v1")
    monkeypatch.setattr(
        benchmark.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network")
    )
    with pytest.raises(ValueError, match="loopback_required"):
        benchmark.main(
            [
                "--tag",
                "test",
                "--output",
                str(tmp_path / "new.json"),
                "--work-dir",
                str(tmp_path / "work"),
            ]
        )
    assert not (tmp_path / "new.json").exists()
