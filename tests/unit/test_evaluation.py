"""Oráculos independentes: mutações precisam derrubar métricas e denominadores."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.models import AgentResult, ToolTrace
from app.evaluation.models import CATEGORY_COUNTS, Check, EvaluationStep, load_cases
from app.evaluation.runner import _policy_scores, _tokens_and_policy
from app.evaluation.scoring import (
    MISSING,
    arguments_match,
    check_value,
    extract,
    grounded,
    latency,
    rate,
    score_step,
)


def test_dataset_exact_distribution_and_ids():
    cases = load_cases(Path("tests/evaluations/agent_cases.json"))
    assert len(cases) == 40 and len({case.case_id for case in cases}) == 40
    assert sum(len(case.steps) for case in cases) == 46
    assert {
        name: sum(case.category == name for case in cases) for name in CATEGORY_COUNTS
    } == CATEGORY_COUNTS
    assert all(case.answer_key and step.question for case in cases for step in case.steps)


@pytest.mark.parametrize("mutation", ["duplicate", "remove", "category"])
def test_dataset_rejects_invalid_distribution(tmp_path, mutation):
    raw = json.loads(Path("tests/evaluations/agent_cases.json").read_text())
    if mutation == "duplicate":
        raw[1]["case_id"] = raw[0]["case_id"]
    elif mutation == "remove":
        raw.pop()
    else:
        raw[0]["category"] = "orders"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_cases(path)


def test_extract_distinguishes_missing_null_and_empty_results():
    assert extract({"x": None}, "x") is None
    assert extract({"x": None}, "x.y") is MISSING
    assert extract({"items": []}, "items.*.id") == []
    assert extract({"items": [{"id": 1}, {"id": 2}]}, "items.*.id") == [1, 2]
    assert not check_value(Check(path="missing", value=None), {})
    assert check_value(Check(path="x", op="contains_all", value=[1, 2]), {"x": [2, 3, 1]})
    assert check_value(Check(path="x", op="not_contains", value=4), {"x": [2, 3, 1]})


def test_argument_matching_validates_defaults_decimal_and_essential_filters():
    assert arguments_match(
        "search_products", {"max_price": "800", "available_only": True}, {"max_price": "800.00"}
    )
    assert not arguments_match("search_products", {"max_price": "800"}, {})
    assert not arguments_match("get_product_offers", {"product_id": 127}, {"product_id": 102})


def test_grounding_checks_price_stock_and_policy_sources_independently():
    product = {
        "status": "ok",
        "data": {
            "product_id": 102,
            "price_brl": "250.00",
            "stock_quantity": 4,
        },
    }
    valid = "Item (ID 102): R$ 250,00; disponível; estoque registrado: 4."
    assert grounded(valid, [product]) is True
    assert grounded(valid.replace("250,00", "1,00"), [product]) is False
    assert grounded(valid.replace("registrado: 4", "registrado: 99"), [product]) is False
    assert grounded(valid.replace("ID 102", "ID 127"), [product]) is False
    assert grounded(valid, []) is False
    assert grounded("Não consigo confirmar.", []) is None
    policy = {
        "status": "ok",
        "data": {
            "hits": [
                {
                    "metadata": {"section_id": "8.1"},
                    "excerpt": "Garantia legal de 90 dias.",
                }
            ]
        },
    }
    assert grounded("Garantia de 90 dias [seção 8.1].", [policy]) is True
    assert grounded("Garantia de 90 dias [seção 4.2].", [policy]) is False


def sample_step_and_observation():
    step = EvaluationStep.model_validate(
        {
            "question": "Mostre o produto 102",
            "calls": [
                {
                    "name": "get_product_details",
                    "arguments": {"product_id": 102},
                    "checks": [{"path": "data.product_id", "value": 102}],
                }
            ],
            "required": ["ID 102", "250,00"],
            "forbidden": ["aprovado"],
        }
    )
    result = AgentResult(
        status="answered",
        text="Item (ID 102): R$ 250,00; disponível; estoque registrado: 4.",
        rounds=2,
        tools=(ToolTrace(call_id="x", name="get_product_details", status="ok"),),
    )
    records = [
        {
            "name": "get_product_details",
            "arguments": {"product_id": 102},
            "authorized_customer_id": None,
            "payload": {
                "status": "ok",
                "data": {
                    "product_id": 102,
                    "price_brl": "250.00",
                    "stock_quantity": 4,
                },
            },
        }
    ]
    return step, result, records


def test_task_tool_selection_grounding_and_compliance_can_fail_separately():
    step, result, records = sample_step_and_observation()
    good = score_step(step, result, records)
    assert all(good[name] for name in ("task_success", "tool_selection", "grounding", "compliance"))
    wrong_data = copy.deepcopy(records)
    wrong_data[0]["payload"]["data"]["product_id"] = 127
    assert not score_step(step, result, wrong_data)["task_success"]
    wrong_tool = result.model_copy(update={"tools": ()})
    assert not score_step(step, wrong_tool, records)["tool_selection"]
    wrong_money = result.model_copy(update={"text": result.text.replace("250,00", "1,00")})
    assert score_step(step, wrong_money, records)["grounding"] is False
    assert not score_step(
        step, result.model_copy(update={"text": result.text + " aprovado"}), records
    )["compliance"]


def test_failed_tool_output_is_never_a_grounding_source():
    step, result, records = sample_step_and_observation()
    result = result.model_copy(
        update={
            "tools": (
                ToolTrace(
                    call_id="x",
                    name="get_product_details",
                    status="error",
                    error_code="service_unavailable",
                ),
            )
        }
    )
    assert score_step(step, result, records)["grounding"] is False


def test_unauthorized_order_result_fails_compliance_even_if_not_displayed():
    step = EvaluationStep(question="Pedido", no_facts=True)
    result = AgentResult(status="answered", text="Não consigo confirmar.", rounds=1, tools=())
    records = [
        {
            "name": "get_order_status",
            "arguments": {"order_id": 1},
            "authorized_customer_id": None,
            "payload": {"status": "ok", "data": {"order_id": 1}},
        }
    ]
    assert not score_step(step, result, records)["compliance"]


def test_none_does_not_inflate_rates_and_p95_is_nearest_rank():
    assert rate([True, False, None]) == {"passed": 1, "applicable": 2, "rate": 0.5}
    assert rate([])["rate"] is None
    assert latency([])["median_ms"] is None
    values = list(range(1, 21))
    assert latency(values)["median_ms"] == 10.5
    assert latency(values)["p95_ms"] == 19


def test_partial_usage_is_not_reported_as_complete_and_cost_is_unknown():
    turn = {
        "usage": None,
        "policy": {"agent_recall_at_3": None, "reference_recall_at_3": None},
        "provider_latency_ms": [],
    }
    reported = copy.deepcopy(turn)
    reported["usage"] = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    stats = _tokens_and_policy([{"turns": [turn, reported]}])
    assert stats["tokens"]["reported_turns"] == 1
    assert stats["tokens"]["known_usage"]["total_tokens"] == 15
    assert stats["tokens"]["complete_usage"] is None
    assert stats["cost"]["billed_usd"] is None and stats["cost"]["estimated_usd"] is None


def test_invalid_step_fault_is_rejected():
    with pytest.raises(ValidationError):
        EvaluationStep(question="Oi", fault="arbitrary_code")


def test_expected_denial_catches_hidden_cross_customer_payload_too():
    step = EvaluationStep.model_validate(
        {
            "question": "Pedido alheio",
            "calls": [
                {
                    "name": "get_order_status",
                    "arguments": {"order_id": 1},
                    "checks": [{"path": "error.code", "value": "forbidden"}],
                }
            ],
            "no_facts": True,
        }
    )
    result = AgentResult(status="answered", text="Não consigo confirmar.", rounds=1, tools=())
    records = [
        {
            "name": "get_order_status",
            "arguments": {"order_id": 1},
            "authorized_customer_id": 2,
            "payload": {"status": "ok", "data": {"order_id": 1}},
        }
    ]
    metrics = score_step(step, result, records)
    assert metrics["compliance"] is False and "authorization" in metrics["errors"]


def test_recall_uses_all_relevant_sections_and_only_first_three_hits():
    step = EvaluationStep.model_validate(
        {
            "question": "30 vs 90",
            "calls": [
                {
                    "name": "search_store_policies",
                    "arguments": {"query": "garantia"},
                    "checks": [
                        {
                            "path": "data.hits.*.metadata.section_id",
                            "op": "contains_all",
                            "value": ["4.2", "8.1"],
                        }
                    ],
                }
            ],
        }
    )
    payload = {
        "status": "ok",
        "data": {
            "hits": [
                {"metadata": {"section_id": section}} for section in ["4.2", "8.2", "8.3", "8.1"]
            ]
        },
    }
    metrics = _policy_scores(step, [{"payload": payload}], [payload])
    assert metrics["agent_recall_at_3"] == 0.5
    assert metrics["reference_recall_at_3"] == 0.5
