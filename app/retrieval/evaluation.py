"""Recall de seções relevantes: avaliação local sem LLM-juiz ou respostas geradas."""

from collections import defaultdict
from typing import Annotated, Any

from pydantic import Field, TypeAdapter

from app.retrieval.models import PolicySearch, RetrievalModel
from app.retrieval.retriever import LexicalRetriever


class PolicyCase(RetrievalModel):
    case_id: str
    topic: str
    question: Annotated[str, Field(min_length=1, max_length=500)]
    relevant_sections: tuple[str, ...]
    answer_key: str


CASES_ADAPTER = TypeAdapter(list[PolicyCase])


def recall_at_k(expected: set[str], actual: list[str], k: int = 3) -> float | None:
    return len(expected & set(actual[:k])) / len(expected) if expected else None


def evaluate_retrieval(retriever: LexicalRetriever, cases: list[PolicyCase]) -> dict[str, Any]:
    ids = [case.case_id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate_case_id")
    sections = {section.section_id for section in retriever.document.sections}
    if any(set(case.relevant_sections) - sections for case in cases):
        raise ValueError("unknown_gold_section")
    results = []
    by_topic: dict[str, list[float]] = defaultdict(list)
    negatives = []
    for case in cases:
        response = retriever.search(PolicySearch(query=case.question, top_k=3))
        actual = [hit.metadata.section_id for hit in response.hits]
        recall = recall_at_k(set(case.relevant_sections), actual)
        if recall is not None:
            by_topic[case.topic].append(recall)
        else:
            negatives.append(not actual)
        results.append(
            {
                "case_id": case.case_id,
                "topic": case.topic,
                "relevant_sections": list(case.relevant_sections),
                "retrieved": [
                    {
                        "section_id": hit.metadata.section_id,
                        "pages": list(hit.metadata.pages),
                        "chunk_id": hit.chunk_id,
                    }
                    for hit in response.hits
                ],
                "recall_at_3": recall,
                "abstained": not actual,
            }
        )
    recalls = [item["recall_at_3"] for item in results if item["recall_at_3"] is not None]
    document = retriever.document
    return {
        "retrieval_version": "lexical-v1",
        "top_k": 3,
        "source_name": document.source_name,
        "source_sha256": document.source_sha256,
        "document_version": document.version,
        "pages": len(document.pages),
        "sections": len(document.sections),
        "chunks": len(document.chunks),
        "tables": sum(chunk.kind == "table" for chunk in document.chunks),
        "positive_cases": len(recalls),
        "negative_cases": len(negatives),
        "macro_recall_at_3": sum(recalls) / len(recalls) if recalls else None,
        "hit_rate_at_3": sum(value > 0 for value in recalls) / len(recalls) if recalls else None,
        "negative_abstention_rate": sum(negatives) / len(negatives) if negatives else None,
        "recall_by_topic": {
            key: sum(values) / len(values) for key, values in sorted(by_topic.items())
        },
        "results": results,
    }
