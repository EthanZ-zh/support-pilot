from pathlib import Path

import pytest

from support_pilot.evaluation.agent import (
    StepExpectation,
    classification_metrics,
    evaluate_step,
    load_agent_dataset,
    nested_value,
)


def test_frozen_agent_dataset_contains_80_unique_scenarios() -> None:
    dataset, scenarios = load_agent_dataset(Path("data/evaluation/agent_scenarios_v1.json"))

    assert dataset.version == "agent-scenarios-v1"
    assert len(scenarios) == 80
    assert len({scenario.scenario_id for scenario in scenarios}) == 80
    assert all(scenario.data_origin == "human_labeled_synthetic" for scenario in scenarios)


def test_step_evaluation_checks_nested_tool_fields_and_trace() -> None:
    result = evaluate_step(
        scenario_id="quota_01",
        step_index=1,
        expected=StepExpectation(
            intent="quota",
            outcome="answered",
            fields={"tool_result.remaining": 2500},
            trace_contains=["business_tool"],
        ),
        status_code=200,
        payload={
            "intent": "quota",
            "outcome": "answered",
            "tool_result": {"remaining": 2500},
            "trace": [{"node": "business_tool"}],
            "citations": [],
        },
        elapsed_ms=1.0,
    )

    assert result.passed is True
    assert result.tool_field_checks == 1
    assert result.tool_field_checks_passed == 1


def test_classification_metrics_report_macro_f1_without_hiding_weak_class() -> None:
    correct = evaluate_step(
        scenario_id="a",
        step_index=1,
        expected=StepExpectation(intent="knowledge"),
        status_code=200,
        payload={"intent": "knowledge", "trace": [], "citations": []},
        elapsed_ms=1.0,
    )
    wrong = evaluate_step(
        scenario_id="b",
        step_index=1,
        expected=StepExpectation(intent="quota"),
        status_code=200,
        payload={"intent": "knowledge", "trace": [], "citations": []},
        elapsed_ms=1.0,
    )

    metrics = classification_metrics([correct, wrong])

    assert metrics["accuracy"] == 0.5
    assert metrics["macro_f1"] == pytest.approx(1 / 3, abs=0.0001)
    assert metrics["per_class"]["quota"]["f1"] == 0.0


def test_nested_value_supports_list_indexes() -> None:
    assert nested_value({"items": [{"code": "INC-1"}]}, "items.0.code") == "INC-1"
    with pytest.raises(KeyError):
        nested_value({"items": []}, "items.0.code")
