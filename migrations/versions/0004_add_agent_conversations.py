"""Add recoverable Agent conversation state.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_agent_runs_valid_status"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_status"),
        "agent_runs",
        "status IN ('running', 'answered', 'needs_clarification', 'needs_confirmation', "
        "'escalated', 'refused', 'cancelled', 'failed')",
    )
    op.create_table(
        "agent_conversations",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("pending_intent", sa.String(length=30), nullable=True),
        sa.Column("pending_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ticket_draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ticket_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confirmation_key_hash", sa.String(length=64), nullable=True),
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
        sa.CheckConstraint("version >= 1", name=op.f("ck_agent_conversations_positive_version")),
        sa.CheckConstraint(
            "pending_intent IS NULL OR pending_intent IN ('knowledge', 'entitlement', "
            "'quota', 'incident', 'ticket_request', 'high_risk', 'unknown')",
            name=op.f("ck_agent_conversations_valid_pending_intent"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'awaiting_clarification', 'awaiting_confirmation', "
            "'completed', 'cancelled')",
            name=op.f("ck_agent_conversations_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_agent_conversations_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_agent_conversations_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_agent_conversations")),
    )
    op.create_index(op.f("ix_agent_conversations_tenant_id"), "agent_conversations", ["tenant_id"])
    op.create_index(op.f("ix_agent_conversations_user_id"), "agent_conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_conversations_user_id"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_tenant_id"), table_name="agent_conversations")
    op.drop_table("agent_conversations")
    op.drop_constraint(op.f("ck_agent_runs_valid_status"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_status"),
        "agent_runs",
        "status IN ('running', 'answered', 'needs_clarification', 'needs_confirmation', "
        "'escalated', 'refused', 'failed')",
    )
