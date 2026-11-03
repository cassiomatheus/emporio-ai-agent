"""Benchmark real opt-in: 40 gabaritos, apenas Ollama loopback e fixtures sintéticas."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from pydantic import TypeAdapter

import app
from app.agent.sessions import ConversationService
from app.config import Settings
from app.database.ingestion import protect_output
from app.evaluation import runner
from app.evaluation.fixtures import prepare_policy_pdf
from app.evaluation.models import EvaluationCase, load_cases


def _write_report_exclusive(path: Path, report: dict) -> None:
    """Arquivo final só aparece completo; nunca sobrescreve uma evidência anterior."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as destination:
            temporary = Path(destination.name)
            json.dump(report, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--finalization", choices=["on", "off"], default="on")
    parser.add_argument("--thinking", choices=["none", "default"], default="none")
    parser.add_argument("--ids")
    parser.add_argument("--rich-trace", action="store_true")
    parser.add_argument(
        "--cases-file", type=Path, help="Gabaritos sintéticos adicionais, congelados."
    )
    parser.add_argument("--context", type=int, choices=[4096, 8192], default=4096)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", a.tag):
        raise ValueError("invalid_profile_tag")
    out = a.output
    protect_output(out, Path(app.__file__).resolve().parents[1] / "data/raw", {".json"})
    if out.exists() or out.is_symlink():
        raise ValueError("use_new_output_path")
    tmp = a.work_dir or Path(tempfile.mkdtemp(prefix="emporio-benchmark-"))
    protect_output(
        tmp / "probe.json", Path(app.__file__).resolve().parents[1] / "data/raw", {".json"}
    )
    tmp.mkdir(parents=True, exist_ok=True)
    checkpoint = tmp / (a.tag + ".checkpoint.json")
    samples = []
    physical = []
    rows = []
    observed_turns = []
    stop = threading.Event()

    def local(path, body=None, timeout=10):
        req = urllib.request.Request(
            "http://127.0.0.1:11434" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())

    def sample():
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, val = line.split(":", 1)
            if key in ["MemAvailable", "SwapFree"]:
                mem[key] = int(val.strip().split()[0])
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        try:
            values = [int(x.strip()) for x in gpu.stdout.strip().split(",")]
        except ValueError:
            values = []
        try:
            models = [
                {k: m.get(k) for k in ["name", "size", "size_vram", "context_length"]}
                for m in local("/api/ps")["models"]
            ]
        except Exception:
            models = []
        return {
            "monotonic": round(time.monotonic(), 3),
            "ram_available_kib": mem.get("MemAvailable"),
            "swap_free_kib": mem.get("SwapFree"),
            "gpu": values,
            "models": models,
        }

    def monitor():
        while not stop.is_set():
            try:
                samples.append(sample())
            except Exception:
                pass
            stop.wait(3)

    async def evaluate_profile():
        s = Settings().model_copy(
            update={
                "llm_model": a.model,
                "llm_structured_finalization": a.finalization == "on",
                "llm_temperature": 0,
                "llm_reasoning_effort": None if a.thinking == "default" else "none",
            }
        )
        if (
            s.llm_provider != "openai_compatible"
            or s.llm_base_url != "http://127.0.0.1:11434/v1"
            or not s.llm_configured
        ):
            raise ValueError("loopback_required")
        if a.model not in {m["id"] for m in local("/v1/models")["data"]}:
            raise ValueError("installed_model_required")
        version = local("/api/version")["version"]
        start = time.perf_counter()
        local(
            "/api/generate",
            {"model": a.model, "prompt": "", "stream": False, "options": {"num_ctx": a.context}},
            timeout=90,
        )
        warmup = round(time.perf_counter() - start, 3)
        samples.append(sample())
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        factory = runner.configured_provider

        def observed_factory(settings):
            provider = factory(settings)
            create = provider.client.responses.create

            async def observed(**kwargs):
                kwargs["temperature"] = 0
                if a.thinking == "none":
                    kwargs["reasoning"] = {"effort": "none"}
                started = time.perf_counter()
                record = {
                    "stage": "finalization" if "text" in kwargs else "native",
                    "store": kwargs.get("store"),
                    "server_state_reference": "previous_response_id" in kwargs
                    or "conversation" in kwargs,
                }
                if a.rich_trace:
                    # Somente outputs das fixtures: nunca exportar prompts, chaves ou raciocínio.
                    record["tool_outputs_visible_to_model"] = [
                        {"call_id": item["call_id"], "output": json.loads(item["output"])}
                        for item in kwargs.get("input", [])
                        if item.get("type") == "function_call_output"
                    ]
                try:
                    response = await create(**kwargs)
                    record.update(
                        status=response.status,
                        usage=response.usage.model_dump(mode="json") if response.usage else None,
                        output_types=[i.type for i in response.output],
                        calls=[
                            {"name": i.name, "arguments": i.arguments, "call_id": i.call_id}
                            for i in response.output
                            if i.type == "function_call"
                        ],
                        final_text=response.output_text or None,
                    )
                    return response
                except BaseException as exc:
                    record["error_type"] = type(exc).__name__
                    raise
                finally:
                    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 4)
                    physical.append(record)

            provider.client.responses.create = observed
            return provider

        runner.configured_provider = observed_factory
        original_case = runner._case
        original_chat = ConversationService.chat

        async def observed_chat(backend, *args, **kwargs):
            before = len(physical)
            answer = await original_chat(backend, *args, **kwargs)
            if a.rich_trace:
                observed_turns.append(
                    {
                        "delivered": answer.model_dump(mode="json"),
                        "requested_tools_and_raw_results": [
                            {k: record[k] for k in ("name", "arguments", "payload")}
                            for record in backend._agent.tools.records
                        ],
                        "physical_requests": physical[before:],
                    }
                )
            return answer

        ConversationService.chat = observed_chat

        async def measured_case(case, *args, **kwargs):
            before = len(physical)
            before_turns = len(observed_turns)
            row = await original_case(case, *args, **kwargs)
            row["physical_requests"] = physical[before:]
            if a.rich_trace:
                row["frozen_answer_key"] = case.model_dump(mode="json")
                for turn, trace, expected in zip(
                    row["turns"], observed_turns[before_turns:], case.steps, strict=True
                ):
                    turn["input"] = expected.question
                    turn["audit"] = trace
            rows.append(row)
            checkpoint.write_text(
                json.dumps(
                    {"tag": a.tag, "completed_cases": len(rows), "cases": rows},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            print(
                json.dumps(
                    {
                        "tag": a.tag,
                        "case": case.case_id,
                        "completed": len(rows),
                        "task_success": all(t["checks"]["task_success"] for t in row["turns"]),
                        "errors": sorted({e for t in row["turns"] for e in t["checks"]["errors"]}),
                        "physical_requests": len(row["physical_requests"]),
                    }
                ),
                flush=True,
            )
            return row

        runner._case = measured_case
        cases_file = a.cases_file or (
            Path(app.__file__).resolve().parents[1] / "tests/evaluations/agent_cases.json"
        )
        cases = (
            TypeAdapter(list[EvaluationCase]).validate_json(cases_file.read_bytes())
            if a.cases_file
            else load_cases(cases_file)
        )
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("duplicate_case_id")
        if a.ids:
            selected = set(a.ids.split(","))
            if not selected <= {case.case_id for case in cases}:
                raise ValueError("unknown_case_id")
            cases = [c for c in cases if c.case_id in selected]
        common = tmp / "shared_synthetic.pdf"
        marker = tmp / "synthetic_source.json"
        if common.exists():
            if (
                not marker.is_file()
                or hashlib.sha256(common.read_bytes()).hexdigest()
                != json.loads(marker.read_text())["sha256"]
            ):
                raise ValueError("unregistered_policy_file")
        else:
            prepare_policy_pdf(common)
            marker.write_text(
                json.dumps(
                    {
                        "sha256": hashlib.sha256(common.read_bytes()).hexdigest(),
                        "generator": "app.evaluation.fixtures.prepare_policy_pdf",
                    }
                )
            )
        started = time.perf_counter()
        try:
            report = await runner.run_evaluation(
                cases, tmp / ("fixtures_" + a.tag), real=True, policy_pdf=common, settings=s
            )
        finally:
            stop.set()
            thread.join(timeout=6)
            runner.configured_provider = factory
            runner._case = original_case
            ConversationService.chat = original_chat
        report["policy_source"] = "shared_generated_synthetic_pdf"
        report["experimental_profile"] = {
            "tag": a.tag,
            "temperature": 0,
            "thinking": a.thinking,
            "structured_finalization": a.finalization == "on",
            "requested_context": a.context,
            "warmup_seconds_excluded": warmup,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "ollama_version": version,
            "source_root_label": "frozen_baseline"
            if "baseline_source" in str(app.__file__)
            else "workspace",
            "model": a.model,
            "raw_answer_keys_sha256": hashlib.sha256(cases_file.read_bytes()).hexdigest(),
            "faults_are_existing_harness_injections": True,
            "credentials_or_reasoning_exported": False,
        }
        usages = [p["usage"] for p in physical if p.get("usage")]
        report["physical_metrics"] = {
            "requests": len(physical),
            "finalizations": sum(p["stage"] == "finalization" for p in physical),
            "sdk_time_ms": sum(p["latency_ms"] for p in physical),
            "finalization_time_ms": sum(
                p["latency_ms"] for p in physical if p["stage"] == "finalization"
            ),
            "usage_reported_requests": len(usages),
            "known_tokens": {
                k: sum(u[k] for u in usages)
                for k in ["input_tokens", "output_tokens", "total_tokens"]
            },
            "injected_provider_calls": sum(
                t["injected_provider_calls"] for r in report["cases"] for t in r["turns"]
            ),
            "native_subject_calls": sum(
                t["provider_calls"] for r in report["cases"] for t in r["turns"]
            ),
        }
        report["resource_samples"] = samples
        out.parent.mkdir(parents=True, exist_ok=True)
        _write_report_exclusive(out, report)
        print(
            json.dumps(
                {
                    "completed_tag": a.tag,
                    "cases": report["executed_cases"],
                    "case_success": report["summary"]["case_success"],
                    "physical": report["physical_metrics"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return (
            0
            if all(
                all(t["checks"]["task_success"] for t in row["turns"]) for row in report["cases"]
            )
            else 1
        )

    return asyncio.run(evaluate_profile())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": "benchmark_unavailable", "error_type": type(exc).__name__}))
        raise SystemExit(2) from None
