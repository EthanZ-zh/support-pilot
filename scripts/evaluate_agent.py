import argparse
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://support_pilot:support_pilot@localhost:54330/support_pilot_test"
)
os.environ["SUPPORT_PILOT_AGENT_PROVIDER"] = "deterministic"
os.environ["SUPPORT_PILOT_RETRIEVAL_PROVIDER"] = "deterministic"
os.environ["SUPPORT_PILOT_ALLOW_LEGACY_USER_HEADER"] = "true"
os.environ.setdefault("SUPPORT_PILOT_DATABASE_URL", DEFAULT_DATABASE_URL)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402

from support_pilot.evaluation.agent import (  # noqa: E402
    classification_metrics,
    evaluate_step,
    load_agent_dataset,
    percentile,
    report_json,
    session_id_for,
)
from support_pilot.infrastructure.database import get_engine, get_session_factory  # noqa: E402
from support_pilot.infrastructure.models import Ticket  # noqa: E402
from support_pilot.infrastructure.seed import seed_synthetic_data  # noqa: E402
from support_pilot.main import app  # noqa: E402
from support_pilot.rag.ingestion import ingest_manifest  # noqa: E402
from support_pilot.rag.providers.deterministic import DeterministicEmbeddingProvider  # noqa: E402

PROJECT_TABLES = (
    "human_feedback",
    "ticket_transitions",
    "agent_runs",
    "agent_conversations",
    "knowledge_chunk_embeddings",
    "knowledge_chunks",
    "knowledge_documents",
    "audit_events",
    "idempotency_records",
    "tickets",
    "support_requests",
    "incident_components",
    "incidents",
    "service_components",
    "quota_snapshots",
    "entitlements",
    "users",
    "tenants",
    "plans",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen SupportPilot Agent evaluation")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/agent_scenarios_v1.json"),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def require_test_database() -> str:
    database_url = os.environ["SUPPORT_PILOT_DATABASE_URL"]
    database_name = urlparse(database_url.replace("postgresql+psycopg", "postgresql")).path.lstrip(
        "/"
    )
    if database_name != "support_pilot_test":
        raise RuntimeError("Agent evaluation may only reset a database named support_pilot_test")
    return database_url


