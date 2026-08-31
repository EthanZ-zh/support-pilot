from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class StrictEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepExpectation(StrictEvaluationModel):
    status_code: int = 200
    intent: str | None = None
    outcome: str | None = None
    risk_level: str | None = None
    conversation_status: str | None = None
    required_fields: list[str] | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    trace_contains: list[str] = Field(default_factory=list)
    citations_min: int = 0
    model_calls: int | None = None


class ScenarioStep(StrictEvaluationModel):
    user_id: str
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)
    expected: StepExpectation


class Scenario(StrictEvaluationModel):
    scenario_id: str
    category: str
    data_origin: str = "human_labeled_synthetic"
    requires_safe_handoff: bool = False
    expected_ticket_delta: int = 0
    steps: list[ScenarioStep]


class SuiteTemplate(StrictEvaluationModel):
    id_prefix: str
    category: str
    user_id: str
    messages: list[str]
    payload: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    expected: StepExpectation
    data_origin: str = "human_labeled_synthetic"
    requires_safe_handoff: bool = False
    expected_ticket_delta: int = 0


class AgentEvaluationDataset(StrictEvaluationModel):
    version: str
    frozen_at: str
    description: str
    suites: list[SuiteTemplate] = Field(default_factory=list)
    cases: list[Scenario] = Field(default_factory=list)


@dataclass(frozen=True)
class StepResult:
    scenario_id: str
    step_index: int
    passed: bool
    expected_intent: str | None
    actual_intent: str | None
    expected_outcome: str | None
    actual_outcome: str | None
    field_checks: int
    field_checks_passed: int
    tool_field_checks: int
    tool_field_checks_passed: int
    elapsed_ms: float
    failures: tuple[str, ...]


def load_agent_dataset(path: Path) -> tuple[AgentEvaluationDataset, list[Scenario]]:
    dataset = AgentEvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))
    scenarios = list(dataset.cases)
    for suite in dataset.suites:
        for index, message in enumerate(suite.messages, start=1):
            payload = dict(suite.payload)
            payload["message"] = message
            scenarios.append(
                Scenario(
                    scenario_id=f"{suite.id_prefix}_{index:02d}",
                    category=suite.category,
                    data_origin=suite.data_origin,
                    requires_safe_handoff=suite.requires_safe_handoff,
                    expected_ticket_delta=suite.expected_ticket_delta,
                    steps=[
                        ScenarioStep(
                            user_id=suite.user_id,
                            payload=payload,
                            headers=suite.headers,
                            expected=suite.expected,
                        )
                    ],
                )
            )
    duplicate_ids = [
        key for key, count in Counter(s.scenario_id for s in scenarios).items() if count > 1
    ]
    if duplicate_ids:
        raise ValueError(f"duplicate scenario ids: {duplicate_ids}")
    return dataset, sorted(scenarios, key=lambda scenario: scenario.scenario_id)


def session_id_for(scenario_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"support-pilot-agent-eval:{scenario_id}"))


def nested_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def evaluate_step(
    *,
    scenario_id: str,
    step_index: int,
    expected: StepExpectation,
    status_code: int,
    payload: dict[str, Any],
    elapsed_ms: float,
) -> StepResult:
    failures: list[str] = []
    if status_code != expected.status_code:
        failures.append(f"status_code expected={expected.status_code} actual={status_code}")
    scalar_expectations = {
        "intent": expected.intent,
        "outcome": expected.outcome,
        "risk_level": expected.risk_level,
        "conversation_status": expected.conversation_status,
    }
    for field, expected_value in scalar_expectations.items():
        if expected_value is not None and payload.get(field) != expected_value:
            failures.append(f"{field} expected={expected_value} actual={payload.get(field)}")
    if (
        expected.required_fields is not None
        and payload.get("required_fields") != expected.required_fields
    ):
        failures.append(
            f"required_fields expected={expected.required_fields} "
            f"actual={payload.get('required_fields')}"
        )
    trace_nodes = [event.get("node") for event in payload.get("trace", [])]
    for node in expected.trace_contains:
        if node not in trace_nodes:
            failures.append(f"trace missing node={node}")
    if len(payload.get("citations", [])) < expected.citations_min:
        failures.append(
            f"citations expected>={expected.citations_min} "
            f"actual={len(payload.get('citations', []))}"
        )
    if expected.model_calls is not None:
        actual_calls = payload.get("model_usage", {}).get("model_calls")
        if actual_calls != expected.model_calls:
            failures.append(f"model_calls expected={expected.model_calls} actual={actual_calls}")
    field_checks_passed = 0
    tool_field_checks_passed = 0
    for path, expected_value in expected.fields.items():
        try:
            actual_value = nested_value(payload, path)
        except KeyError:
            failures.append(f"field missing path={path}")
        else:
            if actual_value == expected_value:
                field_checks_passed += 1
                if path.startswith("tool_result."):
                    tool_field_checks_passed += 1
            else:
                failures.append(f"{path} expected={expected_value} actual={actual_value}")
    return StepResult(
        scenario_id=scenario_id,
        step_index=step_index,
        passed=not failures,
        expected_intent=expected.intent,
        actual_intent=payload.get("intent"),
        expected_outcome=expected.outcome,
        actual_outcome=payload.get("outcome"),
        field_checks=len(expected.fields),
        field_checks_passed=field_checks_passed,
        tool_field_checks=sum(path.startswith("tool_result.") for path in expected.fields),
        tool_field_checks_passed=tool_field_checks_passed,
        elapsed_ms=elapsed_ms,
        failures=tuple(failures),
    )


def classification_metrics(results: list[StepResult]) -> dict[str, Any]:
    labeled = [result for result in results if result.expected_intent is not None]
    labels = sorted({str(result.expected_intent) for result in labeled})
    per_class: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    for label in labels:
        true_positive = sum(
            result.expected_intent == label and result.actual_intent == label for result in labeled
        )
        false_positive = sum(
            result.expected_intent != label and result.actual_intent == label for result in labeled
        )
        false_negative = sum(
            result.expected_intent == label and result.actual_intent != label for result in labeled
        )
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1_values.append(f1)
        per_class[label] = {
            "support": sum(result.expected_intent == label for result in labeled),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return {
        "sample_count": len(labeled),
        "accuracy": round(
            sum(result.expected_intent == result.actual_intent for result in labeled)
            / len(labeled),
            4,
        )
        if labeled
        else 0.0,
        "macro_f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else 0.0,
        "per_class": per_class,
    }


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(math.ceil(percentile_value * len(ordered)) - 1, 0)
    return round(ordered[index], 2)


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)


DATASET_ADAPTER = TypeAdapter(AgentEvaluationDataset)
