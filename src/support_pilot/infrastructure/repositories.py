from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from support_pilot.infrastructure.models import (
    Entitlement,
    Incident,
    Plan,
    QuotaSnapshot,
    ServiceComponent,
    Tenant,
    Ticket,
    UserAccount,
)


class SupportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user(self, user_id: UUID) -> UserAccount | None:
        return self.session.get(UserAccount, user_id)

    def get_user_by_email(self, email: str) -> UserAccount | None:
        return self.session.scalar(
            select(UserAccount).where(UserAccount.email == email.strip().casefold())
        )

    def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        statement = select(Tenant).options(selectinload(Tenant.plan)).where(Tenant.id == tenant_id)
        return self.session.scalar(statement)

    def get_entitlement(
        self, *, tenant_id: UUID, feature_code: str, at: datetime
    ) -> Entitlement | None:
        statement = (
            select(Entitlement)
            .where(
                Entitlement.tenant_id == tenant_id,
                Entitlement.feature_code == feature_code,
                Entitlement.effective_from <= at,
                or_(Entitlement.effective_to.is_(None), Entitlement.effective_to > at),
            )
            .order_by(Entitlement.effective_from.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def get_latest_quota(self, *, tenant_id: UUID, metric_code: str) -> QuotaSnapshot | None:
        statement = (
            select(QuotaSnapshot)
            .where(
                QuotaSnapshot.tenant_id == tenant_id,
                QuotaSnapshot.metric_code == metric_code,
            )
            .order_by(QuotaSnapshot.measured_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def find_incidents(
        self, *, component_code: str, region: str, occurred_at: datetime
    ) -> list[Incident]:
        statement: Select[tuple[Incident]] = (
            select(Incident)
            .join(Incident.components)
            .where(
                ServiceComponent.code == component_code,
                ServiceComponent.region == region,
                Incident.started_at <= occurred_at,
                or_(Incident.resolved_at.is_(None), Incident.resolved_at >= occurred_at),
            )
            .options(selectinload(Incident.components))
            .order_by(Incident.started_at.desc())
        )
        return list(self.session.scalars(statement).unique())

    def get_plan(self, plan_id: UUID) -> Plan | None:
        return self.session.get(Plan, plan_id)

    def get_ticket(self, ticket_id: UUID) -> Ticket | None:
        return self.session.get(Ticket, ticket_id)
