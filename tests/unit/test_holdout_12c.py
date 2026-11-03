"""Integridade do holdout pré-definido; não chama modelo nem ajusta seu gabarito."""

import hashlib
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.evaluation.models import EvaluationCase, load_cases


def test_holdout_is_frozen_valid_and_separate_from_the_original_suite():
    project = Path(__file__).resolve().parents[2]
    manifest = json.loads((project / "docs/evaluation_12c/holdout_manifest.json").read_text())
    data = (project / manifest["file"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest["sha256"]
    cases = TypeAdapter(list[EvaluationCase]).validate_json(data)
    original = load_cases(project / "tests/evaluations/agent_cases.json")
    assert 15 <= len(cases) <= 20 and len(cases) == manifest["cases"]
    assert len({case.case_id for case in cases}) == len(cases)
    assert not {case.case_id for case in cases} & {case.case_id for case in original}
    assert sum(len(case.steps) for case in cases) == manifest["turns"]
