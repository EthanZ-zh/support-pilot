"""Initial deterministic business baseline.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.String(length=150), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'succeeded', 'failed')",
            name=op.f("ck_idempotency_records_valid_status"),
        ),
        sa.PrimaryKeyConstraint("scope", "key", name=op.f("pk_idempotency_records")),
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_code", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("regions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_message", sa.Text(), nullable=False),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('sev1', 'sev2', 'sev3', 'sev4')",
            name=op.f("ck_incidents_valid_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('investigating', 'identified', 'monitoring', 'resolved')",
            name=op.f("ck_incidents_valid_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        sa.UniqueConstraint("public_code", name=op.f("uq_incidents_public_code")),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
        sa.UniqueConstraint("code", name=op.f("uq_plans_code")),
    )
    op.create_table(
        "service_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('operational', 'degraded', 'partial_outage', 'major_outage', "
            "'maintenance')",
            name=op.f("ck_service_components_valid_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_components")),
        sa.UniqueConstraint("code", "region", name="uq_service_component_code_region"),
    )
    op.create_table(
        "incident_components",
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["component_id"],
            ["service_components.id"],
            name=op.f("fk_incident_components_component_id_service_components"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_components_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("incident_id", "component_id", name=op.f("pk_incident_components")),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("region", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("data_origin", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "data_origin IN ('synthetic', 'human_labeled', 'public')",
            name=op.f("ck_tenants_valid_data_origin"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name=op.f("ck_tenants_valid_status"),
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name=op.f("fk_tenants_plan_id_plans")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("metadata_redacted", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'agent', 'system')",
            name=op.f("ck_audit_events_valid_actor_type"),
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure', 'denied')",
            name=op.f("ck_audit_events_valid_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_audit_events_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_event_trace_created", "audit_events", ["trace_id", "created_at"])
    op.create_index(op.f("ix_audit_events_tenant_id"), "audit_events", ["tenant_id"])
    op.create_table(
        "entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("feature_code", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('plan', 'override', 'trial')",
            name=op.f("ck_entitlements_valid_source"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_entitlements_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlements")),
        sa.UniqueConstraint(
            "tenant_id", "feature_code", "effective_from", name="uq_entitlement_window"
        ),
    )
    op.create_index(op.f("ix_entitlements_tenant_id"), "entitlements", ["tenant_id"])
    op.create_table(
        "quota_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("metric_code", sa.String(length=100), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint('"limit" >= 0', name=op.f("ck_quota_snapshots_non_negative_limit")),
        sa.CheckConstraint(
            "period_end > period_start", name=op.f("ck_quota_snapshots_valid_period")
        ),
        sa.CheckConstraint("used >= 0", name=op.f("ck_quota_snapshots_non_negative_used")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_quota_snapshots_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quota_snapshots")),
    )
    op.create_index(
        "ix_quota_snapshot_lookup",
        "quota_snapshots",
        ["tenant_id", "metric_code", "measured_at"],
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('customer_developer', 'tenant_admin', 'support_agent', 'knowledge_admin')",
            name=op.f("ck_users_valid_role"),
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_users_valid_status")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"])
    op.create_table(
        "support_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("raw_message", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=30), nullable=False),
        sa.Column("risk_level", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "intent IN ('entitlement', 'quota', 'incident', 'ticket_request', 'high_risk')",
            name=op.f("ck_support_requests_valid_intent"),
        ),
        sa.CheckConstraint(
            "risk_level IN ('R1', 'R2', 'R3')",
            name=op.f("ck_support_requests_valid_risk_level"),
        ),
        sa.CheckConstraint(
            "status IN ('received', 'running', 'answered', 'escalated', 'failed', 'refused')",
            name=op.f("ck_support_requests_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_support_requests_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_support_requests_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_requests")),
        sa.UniqueConstraint("trace_id", name=op.f("uq_support_requests_trace_id")),
    )
    op.create_index(op.f("ix_support_requests_session_id"), "support_requests", ["session_id"])
    op.create_index(op.f("ix_support_requests_tenant_id"), "support_requests", ["tenant_id"])
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_code", sa.String(length=30), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_request_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("diagnostic_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("escalation_reason", sa.String(length=40), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('authentication', 'entitlement', 'quota', 'incident', "
            "'integration', 'other')",
            name=op.f("ck_tickets_valid_category"),
        ),
        sa.CheckConstraint(
            "escalation_reason IN ('user_requested', 'low_answerability', 'high_risk', "
            "'tool_failure', 'security_or_privacy', 'unknown')",
            name=op.f("ck_tickets_valid_escalation_reason"),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'urgent')",
            name=op.f("ck_tickets_valid_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'triaged', 'in_progress', 'waiting_customer', "
            "'resolved', 'closed')",
            name=op.f("ck_tickets_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name=op.f("fk_tickets_assignee_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["source_request_id"],
            ["support_requests.id"],
            name=op.f("fk_tickets_source_request_id_support_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tickets_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("public_code", name=op.f("uq_tickets_public_code")),
        sa.UniqueConstraint("source_request_id", name=op.f("uq_tickets_source_request_id")),
    )
    op.create_index(op.f("ix_tickets_tenant_id"), "tickets", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_tenant_id"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_index(op.f("ix_support_requests_tenant_id"), table_name="support_requests")
    op.drop_index(op.f("ix_support_requests_session_id"), table_name="support_requests")
    op.drop_table("support_requests")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.drop_index("ix_quota_snapshot_lookup", table_name="quota_snapshots")
    op.drop_table("quota_snapshots")
    op.drop_index(op.f("ix_entitlements_tenant_id"), table_name="entitlements")
    op.drop_table("entitlements")
    op.drop_index(op.f("ix_audit_events_tenant_id"), table_name="audit_events")
    op.drop_index("ix_audit_event_trace_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("tenants")
    op.drop_table("incident_components")
    op.drop_table("service_components")
    op.drop_table("plans")
    op.drop_table("incidents")
    op.drop_table("idempotency_records")
