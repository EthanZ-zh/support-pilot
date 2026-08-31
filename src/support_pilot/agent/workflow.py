import operator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from support_pilot.agent.contracts import (
    AgentDecision,
    AgentRequest,
    AgentResponse,
    ConversationStatus,
    TicketDraft,
    TraceEvent,
)
from support_pilot.agent.providers import DecisionProvider
from support_pilot.application.contracts import (
    EntitlementInput,
    IncidentInput,
    QuotaInput,
    TicketInput,
)
from support_pilot.application.services import SupportService
from support_pilot.domain.errors import AuthorizationError
from support_pilot.domain.safety import (
    has_prompt_injection_pattern,
    is_high_risk_action_request,
)
from support_pilot.infrastructure.models import UserAccount
from support_pilot.rag.contracts import KnowledgeSearchInput, RetrievalFilters
from support_pilot.rag.providers.base import EmbeddingProvider, RerankerProvider
from support_pilot.rag.retrieval import HybridRetrievalService


class AgentState(TypedDict, total=False):
    request: AgentRequest
    decision: AgentDecision
    risk_level: Literal["R1", "R2", "R3"]
    outcome: str
    message: str
    response_mode: str
    citations: list[dict[str, Any]]
    tool_result: dict[str, Any] | None
    ticket_draft: dict[str, Any] | None
    escalation_reason: str | None
    provider_error: str | None
    model_usage: dict[str, Any]
    preflight_blocked: bool
    resume_intent: str | None
    conversation_ticket_draft: dict[str, Any] | None
    stored_ticket_result: dict[str, Any] | None
    idempotency_key: str | None
    required_fields: list[str]
    trace: Annotated[list[dict[str, Any]], operator.add]


def _event(node: str, status: str, detail: str) -> dict[str, Any]:
    return {"sequence": 1, "node": node, "status": status, "detail": detail}


def _with_sequences(events: list[dict[str, Any]]) -> list[TraceEvent]:
    return [TraceEvent(**(event | {"sequence": index})) for index, event in enumerate(events, 1)]


