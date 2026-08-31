"""Add local demo authentication credentials.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$MtzpBsirEtF1rPaNlWyDaA$"
    "RSQrj2WRF9eCu6/kcx2N74yMiu1W2v1xGUeRRPYj6b8"
)


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=500), nullable=True))
    op.execute(
        sa.text(
            "UPDATE users SET email = 'user-' || id::text || '@example.invalid', "
            "password_hash = :password_hash"
        ).bindparams(password_hash=DEMO_PASSWORD_HASH)
    )
    op.alter_column("users", "email", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
