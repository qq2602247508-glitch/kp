"""harden COC7 chase state

Revision ID: 0006_chase_engine
Revises: 0005_roll_case_session
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_chase_engine"
down_revision = "0005_roll_case_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chases", sa.Column("round", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "chases",
        sa.Column("escape_distance", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "chases",
        sa.Column("track_length", sa.Integer(), nullable=False, server_default="10"),
    )


def downgrade() -> None:
    op.drop_column("chases", "track_length")
    op.drop_column("chases", "escape_distance")
    op.drop_column("chases", "round")
