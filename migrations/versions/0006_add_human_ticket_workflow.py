"""Add human ticket workflow and feedback.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET email = CASE id::text "
        "WHEN '30000000-0000-0000-0000-000000000001' THEN 'alpha.admin@example.com' "
        "WHEN '30000000-0000-0000-0000-000000000002' THEN 'beta.developer@example.com' "
        "WHEN '30000000-0000-0000-0000-000000000003' THEN 'support.agent@example.com' "
        "ELSE email END"
    )
    op.create_table(
        "ticket_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=False),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "from_status IN ('open', 'triaged', 'in_progress', 'waiting_customer', "
            "'resolved', 'closed')",
            name=op.f("ck_ticket_transitions_valid_from_status"),
        ),
        sa.CheckConstraint(
            "to_status IN ('open', 'triaged', 'in_progress', 'waiting_customer', "
            "'resolved', 'closed')",
            name=op.f("ck_ticket_transitions_valid_to_status"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_ticket_transitions_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_transitions_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_transitions")),
    )
    op.create_index(op.f("ix_ticket_transitions_ticket_id"), "ticket_transitions", ["ticket_id"])
    op.create_table(
        "human_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("resolution_category", sa.String(length=30), nullable=False),
        sa.Column("knowledge_gap", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "disposition IN ('accepted', 'edited', 'rejected')",
            name=op.f("ck_human_feedback_valid_disposition"),
        ),
        sa.CheckConstraint(
            "resolution_category IN ('authentication', 'entitlement', 'quota', "
            "'incident', 'integration', 'other')",
            name=op.f("ck_human_feedback_valid_resolution_category"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_human_feedback_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["users.id"], name=op.f("fk_human_feedback_reviewer_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_human_feedback_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_feedback")),
        sa.UniqueConstraint(
            "ticket_id",
            "agent_run_id",
            "reviewer_id",
            name="uq_human_feedback_review",
        ),
    )
    op.create_index(op.f("ix_human_feedback_agent_run_id"), "human_feedback", ["agent_run_id"])
    op.create_index(op.f("ix_human_feedback_ticket_id"), "human_feedback", ["ticket_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_human_feedback_ticket_id"), table_name="human_feedback")
    op.drop_index(op.f("ix_human_feedback_agent_run_id"), table_name="human_feedback")
    op.drop_table("human_feedback")
    op.drop_index(op.f("ix_ticket_transitions_ticket_id"), table_name="ticket_transitions")
    op.drop_table("ticket_transitions")
