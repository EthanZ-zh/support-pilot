from collections.abc import Iterator
from hashlib import sha256
from typing import Literal, TypeAlias
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.agent.contracts import (
    AgentContext,
    AgentRequest,
    AgentResponse,
    TraceEvent,
)
from support_pilot.agent.providers import DecisionProvider
from support_pilot.agent.workflow import AgentState, build_agent_graph, response_from_state
from support_pilot.domain.enums import UserRole
from support_pilot.domain.errors import (
    AuthorizationError,
    IdempotencyConflictError,
    RequestPreconditionError,
)
from support_pilot.domain.rules import can_access_tenant
from support_pilot.domain.sanitization import redact_text, redact_value
from support_pilot.infrastructure.models import (
    AgentConversation,
    AgentRun,
    AuditEvent,
    UserAccount,
)
from support_pilot.rag.providers.base import EmbeddingProvider, RerankerProvider

AgentStreamPayload: TypeAlias = TraceEvent | AgentResponse
AgentStreamItem: TypeAlias = tuple[Literal["progress", "result"], AgentStreamPayload]


class AgentService:
    def __init__(
        self,
        session: Session,
        *,
        decision_provider: DecisionProvider,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
    ) -> None:
        self.session = session
        self.decision_provider = decision_provider
        self.embedding_provider = embedding_provider
        self.reranker_provider = reranker_provider

    def resolve(
        self,
        request: AgentRequest,
        *,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> AgentResponse:
        response: AgentResponse | None = None
        for event_name, payload in self.resolve_events(
            request,
            actor=actor,
            idempotency_key=idempotency_key,
        ):
            if event_name == "result":
                if not isinstance(payload, AgentResponse):
                    raise RuntimeError("agent stream result has an invalid payload")
                response = payload
        if response is None:
            raise RuntimeError("agent stream completed without a result")
        return response

    def resolve_events(
        self,
        request: AgentRequest,
        *,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> Iterator[AgentStreamItem]:
        conversation = self._get_or_create_conversation(request=request, actor=actor)
        resolved_request = self._merge_pending_context(request, conversation)
        confirmation_key_hash = self._validate_confirmation(
            request=resolved_request,
            conversation=conversation,
            idempotency_key=idempotency_key,
        )
        trace_id = uuid4().hex
        run = AgentRun(
            session_id=resolved_request.session_id,
            user_id=actor.id,
            tenant_id=resolved_request.tenant_id or actor.tenant_id,
            raw_message=redact_text(resolved_request.message),
            status="running",
            provider=self.decision_provider.provider_name,
            model=self.decision_provider.model_name,
            trace_id=trace_id,
            state_json={},
            trace_json=[],
        )
        self.session.add(run)
        self.session.flush()
        graph = build_agent_graph(
            session=self.session,
            actor=actor,
            decision_provider=self.decision_provider,
            embedding_provider=self.embedding_provider,
            reranker_provider=self.reranker_provider,
        )
        initial_state: AgentState = {
            "request": resolved_request,
            "resume_intent": (
                conversation.pending_intent
                if conversation.status in {"awaiting_clarification", "awaiting_confirmation"}
                else None
            ),
            "conversation_ticket_draft": conversation.ticket_draft,
            "stored_ticket_result": conversation.ticket_result,
            "trace": [],
        }
        try:
            emitted_trace_events = 0
            state = initial_state
            for streamed_state in graph.stream(
                initial_state,
                {"recursion_limit": 12},
                stream_mode="values",
            ):
                state = streamed_state
                trace = state.get("trace", [])
                for trace_event in trace[emitted_trace_events:]:
                    yield "progress", trace_event
                emitted_trace_events = len(trace)
        except Exception:
            self._record_unexpected_failure(run=run, trace_id=trace_id)
            raise
        response = response_from_state(request_id=run.id, trace_id=trace_id, state=state)
        self._update_conversation(
            conversation=conversation,
            request=resolved_request,
            response=response,
            confirmation_key_hash=confirmation_key_hash,
        )
        response = response.model_copy(update={"conversation_status": conversation.status})
        self._record_success(run=run, response=response)
        self.session.commit()
        yield "result", response

    def _get_or_create_conversation(
        self,
        *,
        request: AgentRequest,
        actor: UserAccount,
    ) -> AgentConversation:
        conversation = self.session.scalar(
            select(AgentConversation)
            .where(AgentConversation.session_id == request.session_id)
            .with_for_update()
        )
        target_tenant_id = request.tenant_id or actor.tenant_id
        if target_tenant_id is not None and not can_access_tenant(
            role=UserRole(actor.role),
            actor_tenant_id=actor.tenant_id,
            target_tenant_id=target_tenant_id,
        ):
            raise AuthorizationError("actor cannot attach this session to the requested tenant")
        if conversation is None:
            conversation = AgentConversation(
                session_id=request.session_id,
                user_id=actor.id,
                tenant_id=target_tenant_id,
                status="active",
                pending_context={},
                version=1,
            )
            self.session.add(conversation)
            self.session.flush()
            return conversation
        if conversation.user_id != actor.id:
            raise AuthorizationError("agent session belongs to another user")
        if (
            conversation.tenant_id is not None
            and target_tenant_id is not None
            and conversation.tenant_id != target_tenant_id
        ):
            raise AuthorizationError("agent session tenant cannot be changed")
        if conversation.tenant_id is None:
            conversation.tenant_id = target_tenant_id
        return conversation

    @staticmethod
    def _merge_pending_context(
        request: AgentRequest,
        conversation: AgentConversation,
    ) -> AgentRequest:
        stored = conversation.pending_context if conversation.pending_intent is not None else {}
        supplied = request.context.model_dump(mode="json", exclude_none=True)
        merged = AgentContext.model_validate(stored | supplied)
        return request.model_copy(
            update={
                "tenant_id": request.tenant_id or conversation.tenant_id,
                "context": merged,
            }
        )

    @staticmethod
    def _validate_confirmation(
        *,
        request: AgentRequest,
        conversation: AgentConversation,
        idempotency_key: str | None,
    ) -> str | None:
        if request.confirmation != "confirm_ticket":
            return None
        if conversation.ticket_draft is None and conversation.ticket_result is None:
            raise RequestPreconditionError("no pending ticket draft exists for this session")
        if idempotency_key is None or not idempotency_key.strip():
            raise RequestPreconditionError(
                "Idempotency-Key header is required when confirming a ticket"
            )
        key_hash = sha256(idempotency_key.strip().encode("utf-8")).hexdigest()
        if (
            conversation.confirmation_key_hash is not None
            and conversation.confirmation_key_hash != key_hash
        ):
            raise IdempotencyConflictError(
                "this ticket confirmation was already completed with a different key"
            )
        return key_hash

    @staticmethod
    def _update_conversation(
        *,
        conversation: AgentConversation,
        request: AgentRequest,
        response: AgentResponse,
        confirmation_key_hash: str | None,
    ) -> None:
        previous_status = conversation.status
        if response.outcome == "needs_clarification":
            conversation.status = "awaiting_clarification"
            conversation.pending_intent = response.intent
            conversation.pending_context = redact_value(
                request.context.model_dump(mode="json", exclude_none=True)
            )
        elif response.outcome == "needs_confirmation":
            conversation.status = "awaiting_confirmation"
            conversation.pending_intent = "ticket_request"
            conversation.pending_context = {}
            conversation.ticket_draft = (
                redact_value(response.ticket_draft.model_dump(mode="json"))
                if response.ticket_draft is not None
                else conversation.ticket_draft
            )
        elif response.outcome == "cancelled":
            conversation.status = "cancelled"
            conversation.pending_intent = None
            conversation.pending_context = {}
            conversation.ticket_draft = None
        elif response.outcome == "refused" and previous_status in {
            "awaiting_clarification",
            "awaiting_confirmation",
        }:
            pass
        else:
            conversation.status = "completed"
            conversation.pending_intent = None
            conversation.pending_context = {}
        if (
            response.outcome == "escalated"
            and response.tool_result is not None
            and "ticket_id" in response.tool_result
        ):
            conversation.ticket_result = redact_value(response.tool_result)
            conversation.confirmation_key_hash = confirmation_key_hash
        conversation.version += 1

    def _record_unexpected_failure(self, *, run: AgentRun, trace_id: str) -> None:
        run.status = "failed"
        run.state_json = {"error": "unexpected_agent_failure"}
        run.trace_json = []
        self.session.add(
            AuditEvent(
                tenant_id=run.tenant_id,
                actor_type="agent",
                actor_id=self.decision_provider.provider_name,
                action="agent.resolve",
                resource_type="agent_run",
                resource_id=str(run.id),
                outcome="failure",
                reason_code="unexpected_agent_failure",
                metadata_redacted={
                    "provider": self.decision_provider.provider_name,
                    "model": self.decision_provider.model_name,
                },
                trace_id=trace_id,
            )
        )
        self.session.commit()

    def _record_success(self, *, run: AgentRun, response: AgentResponse) -> None:
        run.status = response.outcome
        run.intent = response.intent
        run.risk_level = response.risk_level
        run.state_json = redact_value(
            response.model_dump(
                mode="json",
                exclude={"request_id", "trace_id", "trace"},
            )
        )
        run.trace_json = redact_value([event.model_dump(mode="json") for event in response.trace])
        self.session.add(
            AuditEvent(
                tenant_id=run.tenant_id,
                actor_type="agent",
                actor_id=self.decision_provider.provider_name,
                action="agent.resolve",
                resource_type="agent_run",
                resource_id=str(run.id),
                outcome="denied" if response.outcome == "refused" else "success",
                reason_code=response.escalation_reason or response.outcome,
                metadata_redacted={
                    "intent": response.intent,
                    "risk_level": response.risk_level,
                    "provider": self.decision_provider.provider_name,
                    "model": self.decision_provider.model_name,
                    "conversation_status": response.conversation_status,
                },
                trace_id=run.trace_id,
            )
        )
