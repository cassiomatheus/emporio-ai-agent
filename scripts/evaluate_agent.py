"""Executa 40 gabaritos sem LLM-juiz. Código 1 significa falhas observadas, não erro do harness."""

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from app.config import Settings
from app.database.ingestion import protect_output
from app.evaluation.fixtures import PROJECT
from app.evaluation.models import load_cases
from app.evaluation.runner import run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Avaliação integrada com gabaritos determinísticos."
    )
    parser.add_argument(
        "--cases", type=Path, default=PROJECT / "tests/evaluations/agent_cases.json"
    )
    parser.add_argument(
        "--policy-pdf", type=Path, help="Manual local opcional; nunca exporta texto."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--real", action="store_true", help="Requer provedor/modelo/credencial explícitos."
    )
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 11))
    args = parser.parse_args()
    filename = (
        "evaluation_real.json"
        if args.real
        else ("evaluation_local_pdf_results.json" if args.policy_pdf else "evaluation_results.json")
    )
    output = args.output or PROJECT / "docs" / filename
    try:
        protect_output(output, PROJECT / "data/raw", {".json"})
        if output.resolve() == args.cases.resolve():
            raise ValueError("cannot_overwrite_cases")
        cases = load_cases(args.cases)
        with tempfile.TemporaryDirectory(prefix="emporio-evaluation-") as directory:
            report = asyncio.run(
                run_evaluation(
                    cases,
                    Path(directory),
                    real=args.real,
                    policy_pdf=args.policy_pdf,
                    settings=Settings(),
                    repeats=args.repeats,
                )
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "execution": report["execution"],
                    "executed_cases": report["executed_cases"],
                    "case_success": report["summary"]["case_success"]
                    if report["summary"]
                    else None,
                },
                ensure_ascii=False,
            )
        )
        if report["execution"] == "not_run":
            return 3
        return 0 if report["summary"]["case_success"]["rate"] == 1 else 1
    except Exception:
        print('{"error":"evaluation_unavailable"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
