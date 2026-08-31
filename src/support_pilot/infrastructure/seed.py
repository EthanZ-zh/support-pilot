from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import (
    Entitlement,
    Incident,
    Plan,
    QuotaSnapshot,
    ServiceComponent,
    Tenant,
    UserAccount,
)

PLAN_STARTER_ID = UUID("10000000-0000-0000-0000-000000000001")
PLAN_ENTERPRISE_ID = UUID("10000000-0000-0000-0000-000000000002")
TENANT_ALPHA_ID = UUID("20000000-0000-0000-0000-000000000001")
TENANT_BETA_ID = UUID("20000000-0000-0000-0000-000000000002")
USER_ALPHA_ADMIN_ID = UUID("30000000-0000-0000-0000-000000000001")
USER_BETA_DEVELOPER_ID = UUID("30000000-0000-0000-0000-000000000002")
SUPPORT_AGENT_ID = UUID("30000000-0000-0000-0000-000000000003")
COMPONENT_REST_SG_ID = UUID("40000000-0000-0000-0000-000000000001")
INCIDENT_SG_ID = UUID("50000000-0000-0000-0000-000000000001")

FIXTURE_TIME = datetime(2026, 8, 1, tzinfo=UTC)
DEMO_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$MtzpBsirEtF1rPaNlWyDaA$"
    "RSQrj2WRF9eCu6/kcx2N74yMiu1W2v1xGUeRRPYj6b8"
)


def seed_synthetic_data(session: Session) -> None:
    if session.scalar(select(Plan.id).limit(1)) is not None:
        return

    starter = Plan(
        id=PLAN_STARTER_ID,
        code="starter",
        name="Starter（合成套餐）",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    enterprise = Plan(
        id=PLAN_ENTERPRISE_ID,
        code="enterprise",
        name="Enterprise（合成套餐）",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    alpha = Tenant(
        id=TENANT_ALPHA_ID,
        display_name="Alpha Lab（合成租户）",
        plan=starter,
        region="ap-southeast-1",
        status="active",
        data_origin="synthetic",
    )
    beta = Tenant(
        id=TENANT_BETA_ID,
        display_name="Beta Studio（合成租户）",
        plan=enterprise,
        region="ap-southeast-1",
        status="active",
        data_origin="synthetic",
    )
    session.add_all([starter, enterprise, alpha, beta])
    session.flush()
    session.add_all(
        [
            UserAccount(
                id=USER_ALPHA_ADMIN_ID,
                tenant_id=TENANT_ALPHA_ID,
                email="alpha.admin@example.com",
                password_hash=DEMO_PASSWORD_HASH,
                display_name="Alpha Admin（合成用户）",
                role="tenant_admin",
                status="active",
            ),
            UserAccount(
                id=USER_BETA_DEVELOPER_ID,
                tenant_id=TENANT_BETA_ID,
                email="beta.developer@example.com",
                password_hash=DEMO_PASSWORD_HASH,
                display_name="Beta Developer（合成用户）",
                role="customer_developer",
                status="active",
            ),
            UserAccount(
                id=SUPPORT_AGENT_ID,
                tenant_id=None,
                email="support.agent@example.com",
                password_hash=DEMO_PASSWORD_HASH,
                display_name="Support Agent（合成用户）",
                role="support_agent",
                status="active",
            ),
            Entitlement(
                tenant_id=TENANT_ALPHA_ID,
                feature_code="bulk_export",
                enabled=False,
                source="plan",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            Entitlement(
                tenant_id=TENANT_BETA_ID,
                feature_code="bulk_export",
                enabled=True,
                source="plan",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            QuotaSnapshot(
                tenant_id=TENANT_ALPHA_ID,
                metric_code="api_requests_monthly",
                limit=10_000,
                used=7_500,
                period_start=datetime(2026, 8, 1, tzinfo=UTC),
                period_end=datetime(2026, 9, 1, tzinfo=UTC),
                measured_at=FIXTURE_TIME,
            ),
        ]
    )
    component = ServiceComponent(
        id=COMPONENT_REST_SG_ID,
        code="rest_api",
        region="ap-southeast-1",
        status="degraded",
        observed_at=datetime(2026, 8, 1, 10, 25, tzinfo=UTC),
    )
    session.add(
        Incident(
            id=INCIDENT_SG_ID,
            public_code="INC-2026-0801",
            title="新加坡区域 REST API 延迟升高（合成事故）",
            severity="sev2",
            status="monitoring",
            regions=["ap-southeast-1"],
            started_at=datetime(2026, 8, 1, 10, 15, tzinfo=UTC),
            resolved_at=datetime(2026, 8, 1, 11, 30, tzinfo=UTC),
            customer_message="已确认区域性延迟，正在监控恢复情况。本事故为合成演示数据。",
            internal_notes="Synthetic fixture only.",
            components=[component],
        )
    )
    session.commit()
