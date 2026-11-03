"""Validação opt-in real no Ollama loopback, exclusivamente com fixtures sintéticas."""

import argparse
import asyncio
import hashlib
import json
import platform
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from app.agent.models import AgentLimits, AgentRequest
from app.agent.provider import configured_provider
from app.agent.sessions import ConversationService
from app.config import Settings
from app.database.ingestion import protect_output
from app.evaluation.fixtures import PROJECT, prepare_databases, prepare_policy_pdf
from app.evaluation.models import load_cases
from app.evaluation.runner import ObservedRegistry
from app.evaluation.scoring import latency, score_step
from app.services.policy_service import PolicyService

CORE_CASES = ("CAT02", "PRE02", "POL04", "PED01", "MUL05", "ROB01")
SUPPLEMENTAL_CASES = ("POL07", "PED04")
LOCAL_URL = "http://127.0.0.1:11434/v1"


def local_info(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:11434{path}", timeout=5) as response:
        return json.loads(response.read())


class PhysicalRequests:
    """Observa chamadas reais do SDK; não substitui resposta nem escolhe tools."""

    def __init__(self, provider) -> None:
        self.records = []
        self.create = provider.client.responses.create
        provider.client.responses.create = self.measured

    async def measured(self, **kwargs):
        start = time.perf_counter()
        record = {
            "stage": "structured_finalization" if "text" in kwargs else "automatic_tools",
            "store": kwargs.get("store"),
            "server_state_reference": "previous_response_id" in kwargs or "conversation" in kwargs,
        }
        try:
            response = await self.create(**kwargs)
            record.update(
                status=response.status,
                output_types=[item.type for item in response.output],
                function_calls=[
                    {"name": item.name, "call_id": item.call_id, "arguments": item.arguments}
                    for item in response.output
                    if item.type == "function_call"
                ],
                final_text=response.output_text or None,
                usage=response.usage.model_dump(mode="json") if response.usage else None,
            )
            return response
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            raise
        finally:
            record["latency_ms"] = round((time.perf_counter() - start) * 1000, 4)
            self.records.append(record)


async def validate(settings: Settings, directory: Path) -> dict:
    if (
        settings.llm_provider != "openai_compatible"
        or settings.llm_base_url != LOCAL_URL
        or not settings.llm_configured
    ):
        raise ValueError("configured_loopback_ollama_required")
    models = local_info("/v1/models")
    if settings.llm_model not in {item["id"] for item in models["data"]}:
        raise ValueError("model_must_already_be_installed")
    cases_path = PROJECT / "tests/evaluations/agent_cases.json"
    cases = {case.case_id: case for case in load_cases(cases_path)}
    catalog, orders = prepare_databases(directory)
    policy_pdf = directory / "policies_synthetic.pdf"
    prepare_policy_pdf(policy_pdf)
    policies = PolicyService.from_pdf(policy_pdf)
    provider = configured_provider(settings)
    physical = PhysicalRequests(provider)
    limits = AgentLimits(
        max_rounds=settings.agent_max_rounds,
        max_tool_calls=settings.agent_max_tool_calls,
        timeout_seconds=settings.agent_timeout_seconds,
        tool_timeout_seconds=settings.agent_tool_timeout_seconds,
        request_timeout_seconds=settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
    )
    report = {
        "execution": "real_local_ollama",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "model": settings.llm_model,
        "ollama_version": local_info("/api/version")["version"],
        "base_url": LOCAL_URL,
        "python": platform.python_version(),
        "structured_finalization": settings.llm_structured_finalization,
        "limits": limits.model_dump(),
        "sources": "temporary_synthetic_fixtures_only",
        "suite_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "core_cases": list(CORE_CASES),
        "supplemental_cases": list(SUPPLEMENTAL_CASES),
        "cases": [],
        "reasoning_content_exported": False,
        "credentials_or_session_ids_exported": False,
    }
    try:
        for case_id in (*CORE_CASES, *SUPPLEMENTAL_CASES):
            case = cases[case_id]
            backend = ConversationService.for_demo(
                provider,
                catalog_database=catalog,
                demo_database=orders,
                policies=policies,
                agent_limits=limits,
            )
            registry = ObservedRegistry(backend._agent.tools)
            backend._agent.tools = registry
            handles, sessions = {}, {}
            for actor in {step.actor for step in case.steps}:
                handles[actor] = backend.register_demo_client(
                    customer_id=case.authorization.get(actor)
                )
                sessions[actor] = backend.create_session(handles[actor])
            row = {"case_id": case_id, "category": case.category, "turns": []}
            try:
                for number, step in enumerate(case.steps, 1):
                    registry.records.clear()
                    before = len(physical.records)
                    start = time.perf_counter()
                    result = await backend.chat(
                        handles[step.actor],
                        sessions[step.actor],
                        AgentRequest(message=step.question),
                    )
                    elapsed = (time.perf_counter() - start) * 1000
                    records = list(registry.records)
                    checks = score_step(step, result, records)
                    row["turns"].append(
                        {
                            "step": number,
                            "actor": step.actor,
                            "question": step.question,
                            "response": result.model_dump(mode="json"),
                            "latency_ms": round(elapsed, 4),
                            "physical_requests": physical.records[before:],
                            "tools": [
                                {key: item[key] for key in ("name", "arguments", "payload")}
                                for item in records
                            ],
                            "checks": checks,
                        }
                    )
                    print(
                        json.dumps(
                            {
                                "case": case_id,
                                "step": number,
                                "status": result.status,
                                "task_success": checks["task_success"],
                                "tools": [trace.name for trace in result.tools],
                                "latency_ms": round(elapsed, 2),
                            }
                        ),
                        flush=True,
                    )
            finally:
                for handle in handles.values():
                    backend.revoke_client(handle)
            row["success"] = all(turn["checks"]["task_success"] for turn in row["turns"])
            report["cases"].append(row)
        core = [row for row in report["cases"] if row["case_id"] in CORE_CASES]
        turns = [turn for row in core for turn in row["turns"]]
        usage = [record["usage"] for record in physical.records if record.get("usage")]
        report["summary"] = {
            "core_success": sum(row["success"] for row in core),
            "core_total": len(core),
            "supplemental_success": sum(
                row["success"] for row in report["cases"] if row not in core
            ),
            "turn_latency_core_including_guards": latency([turn["latency_ms"] for turn in turns]),
            "turn_latency_core_with_model": latency(
                [turn["latency_ms"] for turn in turns if turn["physical_requests"]]
            ),
            "physical_requests": len(physical.records),
            "structured_finalizations": sum(
                record["stage"] == "structured_finalization" for record in physical.records
            ),
            "usage_reported_requests": len(usage),
            "known_tokens": {
                key: sum(item[key] for item in usage)
                for key in ("input_tokens", "output_tokens", "total_tokens")
            },
            "billed_cost_usd": None,
            "energy_or_electricity_cost_measured": False,
        }
        report["loaded_models_after"] = local_info("/api/ps")["models"]
        return report
    finally:
        await provider.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=PROJECT / "docs/ollama_validation_results.json"
    )
    args = parser.parse_args()
    try:
        protect_output(args.output, PROJECT / "data/raw", {".json"})
        if args.output.is_symlink() or args.output.exists():
            raise ValueError("use_new_output_path")
        with tempfile.TemporaryDirectory(prefix="emporio-ollama-") as directory:
            report = asyncio.run(validate(Settings(), Path(directory)))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return 0 if all(row["success"] for row in report["cases"]) else 1
    except Exception as exc:
        print(
            json.dumps({"error": "ollama_validation_unavailable", "error_type": type(exc).__name__})
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
