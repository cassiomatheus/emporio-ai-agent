"""Publicação de evidências sintéticas sem alterar fontes ligadas ou resultados anteriores."""

import asyncio
import hashlib
import importlib.util
import os
import subprocess
import sys

import pytest

from app.agent.models import ModelTurn

spec = importlib.util.spec_from_file_location("release_examples", "scripts/generate_examples.py")
examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examples)


@pytest.mark.parametrize("name", ["01_catalogo.md", "manifest.json"])
def test_symlink_output_cannot_modify_original(tmp_path, name):
    original = tmp_path / "source.csv"
    original.write_bytes(b"immutable synthetic source")
    destination = tmp_path / "examples"
    destination.mkdir()
    (destination / name).symlink_to(original)
    with pytest.raises(ValueError, match="unsafe_example_output"):
        asyncio.run(examples.generate_examples(destination))
    assert original.read_bytes() == b"immutable synthetic source"
    assert sorted(path.name for path in destination.iterdir()) == [name]


@pytest.mark.parametrize("name", ["01_catalogo.md", "manifest.json"])
def test_hardlinked_outputs_preserve_source_and_have_valid_manifest(tmp_path, name):
    original = tmp_path / "source.csv"
    original.write_bytes(b"immutable synthetic source")
    destination = tmp_path / "examples"
    destination.mkdir()
    os.link(original, destination / name)
    manifest = asyncio.run(examples.generate_examples(destination))
    assert original.read_bytes() == b"immutable synthetic source"
    assert len(manifest["examples"]) == 5 and not manifest["real_provider_called"]
    for item in manifest["examples"]:
        assert (
            hashlib.sha256((destination / item["file"]).read_bytes()).hexdigest() == item["sha256"]
        )
    assert not list(destination.glob(".examples-stage-*"))


def test_late_validation_failure_preserves_all_previous_evidence(tmp_path, monkeypatch):
    destination = tmp_path / "examples"
    destination.mkdir()
    names = [f"{scenario[0]}.md" for scenario in examples.SCENARIOS] + ["manifest.json"]
    for name in names:
        (destination / name).write_bytes(b"previous verified evidence")
    original = examples.ExampleProvider.complete

    async def bad_promotion(self, messages, *args, **kwargs):
        if "Mostre detalhes e oferta" in messages[-1].get("content", ""):
            return ModelTurn(
                final_text='{"intent":"greeting","evidence_call_ids":[],"clarification":null}'
            )
        return await original(self, messages, *args, **kwargs)

    monkeypatch.setattr(examples.ExampleProvider, "complete", bad_promotion)
    with pytest.raises(ValueError, match="promotion_example_invalid"):
        asyncio.run(examples.generate_examples(destination))
    assert all((destination / name).read_bytes() == b"previous verified evidence" for name in names)


@pytest.mark.parametrize("parent", ["project", "external"])
def test_library_function_protects_both_data_directories(tmp_path, monkeypatch, parent):
    project = tmp_path / "repo"
    monkeypatch.setattr(examples, "PROJECT", project)
    target = project / "data" if parent == "project" else project.parent / "data"
    with pytest.raises(ValueError, match="output_in_data_not_allowed"):
        asyncio.run(examples.generate_examples(target))
    assert not target.exists()


def test_validation_cannot_be_disabled_by_python_optimization(tmp_path):
    code = """import asyncio, importlib.util, sys
from pathlib import Path
from app.agent.models import ModelTurn
spec = importlib.util.spec_from_file_location("optimized_examples", "scripts/generate_examples.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
async def bad(*args, **kwargs):
    return ModelTurn(final_text='{"intent":"greeting","evidence_call_ids":[],"clarification":null}')
module.ExampleProvider.complete = bad
try:
    asyncio.run(module.generate_examples(Path(sys.argv[1])))
except ValueError as exc:
    sys.exit(0 if str(exc) == "catalog_example_invalid" else 2)
sys.exit(3)
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", code, str(tmp_path / "examples")],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert not list((tmp_path / "examples").glob("*.md"))