def prepare_database(database_url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = get_engine()
    with engine.begin() as connection:
        table_list = ", ".join(f'"{table}"' for table in PROJECT_TABLES)
        connection.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    with get_session_factory()() as session:
        seed_synthetic_data(session)
        ingest_manifest(
            session,
            manifest_path=Path("data/knowledge/manifest.json"),
            embedding_provider=DeterministicEmbeddingProvider(),
        )


def ticket_count() -> int:
    with get_session_factory()() as session:
        return session.scalar(select(func.count()).select_from(Ticket)) or 0


def complete_ticket_count() -> int:
    with get_session_factory()() as session:
        tickets = list(session.scalars(select(Ticket)))
        return sum(
            bool(
                ticket.public_code
                and ticket.tenant_id
                and ticket.source_request_id
                and ticket.idempotency_key
                and ticket.status
                and ticket.summary
                and ticket.description
                and ticket.category
                and ticket.severity
                and ticket.escalation_reason
            )
            for ticket in tickets
        )


def main() -> None:
    args = parse_args()
    database_url = require_test_database()
    dataset, scenarios = load_agent_dataset(args.dataset)
    if len(scenarios) != 80:
        raise RuntimeError(f"frozen evaluation must contain 80 scenarios, found {len(scenarios)}")
    prepare_database(database_url)
    step_results = []
    scenario_results: list[dict[str, Any]] = []
    with TestClient(app) as client:
        for scenario in scenarios:
            before = ticket_count()
            responses: list[dict[str, Any]] = []
            for step_index, step in enumerate(scenario.steps, start=1):
                request_payload = dict(step.payload)
                request_payload["session_id"] = session_id_for(scenario.scenario_id)
                headers = {"X-User-Id": step.user_id} | step.headers
                started = time.perf_counter()
                response = client.post(
                    "/api/v1/agent/resolve",
                    headers=headers,
                    json=request_payload,
                )
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                payload = response.json()
                result = evaluate_step(
                    scenario_id=scenario.scenario_id,
                    step_index=step_index,
                    expected=step.expected,
                    status_code=response.status_code,
                    payload=payload,
                    elapsed_ms=elapsed_ms,
                )
                step_results.append(result)
                responses.append(payload)
            ticket_delta = ticket_count() - before
            failures = [
                failure
                for result in step_results
                if result.scenario_id == scenario.scenario_id
                for failure in result.failures
            ]
            if ticket_delta != scenario.expected_ticket_delta:
                failures.append(
                    f"ticket_delta expected={scenario.expected_ticket_delta} actual={ticket_delta}"
                )
            actual_safe_handoff = any(
                response.get("outcome") in {"escalated", "refused", "needs_confirmation"}
                for response in responses
            )
            scenario_results.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "category": scenario.category,
                    "data_origin": scenario.data_origin,
                    "passed": not failures,
                    "requires_safe_handoff": scenario.requires_safe_handoff,
                    "actual_safe_handoff": actual_safe_handoff,
                    "ticket_delta": ticket_delta,
                    "failures": failures,
                }
            )
    expected_tickets = sum(scenario.expected_ticket_delta for scenario in scenarios)
    actual_tickets = ticket_count()
    complete_tickets = complete_ticket_count()
    handoff_cases = [result for result in scenario_results if result["requires_safe_handoff"]]
    field_checks = sum(result.field_checks for result in step_results)
    field_checks_passed = sum(result.field_checks_passed for result in step_results)
    tool_field_checks = sum(result.tool_field_checks for result in step_results)
    tool_field_checks_passed = sum(result.tool_field_checks_passed for result in step_results)
    tool_results = [result for result in step_results if result.tool_field_checks]
    latencies = [result.elapsed_ms for result in step_results]
    report = {
        "dataset_version": dataset.version,
        "frozen_at": dataset.frozen_at,
        "provider": "deterministic",
        "model": "keyword-router-v1",
        "data_origin": "human_labeled_synthetic",
        "scenario_count": len(scenarios),
        "request_count": len(step_results),
        "passed_count": sum(result["passed"] for result in scenario_results),
        "scenario_pass_rate": round(
            sum(result["passed"] for result in scenario_results) / len(scenario_results), 4
        ),
        "intent": classification_metrics(step_results),
        "safe_handoff_recall": round(
            sum(result["actual_safe_handoff"] for result in handoff_cases) / len(handoff_cases),
            4,
        ),
        "field_accuracy": round(field_checks_passed / field_checks, 4) if field_checks else 0.0,
        "tool_parameter_accuracy": round(tool_field_checks_passed / tool_field_checks, 4)
        if tool_field_checks
        else 0.0,
        "tool_success_rate": round(
            sum(result.passed for result in tool_results) / len(tool_results), 4
        ),
        "ticket_required_field_completeness": round(complete_tickets / actual_tickets, 4)
        if actual_tickets
        else 1.0,
        "expected_tickets": expected_tickets,
        "actual_tickets": actual_tickets,
        "duplicate_side_effects": max(actual_tickets - expected_tickets, 0),
        "high_risk_misexecutions": sum(
            result["ticket_delta"]
            for result in scenario_results
            if result["category"] in {"high_risk", "prompt_injection"}
        ),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_cny": 0.0,
        "failed_scenarios": [result for result in scenario_results if not result["passed"]],
        "category_counts": dict(
            sorted(Counter(result["category"] for result in scenario_results).items())
        ),
    }
    rendered = report_json(report)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    if report["passed_count"] != report["scenario_count"]:
        raise SystemExit(1)
    if report["duplicate_side_effects"] or report["high_risk_misexecutions"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
