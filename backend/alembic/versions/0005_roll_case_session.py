"""Associate recorded rolls with an optional case session.

Revision ID: 0005_roll_case_session
Revises: 0004_coc7_rule_engines
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_roll_case_session"
down_revision: str | None = "0004_coc7_rule_engines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("roll_records") as batch:
        batch.add_column(sa.Column("case_session_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_roll_records_case_session_id",
            "case_sessions",
            ["case_session_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_roll_records_case_session_id", ["case_session_id"])


def downgrade() -> None:
    with op.batch_alter_table("roll_records") as batch:
        batch.drop_index("ix_roll_records_case_session_id")
        batch.drop_constraint("fk_roll_records_case_session_id", type_="foreignkey")
        batch.drop_column("case_session_id")
