from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from support_pilot.application.contracts import (
    EntitlementInput,
    HighRiskInput,
    IncidentInput,
    QuotaInput,
    SupportInput,
    SupportResponse,
    TicketInput,
)
from support_pilot.domain.enums import (
    AuditOutcome,
    IdempotencyStatus,
    Intent,
    RequestStatus,
    ResponseOutcome,
    TicketStatus,
    UserRole,
)
from support_pilot.domain.errors import (
    AuthorizationError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    RequestPreconditionError,
    ResourceNotFoundError,
)
from support_pilot.domain.rules import can_access_tenant, canonical_request_hash, risk_for_intent
from support_pilot.domain.sanitization import redact_text, redact_value
from support_pilot.infrastructure.models import (
    AuditEvent,
    IdempotencyRecord,
    SupportRequestRecord,
    Tenant,
    Ticket,
    UserAccount,
)
from support_pilot.infrastructure.repositories import SupportRepository


class SupportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SupportRepository(session)

    def process(
        self,
        request: SupportInput,
        *,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> SupportResponse:
        intent = Intent(request.intent)
        record = SupportRequestRecord(
            session_id=request.session_id,
            user_id=actor.id,
            tenant_id=getattr(request, "tenant_id", actor.tenant_id),
            raw_message=redact_text(request.message),
            intent=intent.value,
            risk_level=risk_for_intent(intent).value,
            status=RequestStatus.RUNNING.value,
            trace_id=uuid4().hex,
        )
        self.session.add(record)
        self.session.flush()

        if isinstance(request, EntitlementInput):
            return self._query_entitlement(record, request, actor)
        if isinstance(request, QuotaInput):
            return self._query_quota(record, request, actor)
        if isinstance(request, IncidentInput):
            return self._query_incident(record, request, actor)
        if isinstance(request, TicketInput):
            return self._create_ticket(record, request, actor, idempotency_key)
        if isinstance(request, HighRiskInput):
            return self._refuse_high_risk(record, request, actor)
        raise AssertionError("unreachable support intent")

    def _authorize_tenant(
        self,
        *,
        request: SupportRequestRecord,
        actor: UserAccount,
        target_tenant_id: UUID,
    ) -> Tenant:
        tenant = self.repository.get_tenant(target_tenant_id)
        if tenant is None:
            self._fail_and_raise(
                request=request,
                actor=actor,
                tenant_id=target_tenant_id,
                action="tenant.read",
                reason_code="tenant_not_found",
                error=ResourceNotFoundError("tenant not found"),
            )
        if not can_access_tenant(
            role=UserRole(actor.role),
            actor_tenant_id=actor.tenant_id,
            target_tenant_id=target_tenant_id,
        ):
            self._fail_and_raise(
                request=request,
                actor=actor,
                tenant_id=target_tenant_id,
                action="tenant.read",
                reason_code="cross_tenant_access_denied",
                error=AuthorizationError("actor cannot access the requested tenant"),
            )
        return tenant

    def _query_entitlement(
        self,
        record: SupportRequestRecord,
        request: EntitlementInput,
        actor: UserAccount,
    ) -> SupportResponse:
        tenant = self._authorize_tenant(
            request=record, actor=actor, target_tenant_id=request.tenant_id
        )
        entitlement = self.repository.get_entitlement(
            tenant_id=request.tenant_id,
            feature_code=request.feature_code,
            at=datetime.now(UTC),
        )
        data: dict[str, Any] = {
            "tenant_id": str(tenant.id),
            "plan_code": tenant.plan.code,
            "feature_code": request.feature_code,
            "enabled": entitlement.enabled if entitlement is not None else False,
            "source": entitlement.source if entitlement is not None else "no_active_entitlement",
        }
        return self._succeed(
            request=record,
            actor=actor,
            action="entitlement.read",
            resource_type="entitlement",
            resource_id=request.feature_code,
            tenant_id=tenant.id,
            data=data,
        )

    def _query_quota(
        self,
        record: SupportRequestRecord,
        request: QuotaInput,
        actor: UserAccount,
    ) -> SupportResponse:
        tenant = self._authorize_tenant(
            request=record, actor=actor, target_tenant_id=request.tenant_id
        )
        quota = self.repository.get_latest_quota(
            tenant_id=tenant.id, metric_code=request.metric_code
        )
        if quota is None:
            self._fail_and_raise(
                request=record,
                actor=actor,
                tenant_id=tenant.id,
                action="quota.read",
                reason_code="quota_not_found",
                error=ResourceNotFoundError("quota snapshot not found"),
            )
        data = {
            "tenant_id": str(tenant.id),
            "metric_code": quota.metric_code,
            "limit": quota.limit,
            "used": quota.used,
            "remaining": max(quota.limit - quota.used, 0),
            "exceeded": quota.used >= quota.limit,
            "period_start": quota.period_start,
            "period_end": quota.period_end,
            "measured_at": quota.measured_at,
        }
        return self._succeed(
            request=record,
            actor=actor,
            action="quota.read",
            resource_type="quota_snapshot",
            resource_id=str(quota.id),
            tenant_id=tenant.id,
            data=data,
        )

    def _query_incident(
        self,
        record: SupportRequestRecord,
        request: IncidentInput,
        actor: UserAccount,
    ) -> SupportResponse:
        incidents = self.repository.find_incidents(
            component_code=request.component_code,
            region=request.region,
            occurred_at=request.occurred_at,
        )
        data = {
            "match_status": "confirmed_incident" if incidents else "no_matching_incident",
            "notice": (
                "未发现匹配事故；这不代表服务一定正常。"
                if not incidents
                else "发现时间与区域匹配的已记录事故。"
            ),
            "incidents": [
                {
                    "public_code": incident.public_code,
                    "title": incident.title,
                    "severity": incident.severity,
                    "status": incident.status,
                    "regions": incident.regions,
                    "started_at": incident.started_at,
                    "resolved_at": incident.resolved_at,
                    "customer_message": incident.customer_message,
                }
                for incident in incidents
            ],
        }
        return self._succeed(
            request=record,
            actor=actor,
            action="incident.read",
            resource_type="incident",
            resource_id=incidents[0].public_code if incidents else "none",
            tenant_id=actor.tenant_id,
            data=data,
        )

    def _create_ticket(
        self,
        record: SupportRequestRecord,
        request: TicketInput,
        actor: UserAccount,
        idempotency_key: str | None,
    ) -> SupportResponse:
        tenant = self._authorize_tenant(
            request=record, actor=actor, target_tenant_id=request.tenant_id
        )
        if idempotency_key is None or not idempotency_key.strip():
            self._fail_and_raise(
                request=record,
                actor=actor,
                tenant_id=tenant.id,
                action="ticket.create",
                reason_code="idempotency_key_required",
                error=RequestPreconditionError("Idempotency-Key header is required"),
            )
        key = idempotency_key.strip()
        scope = f"tenant:{tenant.id}:ticket.create"
        payload = request.model_dump(mode="json", exclude={"session_id"})
        request_hash = canonical_request_hash(payload)
        inserted_key = self.session.scalar(
            insert(IdempotencyRecord)
            .values(
                scope=scope,
                key=key,
                request_hash=request_hash,
                status=IdempotencyStatus.PROCESSING.value,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            .on_conflict_do_nothing(index_elements=["scope", "key"])
            .returning(IdempotencyRecord.key)
        )
        inserted = inserted_key is not None
        if not inserted:
            existing = self.session.scalar(
                select(IdempotencyRecord)
                .where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key)
                .with_for_update()
            )
            if existing is None:
                raise RuntimeError("idempotency record disappeared during conflict handling")
            if existing.request_hash != request_hash:
                self._fail_and_raise(
                    request=record,
                    actor=actor,
                    tenant_id=tenant.id,
                    action="ticket.create",
                    reason_code="idempotency_payload_conflict",
                    error=IdempotencyConflictError(
                        "the idempotency key was already used with a different payload"
                    ),
                    resource_id=str(existing.resource_id or key),
                )
            if existing.status != IdempotencyStatus.SUCCEEDED.value or existing.resource_id is None:
                self._fail_and_raise(
                    request=record,
                    actor=actor,
                    tenant_id=tenant.id,
                    action="ticket.create",
                    reason_code="idempotency_request_in_progress",
                    error=IdempotencyInProgressError(
                        "a request with this idempotency key is still processing"
                    ),
                    resource_id=key,
                )
            ticket = self.repository.get_ticket(existing.resource_id)
            if ticket is None:
                raise RuntimeError("idempotency record refers to a missing ticket")
            record.status = RequestStatus.ESCALATED.value
            self._audit(
                request=record,
                actor=actor,
                tenant_id=tenant.id,
                action="ticket.create",
                resource_type="ticket",
                resource_id=str(ticket.id),
                outcome=AuditOutcome.SUCCESS,
                reason_code="idempotent_replay",
                metadata={"public_code": ticket.public_code},
            )
            self.session.commit()
            return self._ticket_response(record, ticket, replayed=True)

        ticket = Ticket(
            public_code=f"TKT-{uuid4().hex[:10].upper()}",
            tenant_id=tenant.id,
            source_request_id=record.id,
            idempotency_key=key,
            status=TicketStatus.OPEN.value,
            severity=request.severity.value,
            category=request.category.value,
            summary=redact_text(request.summary),
            description=redact_text(request.description),
            diagnostic_context=redact_value(request.diagnostic_context),
            escalation_reason=request.escalation_reason.value,
            version=1,
        )
        self.session.add(ticket)
        self.session.flush()
        self.session.execute(
            update(IdempotencyRecord)
            .where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key)
            .values(
                status=IdempotencyStatus.SUCCEEDED.value,
                resource_id=ticket.id,
            )
        )
        record.status = RequestStatus.ESCALATED.value
        self._audit(
            request=record,
            actor=actor,
            tenant_id=tenant.id,
            action="ticket.create",
            resource_type="ticket",
            resource_id=str(ticket.id),
            outcome=AuditOutcome.SUCCESS,
            reason_code="ticket_created",
            metadata={"public_code": ticket.public_code},
        )
        self.session.commit()
        return self._ticket_response(record, ticket, replayed=False)

    def _refuse_high_risk(
        self,
        record: SupportRequestRecord,
        request: HighRiskInput,
        actor: UserAccount,
    ) -> SupportResponse:
        if request.tenant_id is not None:
            self._authorize_tenant(request=record, actor=actor, target_tenant_id=request.tenant_id)
        record.status = RequestStatus.REFUSED.value
        self._audit(
            request=record,
            actor=actor,
            tenant_id=request.tenant_id or actor.tenant_id,
            action="high_risk.execute",
            resource_type="high_risk_action",
            resource_id="not_executed",
            outcome=AuditOutcome.DENIED,
            reason_code="high_risk_requires_human_approval",
            metadata={"requested_action": redact_text(request.requested_action)},
        )
        self.session.commit()
        return SupportResponse(
            request_id=record.id,
            trace_id=record.trace_id,
            outcome=ResponseOutcome.REFUSED,
            data={
                "executed": False,
                "reason": "高风险动作不允许自动执行，需要人工审批。",
            },
        )

    def _succeed(
        self,
        *,
        request: SupportRequestRecord,
        actor: UserAccount,
        action: str,
        resource_type: str,
        resource_id: str,
        tenant_id: UUID | None,
        data: dict[str, Any],
    ) -> SupportResponse:
        request.status = RequestStatus.ANSWERED.value
        self._audit(
            request=request,
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=AuditOutcome.SUCCESS,
            reason_code="deterministic_query_succeeded",
            metadata={},
        )
        self.session.commit()
        return SupportResponse(
            request_id=request.id,
            trace_id=request.trace_id,
            outcome=ResponseOutcome.ANSWERED,
            data=data,
        )

    def _fail_and_raise(
        self,
        *,
        request: SupportRequestRecord,
        actor: UserAccount,
        tenant_id: UUID | None,
        action: str,
        reason_code: str,
        error: Exception,
        resource_id: str = "none",
    ) -> NoReturn:
        request.status = (
            RequestStatus.REFUSED.value
            if isinstance(error, AuthorizationError)
            else RequestStatus.FAILED.value
        )
        self._audit(
            request=request,
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            resource_type="request",
            resource_id=resource_id,
            outcome=(
                AuditOutcome.DENIED
                if isinstance(error, (AuthorizationError, IdempotencyConflictError))
                else AuditOutcome.FAILURE
            ),
            reason_code=reason_code,
            metadata={},
        )
        self.session.commit()
        raise error

    def _audit(
        self,
        *,
        request: SupportRequestRecord,
        actor: UserAccount,
        tenant_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: AuditOutcome,
        reason_code: str,
        metadata: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_type="user",
                actor_id=str(actor.id),
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome.value,
                reason_code=reason_code,
                metadata_redacted=redact_value(metadata),
                trace_id=request.trace_id,
            )
        )

    @staticmethod
    def _ticket_response(
        request: SupportRequestRecord, ticket: Ticket, *, replayed: bool
    ) -> SupportResponse:
        return SupportResponse(
            request_id=request.id,
            trace_id=request.trace_id,
            outcome=ResponseOutcome.ESCALATED,
            data={
                "ticket_id": str(ticket.id),
                "public_code": ticket.public_code,
                "status": ticket.status,
                "replayed": replayed,
            },
        )