def build_agent_graph(
    *,
    session: Session,
    actor: UserAccount,
    decision_provider: DecisionProvider,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
) -> Any:
    def preflight_safety(state: AgentState) -> dict[str, Any]:
        message = state["request"].message
        if has_prompt_injection_pattern(message):
            reason = "prompt_injection_pattern_detected"
            escalation_reason = "security_or_privacy"
        elif is_high_risk_action_request(message):
            reason = "deterministic_high_risk_action_detected"
            escalation_reason = "high_risk"
        else:
            return {
                "preflight_blocked": False,
                "trace": [_event("preflight_safety", "succeeded", "input_allowed")],
            }
        return {
            "preflight_blocked": True,
            "decision": AgentDecision(
                intent="high_risk",
                confidence=1.0,
                reason=reason,
            ),
            "risk_level": "R3",
            "escalation_reason": escalation_reason,
            "model_usage": {},
            "trace": [_event("preflight_safety", "denied", reason)],
        }

    def after_preflight(state: AgentState) -> str:
        if state.get("preflight_blocked"):
            return "high_risk"
        confirmation = state["request"].confirmation
        if confirmation == "confirm_ticket":
            return "confirm_ticket"
        if confirmation == "cancel_ticket":
            return "cancel_ticket"
        if state.get("resume_intent"):
            return "resume_decision"
        return "classify"

    def resume_decision(state: AgentState) -> dict[str, Any]:
        intent = state["resume_intent"]
        return {
            "decision": AgentDecision(
                intent=cast(Any, intent),
                confidence=1.0,
                reason="resumed_persisted_pending_intent",
            ),
            "model_usage": {},
            "trace": [_event("resume_decision", "succeeded", "pending_intent_restored")],
        }

    def classify(state: AgentState) -> dict[str, Any]:
        try:
            decision = decision_provider.decide(state["request"])
            return {
                "decision": decision,
                "model_usage": decision_provider.usage.model_dump(mode="json"),
                "trace": [_event("classify", "succeeded", decision.reason)],
            }
        except Exception:
            return {
                "decision": AgentDecision(
                    intent="unknown",
                    confidence=0.0,
                    reason="decision_provider_failed",
                ),
                "provider_error": "decision_provider_failed",
                "model_usage": decision_provider.usage.model_dump(mode="json"),
                "trace": [_event("classify", "degraded", "decision_provider_failed")],
            }

    def apply_risk_gate(state: AgentState) -> dict[str, Any]:
        decision = state["decision"]
        risk = (
            "R3"
            if decision.intent == "high_risk"
            else "R2"
            if decision.intent == "ticket_request"
            else "R1"
        )
        return {
            "risk_level": risk,
            "trace": [_event("risk_gate", "succeeded", f"classified_{risk}")],
        }

    def route(state: AgentState) -> str:
        return state["decision"].intent

    def search_knowledge(state: AgentState) -> dict[str, Any]:
        request = state["request"]
        try:
            result = HybridRetrievalService(
                session,
                embedding_provider=embedding_provider,
                reranker_provider=reranker_provider,
            ).search(
                KnowledgeSearchInput(
                    query=request.message,
                    filters=RetrievalFilters(
                        product_version=request.context.product_version,
                        plan_code=request.context.plan_code,
                    ),
                )
            )
        except Exception:
            return _escalation(
                "tool_failure",
                "知识检索暂时失败，已转入人工处理。",
                "knowledge_search_failed",
            )
        if not result.decision.answerable:
            return _escalation(
                "low_answerability",
                "当前证据不足，不能可靠作答，建议转人工处理。",
                result.decision.reason,
            )
        if has_prompt_injection_pattern(result.hits[0].content):
            return _escalation(
                "security_or_privacy",
                "检索证据包含不可信指令，已停止自动回答并转人工复核。",
                "knowledge_prompt_injection_detected",
            )
        citations = [hit.citation.model_dump(mode="json") for hit in result.hits[:3]]
        answer = result.hits[0].content
        return {
            "outcome": "answered",
            "message": answer,
            "response_mode": "extractive",
            "citations": citations,
            "tool_result": {
                "tool": "knowledge.search",
                "answerability_reason": result.decision.reason,
                "evidence_count": result.decision.evidence_count,
            },
            "trace": [_event("knowledge_search", "succeeded", "answerable_evidence_found")],
        }

    def execute_business_tool(state: AgentState) -> dict[str, Any]:
        request = state["request"]
        intent = state["decision"].intent
        tenant_id = request.tenant_id or actor.tenant_id
        missing = _missing_business_fields(request, intent, tenant_id)
        if missing:
            return {
                "outcome": "needs_clarification",
                "message": f"继续查询前还需要：{', '.join(missing)}。",
                "response_mode": "deterministic",
                "required_fields": missing,
                "escalation_reason": None,
                "trace": [_event("business_tool", "degraded", "missing_required_arguments")],
            }
        try:
            support_input = _support_input(request, intent, cast(Any, tenant_id))
            result = SupportService(session).process(
                support_input,
                actor=actor,
                idempotency_key=None,
            )
        except AuthorizationError:
            return {
                "outcome": "refused",
                "message": "当前用户无权访问该租户的数据。",
                "response_mode": "deterministic",
                "escalation_reason": "security_or_privacy",
                "trace": [_event("business_tool", "denied", "tenant_access_denied")],
            }
        except Exception:
            return _escalation(
                "tool_failure",
                "业务查询失败，已转入人工处理。",
                "business_tool_failed",
            )
        return {
            "outcome": "answered",
            "message": "业务数据查询完成。",
            "response_mode": "deterministic",
            "tool_result": result.data,
            "trace": [_event("business_tool", "succeeded", f"{intent}_read_succeeded")],
        }

    def draft_ticket(state: AgentState) -> dict[str, Any]:
        stored_draft = state.get("conversation_ticket_draft")
        if stored_draft is not None:
            draft = TicketDraft.model_validate(stored_draft)
            detail = "existing_ticket_draft_restored"
        else:
            message = state["request"].message
            draft = TicketDraft(
                summary=message[:120],
                description=message,
            )
            detail = "write_not_executed_without_confirmation"
        return {
            "outcome": "needs_confirmation",
            "message": "已生成工单草稿；确认后才会创建工单。",
            "response_mode": "deterministic",
            "ticket_draft": draft.model_dump(mode="json"),
            "escalation_reason": "user_requested",
            "trace": [_event("ticket_draft", "succeeded", detail)],
        }

    def confirm_ticket(state: AgentState) -> dict[str, Any]:
        request = state["request"]
        decision = AgentDecision(
            intent="ticket_request",
            confidence=1.0,
            reason="explicit_ticket_confirmation",
        )
        stored_result = state.get("stored_ticket_result")
        if stored_result is not None:
            replayed_result = stored_result | {"replayed": True}
            return {
                "decision": decision,
                "risk_level": "R2",
                "outcome": "escalated",
                "message": "工单已经创建，本次返回原工单结果。",
                "response_mode": "deterministic",
                "tool_result": replayed_result,
                "model_usage": {},
                "escalation_reason": "user_requested",
                "trace": [_event("ticket_confirm", "succeeded", "conversation_replay")],
            }
        stored_draft = state.get("conversation_ticket_draft")
        if stored_draft is None:
            return {
                "decision": decision,
                "risk_level": "R2",
                "outcome": "needs_clarification",
                "message": "当前会话没有待确认的工单草稿，请先提出创建工单请求。",
                "response_mode": "deterministic",
                "model_usage": {},
                "trace": [_event("ticket_confirm", "degraded", "ticket_draft_not_found")],
            }
        tenant_id = request.tenant_id or actor.tenant_id
        if tenant_id is None:
            return {
                "decision": decision,
                "risk_level": "R2",
                "outcome": "needs_clarification",
                "message": "创建工单前还需要：tenant_id。",
                "response_mode": "deterministic",
                "required_fields": ["tenant_id"],
                "model_usage": {},
                "trace": [_event("ticket_confirm", "degraded", "tenant_id_required")],
            }
        draft = TicketDraft.model_validate(stored_draft)
        support_request = TicketInput(
            session_id=request.session_id,
            intent="ticket_request",
            tenant_id=tenant_id,
            message=request.message,
            summary=draft.summary,
            description=draft.description,
            category=draft.category,
            severity=draft.severity,
            escalation_reason=draft.escalation_reason,
            diagnostic_context={"agent_session_id": str(request.session_id)},
        )
        result = SupportService(session).process(
            support_request,
            actor=actor,
            idempotency_key=f"agent-{request.session_id}",
        )
        return {
            "decision": decision,
            "risk_level": "R2",
            "outcome": "escalated",
            "message": "已按确认创建工单。",
            "response_mode": "deterministic",
            "tool_result": result.data,
            "model_usage": {},
            "escalation_reason": "user_requested",
            "trace": [_event("ticket_confirm", "succeeded", "ticket_created_idempotently")],
        }

    def cancel_ticket(state: AgentState) -> dict[str, Any]:
        _ = state["request"]
        return {
            "decision": AgentDecision(
                intent="ticket_request",
                confidence=1.0,
                reason="explicit_ticket_cancellation",
            ),
            "risk_level": "R2",
            "outcome": "cancelled",
            "message": "已取消待处理的工单草稿，没有创建工单。",
            "response_mode": "deterministic",
            "model_usage": {},
            "trace": [_event("ticket_cancel", "succeeded", "ticket_write_cancelled")],
        }

    def refuse_high_risk(state: AgentState) -> dict[str, Any]:
        reason = state.get("escalation_reason") or "high_risk"
        return {
            "outcome": "refused",
            "message": "高风险动作不允许自动执行，需要人工审批。",
            "response_mode": "none",
            "escalation_reason": reason,
            "trace": [_event("high_risk_gate", "denied", "no_high_risk_tool_executed")],
        }

    def escalate_unknown(state: AgentState) -> dict[str, Any]:
        reason = "tool_failure" if state.get("provider_error") else "unknown"
        return _escalation(reason, "暂时无法可靠识别请求，建议转人工处理。", reason)

    builder = StateGraph(AgentState)
    builder.add_node("preflight_safety", preflight_safety)
    builder.add_node("classify", classify)
    builder.add_node("resume_decision", resume_decision)
    builder.add_node("risk_gate", apply_risk_gate)
    builder.add_node("knowledge", search_knowledge)
    builder.add_node("business_tool", execute_business_tool)
    builder.add_node("ticket_request", draft_ticket)
    builder.add_node("confirm_ticket", confirm_ticket)
    builder.add_node("cancel_ticket", cancel_ticket)
    builder.add_node("high_risk", refuse_high_risk)
    builder.add_node("unknown", escalate_unknown)
    builder.add_edge(START, "preflight_safety")
    builder.add_conditional_edges(
        "preflight_safety",
        after_preflight,
        {
            "classify": "classify",
            "resume_decision": "resume_decision",
            "confirm_ticket": "confirm_ticket",
            "cancel_ticket": "cancel_ticket",
            "high_risk": "high_risk",
        },
    )
    builder.add_edge("classify", "risk_gate")
    builder.add_edge("resume_decision", "risk_gate")
    builder.add_conditional_edges(
        "risk_gate",
        route,
        {
            "knowledge": "knowledge",
            "entitlement": "business_tool",
            "quota": "business_tool",
            "incident": "business_tool",
            "ticket_request": "ticket_request",
            "high_risk": "high_risk",
            "unknown": "unknown",
        },
    )
    for node in (
        "knowledge",
        "business_tool",
        "ticket_request",
        "confirm_ticket",
        "cancel_ticket",
        "high_risk",
        "unknown",
    ):
        builder.add_edge(node, END)
    return builder.compile()


