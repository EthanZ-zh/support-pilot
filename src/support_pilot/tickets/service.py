from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from support_pilot.domain.enums import AuditOutcome, IdempotencyStatus, TicketStatus, UserRole
from support_pilot.domain.errors import (
    AssignmentConflictError,
    AuthorizationError,
    ConcurrencyConflictError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidTransitionError,
    RequestPreconditionError,
    ResourceNotFoundError,
)
from support_pilot.domain.rules import (
    INTERNAL_ROLES,
    can_access_tenant,
    canonical_request_hash,
    ensure_ticket_transition_allowed,
)
from support_pilot.domain.sanitization import redact_text, redact_value
from support_pilot.infrastructure.models import (
    AgentRun,
    AuditEvent,
    HumanFeedback,
    IdempotencyRecord,
    SupportRequestRecord,
    Ticket,
    TicketTransition,
    UserAccount,
)
from support_pilot.tickets.contracts import (
    ClaimTicketRequest,
    HumanFeedbackRequest,
    HumanFeedbackResponse,
    TicketListResponse,
    TicketResponse,
    TicketTransitionResponse,
    TransitionTicketRequest,
)


@dataclass(frozen=True)
class WriteAttempt:
    scope: str
    key: str
    replayed: bool
    resource_id: UUID | None = None


