import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from support_pilot.infrastructure.database import get_session_factory
from support_pilot.rag.contracts import KnowledgeSearchInput, RetrievalFilters
from support_pilot.rag.metrics import (
    aggregate_metrics,
    calculate_binary_metrics,
    calculate_query_metrics,
)
from support_pilot.rag.providers.factory import get_provider_bundle
from support_pilot.rag.retrieval import HybridRetrievalService


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    relevant_sources: list[str] = Field(default_factory=list)
    answerable: bool = True
    product_version: str | None = None
    plan_code: str | None = None

    @model_validator(mode="after")
    def validate_relevant_sources(self) -> "EvaluationCase":
        if self.answerable and not self.relevant_sources:
            raise ValueError("answerable cases require at least one relevant source")
        return self


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate hybrid retrieval")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "local_bge"),
        default="deterministic",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/retrieval_cases.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = TypeAdapter(list[EvaluationCase]).validate_python(
        json.loads(args.dataset.read_text(encoding="utf-8"))
    )
    embedding, reranker = get_provider_bundle(args.provider)
    query_metrics = []
    expected_answerability: list[bool] = []
    predicted_answerability: list[bool] = []
    failures: list[dict[str, Any]] = []
    with get_session_factory()() as session:
        service = HybridRetrievalService(
            session,
            embedding_provider=embedding,
            reranker_provider=reranker,
        )
        for case in cases:
            response = service.search(
                KnowledgeSearchInput(
                    query=case.query,
                    filters=RetrievalFilters(
                        product_version=case.product_version,
                        plan_code=case.plan_code,
                    ),
                    top_k=args.k,
                    candidate_k=20,
                )
            )
            retrieved_sources = list(
                dict.fromkeys(hit.citation.source_uri for hit in response.hits)
            )
            expected_answerability.append(case.answerable)
            predicted_answerability.append(response.decision.answerable)
            if case.relevant_sources:
                metric = calculate_query_metrics(
                    retrieved_sources,
                    set(case.relevant_sources),
                    k=args.k,
                )
                query_metrics.append(metric)
            else:
                metric = None
            if metric is not None and metric.recall_at_k < 1.0:
                failures.append(
                    {
                        "kind": "retrieval",
                        "id": case.id,
                        "query": case.query,
                        "expected": case.relevant_sources,
                        "retrieved": retrieved_sources,
                    }
                )
            if response.decision.answerable != case.answerable:
                failures.append(
                    {
                        "kind": "answerability",
                        "id": case.id,
                        "query": case.query,
                        "expected": case.answerable,
                        "predicted": response.decision.answerable,
                        "reason": response.decision.reason,
                        "top_score": response.decision.top_score,
                    }
                )
    report = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "sample_count": len(cases),
        "retrieval_sample_count": len(query_metrics),
        "k": args.k,
        "data_origin": "human_labeled_synthetic",
        "embedding_provider": embedding.provider_name,
        "embedding_model": embedding.model_name,
        "reranker_provider": reranker.provider_name,
        "reranker_model": reranker.model_name,
        "metrics": aggregate_metrics(query_metrics),
        "answerability": calculate_binary_metrics(expected_answerability, predicted_answerability),
        "failure_count": len(failures),
        "failures": failures,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