def response_from_state(*, request_id: Any, trace_id: str, state: AgentState) -> AgentResponse:
    decision = state["decision"]
    return AgentResponse(
        request_id=request_id,
        session_id=state["request"].session_id,
        trace_id=trace_id,
        outcome=cast(Any, state["outcome"]),
        intent=decision.intent,
        risk_level=state["risk_level"],
        message=state["message"],
        response_mode=cast(Any, state.get("response_mode", "none")),
        citations=state.get("citations", []),
        tool_result=state.get("tool_result"),
        ticket_draft=state.get("ticket_draft"),
        required_fields=state.get("required_fields", []),
        escalation_reason=state.get("escalation_reason"),
        conversation_status=_conversation_status(cast(Any, state["outcome"])),
        model_usage=state.get("model_usage", {}),
        trace=_with_sequences(state.get("trace", [])),
    )


def _conversation_status(outcome: str) -> ConversationStatus:
    if outcome == "needs_clarification":
        return "awaiting_clarification"
    if outcome == "needs_confirmation":
        return "awaiting_confirmation"
    if outcome == "cancelled":
        return "cancelled"
    return "completed"


def _missing_business_fields(
    request: AgentRequest,
    intent: str,
    tenant_id: Any,
) -> list[str]:
    fields: dict[str, tuple[str, ...]] = {
        "entitlement": ("feature_code",),
        "quota": ("metric_code",),
        "incident": ("component_code", "region", "occurred_at"),
    }
    missing = [name for name in fields[intent] if getattr(request.context, name) is None]
    if intent in {"entitlement", "quota"} and tenant_id is None:
        missing.insert(0, "tenant_id")
    return missing


def _support_input(request: AgentRequest, intent: str, tenant_id: Any) -> Any:
    context = request.context
    common = {"session_id": request.session_id, "message": request.message}
    if intent == "entitlement":
        return EntitlementInput(
            **common,
            intent="entitlement",
            tenant_id=tenant_id,
            feature_code=cast(str, context.feature_code),
        )
    if intent == "quota":
        return QuotaInput(
            **common,
            intent="quota",
            tenant_id=tenant_id,
            metric_code=cast(str, context.metric_code),
        )
    return IncidentInput(
        **common,
        intent="incident",
        component_code=cast(str, context.component_code),
        region=cast(str, context.region),
        occurred_at=context.occurred_at or datetime.now(UTC),
    )


def _escalation(reason: str, message: str, detail: str) -> dict[str, Any]:
    return {
        "outcome": "escalated",
        "message": message,
        "response_mode": "none",
        "escalation_reason": reason,
        "trace": [_event("fallback", "degraded", detail)],
    }
