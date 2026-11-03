"""Mede Recall@3 e grava apenas metadados/métricas, sem exportar o manual."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pymupdf

from app.retrieval.document_loader import DocumentLoadError, load_policy_document
from app.retrieval.evaluation import CASES_ADAPTER, evaluate_retrieval
from app.retrieval.retriever import LexicalRetriever


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Avaliação lexical local de políticas com Recall@3."
    )
    parser.add_argument("--pdf", type=Path, default=Path("data/raw/políticas_da_loja.pdf"))
    parser.add_argument("--cases", type=Path, default=Path("tests/evaluations/policy_cases.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/retrieval_results.json"))
    args = parser.parse_args()
    try:
        target = args.output.resolve()
        if (
            target.suffix != ".json"
            or target == args.cases.resolve()
            or target.is_relative_to(args.pdf.resolve().parent)
        ):
            raise ValueError("unsafe_output")
        content = args.cases.read_bytes()
        cases = CASES_ADAPTER.validate_json(content)
        retriever = LexicalRetriever(load_policy_document(args.pdf))
        results = evaluate_retrieval(retriever, cases)
        results["cases_sha256"] = hashlib.sha256(content).hexdigest()
        results["pymupdf_version"] = pymupdf.VersionBind
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
        args.output.write_text(output, encoding="utf-8")
        print(output, end="")
        return 0
    except (DocumentLoadError, OSError, ValueError):
        print('{"error":"retrieval_evaluation_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
