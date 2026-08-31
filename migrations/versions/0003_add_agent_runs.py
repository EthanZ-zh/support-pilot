"""Add persistent Agent run snapshots and traces.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("raw_message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("intent", sa.String(length=30), nullable=True),
        sa.Column("risk_level", sa.String(length=2), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            "intent IS NULL OR intent IN ('knowledge', 'entitlement', 'quota', 'incident', "
            "'ticket_request', 'high_risk', 'unknown')",
            name=op.f("ck_agent_runs_valid_intent"),
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('R1', 'R2', 'R3')",
            name=op.f("ck_agent_runs_valid_risk_level"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'answered', 'needs_clarification', "
            "'needs_confirmation', 'escalated', 'refused', 'failed')",
            name=op.f("ck_agent_runs_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_agent_runs_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_agent_runs_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint("trace_id", name=op.f("uq_agent_runs_trace_id")),
    )
    op.create_index(op.f("ix_agent_runs_session_id"), "agent_runs", ["session_id"])
    op.create_index(op.f("ix_agent_runs_tenant_id"), "agent_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_tenant_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_session_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