class TicketWorkflowService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_tickets(
        self,
        *,
        actor: UserAccount,
        tenant_id: UUID | None,
        status: TicketStatus | None,
        limit: int,
        offset: int,
    ) -> TicketListResponse:
        role = UserRole(actor.role)
        if tenant_id is not None and not can_access_tenant(
            role=role,
            actor_tenant_id=actor.tenant_id,
            target_tenant_id=tenant_id,
        ):
            self._deny(
                actor=actor,
                tenant_id=tenant_id,
                action="ticket.list",
                resource_id=str(tenant_id),
                reason_code="tenant_access_denied",
                error=AuthorizationError("actor cannot list tickets for this tenant"),
            )
        filters = []
        if role not in INTERNAL_ROLES:
            if actor.tenant_id is None:
                self._deny(
                    actor=actor,
                    tenant_id=None,
                    action="ticket.list",
                    resource_id="none",
                    reason_code="tenant_context_required",
                    error=AuthorizationError("customer account has no tenant context"),
                )
            filters.append(Ticket.tenant_id == actor.tenant_id)
        elif tenant_id is not None:
            filters.append(Ticket.tenant_id == tenant_id)
        if status is not None:
            filters.append(Ticket.status == status.value)
        statement = (
            select(Ticket)
            .where(*filters)
            .order_by(Ticket.created_at.desc(), Ticket.id)
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count()).select_from(Ticket).where(*filters)
        tickets = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return TicketListResponse(
            items=[self._ticket_response(item) for item in tickets],
            total=total,
        )

    def get_ticket(self, ticket_id: UUID, *, actor: UserAccount) -> TicketResponse:
        ticket = self._load_visible_ticket(ticket_id, actor=actor)
        return self._ticket_response(ticket)

    def claim_ticket(
        self,
        ticket_id: UUID,
        request: ClaimTicketRequest,
        *,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> TicketResponse:
        ticket = self._load_visible_ticket(ticket_id, actor=actor, for_update=True)
        self._require_support_agent(ticket=ticket, actor=actor, action="ticket.claim")
        payload = request.model_dump(mode="json")
        attempt = self._begin_write(
            ticket=ticket,
            actor=actor,
            action="ticket.claim",
            idempotency_key=idempotency_key,
            payload=payload,
        )
        if attempt.replayed:
            return self._commit_replay(ticket=ticket, actor=actor, action="ticket.claim")
        self._require_version(ticket, request.expected_version, actor=actor, action="ticket.claim")
        if ticket.assignee_id is not None:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.claim",
                resource_id=str(ticket.id),
                reason_code="ticket_already_assigned",
                error=AssignmentConflictError("ticket is already assigned"),
            )
        try:
            ensure_ticket_transition_allowed(TicketStatus(ticket.status), TicketStatus.TRIAGED)
        except InvalidTransitionError as error:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.claim",
                resource_id=str(ticket.id),
                reason_code="invalid_ticket_transition",
                error=error,
            )
        previous_status = ticket.status
        ticket.assignee_id = actor.id
        ticket.status = TicketStatus.TRIAGED.value
        ticket.version += 1
        transition = TicketTransition(
            ticket_id=ticket.id,
            from_status=previous_status,
            to_status=ticket.status,
            actor_id=actor.id,
            reason="ticket_claimed",
        )
        self.session.add(transition)
        self.session.flush()
        self._complete_write(
            attempt=attempt,
            ticket=ticket,
            actor=actor,
            action="ticket.claim",
            resource_id=transition.id,
        )
        self.session.commit()
        return self._ticket_response(ticket)

    def transition_ticket(
        self,
        ticket_id: UUID,
        request: TransitionTicketRequest,
        *,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> TicketResponse:
        ticket = self._load_visible_ticket(ticket_id, actor=actor, for_update=True)
        self._require_support_agent(ticket=ticket, actor=actor, action="ticket.transition")
        payload = request.model_dump(mode="json")
        attempt = self._begin_write(
            ticket=ticket,
            actor=actor,
            action="ticket.transition",
            idempotency_key=idempotency_key,
            payload=payload,
        )
        if attempt.replayed:
            return self._commit_replay(ticket=ticket, actor=actor, action="ticket.transition")
        self._require_version(
            ticket,
            request.expected_version,
            actor=actor,
            action="ticket.transition",
        )
        if ticket.assignee_id != actor.id:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.transition",
                resource_id=str(ticket.id),
                reason_code="ticket_not_assigned_to_actor",
                error=AuthorizationError("only the assigned support agent may transition ticket"),
            )
        current = TicketStatus(ticket.status)
        try:
            ensure_ticket_transition_allowed(current, request.to_status)
        except InvalidTransitionError as error:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.transition",
                resource_id=str(ticket.id),
                reason_code="invalid_ticket_transition",
                error=error,
            )
        ticket.status = request.to_status.value
        ticket.version += 1
        transition = TicketTransition(
            ticket_id=ticket.id,
            from_status=current.value,
            to_status=request.to_status.value,
            actor_id=actor.id,
            reason=redact_text(request.reason),
        )
        self.session.add(transition)
        self.session.flush()
        self._complete_write(
            attempt=attempt,
            ticket=ticket,
            actor=actor,
            action="ticket.transition",
            resource_id=transition.id,
        )
        self.session.commit()
        return self._ticket_response(ticket)

    def submit_feedback(
        self,
        ticket_id: UUID,
        request: HumanFeedbackRequest,
        *,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> HumanFeedbackResponse:
        ticket = self._load_visible_ticket(ticket_id, actor=actor, for_update=True)
        if UserRole(actor.role) not in INTERNAL_ROLES:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.feedback",
                resource_id=str(ticket.id),
                reason_code="internal_role_required",
                error=AuthorizationError("only internal reviewers may submit feedback"),
            )
        payload = request.model_dump(mode="json")
        attempt = self._begin_write(
            ticket=ticket,
            actor=actor,
            action="ticket.feedback",
            idempotency_key=idempotency_key,
            payload=payload,
        )
        if attempt.replayed:
            if attempt.resource_id is None:
                raise RuntimeError("succeeded idempotency record has no resource")
            feedback = self.session.get(HumanFeedback, attempt.resource_id)
            if feedback is None:
                raise RuntimeError("idempotency record refers to missing feedback")
            self._audit(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.feedback",
                resource_id=str(feedback.id),
                outcome=AuditOutcome.SUCCESS,
                reason_code="idempotent_replay",
            )
            self.session.commit()
            return self._feedback_response(feedback, replayed=True)
        agent_run = self.session.get(AgentRun, request.agent_run_id)
        source_request = self.session.get(SupportRequestRecord, ticket.source_request_id)
        if (
            agent_run is None
            or source_request is None
            or agent_run.session_id != source_request.session_id
            or agent_run.tenant_id != ticket.tenant_id
        ):
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.feedback",
                resource_id=str(ticket.id),
                reason_code="agent_run_ticket_mismatch",
                error=RequestPreconditionError("agent_run does not belong to this ticket session"),
            )
        existing_feedback = self.session.scalar(
            select(HumanFeedback).where(
                HumanFeedback.ticket_id == ticket.id,
                HumanFeedback.agent_run_id == agent_run.id,
                HumanFeedback.reviewer_id == actor.id,
            )
        )
        if existing_feedback is not None:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.feedback",
                resource_id=str(existing_feedback.id),
                reason_code="feedback_already_submitted",
                error=IdempotencyConflictError(
                    "feedback already exists; replay the original Idempotency-Key"
                ),
            )
        feedback = HumanFeedback(
            ticket_id=ticket.id,
            agent_run_id=agent_run.id,
            reviewer_id=actor.id,
            disposition=request.disposition,
            resolution_category=request.resolution_category.value,
            knowledge_gap=request.knowledge_gap,
            comment=redact_text(request.comment) if request.comment else None,
        )
        self.session.add(feedback)
        self.session.flush()
        self._complete_write(
            attempt=attempt,
            ticket=ticket,
            actor=actor,
            action="ticket.feedback",
            resource_id=feedback.id,
        )
        self.session.commit()
        return self._feedback_response(feedback)

    def _load_visible_ticket(
        self,
        ticket_id: UUID,
        *,
        actor: UserAccount,
        for_update: bool = False,
    ) -> Ticket:
        statement = select(Ticket).where(Ticket.id == ticket_id)
        if for_update:
            statement = statement.with_for_update()
        ticket = self.session.scalar(statement)
        if ticket is None:
            raise ResourceNotFoundError("ticket not found")
        if not can_access_tenant(
            role=UserRole(actor.role),
            actor_tenant_id=actor.tenant_id,
            target_tenant_id=ticket.tenant_id,
        ):
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action="ticket.read" if not for_update else "ticket.write",
                resource_id=str(ticket.id),
                reason_code="tenant_access_denied",
                error=AuthorizationError("actor cannot access this ticket"),
            )
        return ticket

    def _require_support_agent(self, *, ticket: Ticket, actor: UserAccount, action: str) -> None:
        if UserRole(actor.role) is not UserRole.SUPPORT_AGENT:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action=action,
                resource_id=str(ticket.id),
                reason_code="support_agent_role_required",
                error=AuthorizationError("support_agent role is required"),
            )

    def _require_version(
        self,
        ticket: Ticket,
        expected_version: int,
        *,
        actor: UserAccount,
        action: str,
    ) -> None:
        if ticket.version != expected_version:
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action=action,
                resource_id=str(ticket.id),
                reason_code="ticket_version_conflict",
                error=ConcurrencyConflictError(
                    f"ticket version changed; expected {expected_version}, current {ticket.version}"
                ),
            )

    def _begin_write(
        self,
        *,
        ticket: Ticket,
        actor: UserAccount,
        action: str,
        idempotency_key: str | None,
        payload: dict[str, Any],
    ) -> WriteAttempt:
        if idempotency_key is None or not idempotency_key.strip():
            self._deny(
                actor=actor,
                tenant_id=ticket.tenant_id,
                action=action,
                resource_id=str(ticket.id),
                reason_code="idempotency_key_required",
                error=RequestPreconditionError("Idempotency-Key header is required"),
            )
        key = idempotency_key.strip()
        scope = f"ticket:{ticket.id}:{action}"
        request_hash = canonical_request_hash(payload)
        existing = self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                self._deny(
                    actor=actor,
                    tenant_id=ticket.tenant_id,
                    action=action,
                    resource_id=str(ticket.id),
                    reason_code="idempotency_payload_conflict",
                    error=IdempotencyConflictError(
                        "idempotency key was already used with a different payload"
                    ),
                )
            if existing.status != IdempotencyStatus.SUCCEEDED.value:
                self._deny(
                    actor=actor,
                    tenant_id=ticket.tenant_id,
                    action=action,
                    resource_id=str(ticket.id),
                    reason_code="idempotency_request_in_progress",
                    error=IdempotencyInProgressError("idempotent request is still processing"),
                )
            return WriteAttempt(
                scope=scope,
                key=key,
                replayed=True,
                resource_id=existing.resource_id,
            )
        self.session.add(
            IdempotencyRecord(
                scope=scope,
                key=key,
                request_hash=request_hash,
                status=IdempotencyStatus.PROCESSING.value,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        self.session.flush()
        return WriteAttempt(scope=scope, key=key, replayed=False)

    def _complete_write(
        self,
        *,
        attempt: WriteAttempt,
        ticket: Ticket,
        actor: UserAccount,
        action: str,
        resource_id: UUID,
    ) -> None:
        self.session.execute(
            update(IdempotencyRecord)
            .where(
                IdempotencyRecord.scope == attempt.scope,
                IdempotencyRecord.key == attempt.key,
                IdempotencyRecord.status == IdempotencyStatus.PROCESSING.value,
            )
            .values(status=IdempotencyStatus.SUCCEEDED.value, resource_id=resource_id)
        )
        self._audit(
            actor=actor,
            tenant_id=ticket.tenant_id,
            action=action,
            resource_id=str(resource_id),
            outcome=AuditOutcome.SUCCESS,
            reason_code=f"{action.replace('.', '_')}_succeeded",
        )

    def _commit_replay(self, *, ticket: Ticket, actor: UserAccount, action: str) -> TicketResponse:
        self._audit(
            actor=actor,
            tenant_id=ticket.tenant_id,
            action=action,
            resource_id=str(ticket.id),
            outcome=AuditOutcome.SUCCESS,
            reason_code="idempotent_replay",
        )
        self.session.commit()
        return self._ticket_response(ticket, replayed=True)

    def _deny(
        self,
        *,
        actor: UserAccount,
        tenant_id: UUID | None,
        action: str,
        resource_id: str,
        reason_code: str,
        error: Exception,
    ) -> NoReturn:
        self.session.rollback()
        self._audit(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            resource_id=resource_id,
            outcome=AuditOutcome.DENIED,
            reason_code=reason_code,
        )
        self.session.commit()
        raise error

    def _audit(
        self,
        *,
        actor: UserAccount,
        tenant_id: UUID | None,
        action: str,
        resource_id: str,
        outcome: AuditOutcome,
        reason_code: str,
    ) -> None:
        self.session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_type="user",
                actor_id=str(actor.id),
                action=action,
                resource_type="ticket",
                resource_id=resource_id,
                outcome=outcome.value,
                reason_code=reason_code,
                metadata_redacted=redact_value({}),
                trace_id=uuid4().hex,
            )
        )

    def _ticket_response(self, ticket: Ticket, *, replayed: bool = False) -> TicketResponse:
        source_request = self.session.get(SupportRequestRecord, ticket.source_request_id)
        agent_run = None
        if source_request is not None:
            agent_run = self.session.scalar(
                select(AgentRun)
                .where(AgentRun.session_id == source_request.session_id)
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        transitions = list(
            self.session.scalars(
                select(TicketTransition)
                .where(TicketTransition.ticket_id == ticket.id)
                .order_by(TicketTransition.created_at, TicketTransition.id)
            )
        )
        return TicketResponse(
            id=ticket.id,
            public_code=ticket.public_code,
            tenant_id=ticket.tenant_id,
            status=ticket.status,
            severity=ticket.severity,
            category=ticket.category,
            summary=ticket.summary,
            description=ticket.description,
            diagnostic_context=redact_value(ticket.diagnostic_context),
            escalation_reason=ticket.escalation_reason,
            assignee_id=ticket.assignee_id,
            agent_run_id=agent_run.id if agent_run is not None else None,
            version=ticket.version,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            transitions=[
                TicketTransitionResponse(
                    id=transition.id,
                    from_status=transition.from_status,
                    to_status=transition.to_status,
                    actor_id=transition.actor_id,
                    reason=transition.reason,
                    created_at=transition.created_at,
                )
                for transition in transitions
            ],
            replayed=replayed,
        )

    @staticmethod
    def _feedback_response(
        feedback: HumanFeedback, *, replayed: bool = False
    ) -> HumanFeedbackResponse:
        return HumanFeedbackResponse(
            id=feedback.id,
            ticket_id=feedback.ticket_id,
            agent_run_id=feedback.agent_run_id,
            reviewer_id=feedback.reviewer_id,
            disposition=feedback.disposition,
            resolution_category=feedback.resolution_category,
            knowledge_gap=feedback.knowledge_gap,
            comment=feedback.comment,
            created_at=feedback.created_at,
            replayed=replayed,
        )
