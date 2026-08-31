import math
from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class QueryMetrics:
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


def calculate_query_metrics(
    retrieved_ids: list[str], relevant_ids: set[str], *, k: int
) -> QueryMetrics:
    top_ids = retrieved_ids[:k]
    if not relevant_ids:
        return QueryMetrics(recall_at_k=0.0, reciprocal_rank=0.0, ndcg_at_k=0.0)
    relevant_retrieved = sum(item in relevant_ids for item in top_ids)
    recall = relevant_retrieved / len(relevant_ids)
    reciprocal_rank = next(
        (1.0 / rank for rank, item in enumerate(retrieved_ids, start=1) if item in relevant_ids),
        0.0,
    )
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, item in enumerate(top_ids, start=1)
        if item in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return QueryMetrics(
        recall_at_k=recall,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=dcg / ideal_dcg if ideal_dcg else 0.0,
    )


def aggregate_metrics(metrics: list[QueryMetrics]) -> dict[str, float]:
    if not metrics:
        return {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0}
    return {
        "recall_at_k": mean(item.recall_at_k for item in metrics),
        "mrr": mean(item.reciprocal_rank for item in metrics),
        "ndcg_at_k": mean(item.ndcg_at_k for item in metrics),
    }


def calculate_binary_metrics(expected: list[bool], predicted: list[bool]) -> dict[str, float | int]:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted labels must have the same length")
    pairs = list(zip(expected, predicted, strict=True))
    true_positive = sum(wanted and actual for wanted, actual in pairs)
    false_positive = sum(not wanted and actual for wanted, actual in pairs)
    false_negative = sum(wanted and not actual for wanted, actual in pairs)
    true_negative = sum(not wanted and not actual for wanted, actual in pairs)
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
    }
