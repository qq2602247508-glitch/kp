"""add expiry to AI KP proposals

Revision ID: 0008_ai_kp_proposal_expiry
Revises: 0007_ai_kp_proposals
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_ai_kp_proposal_expiry"
down_revision = "0007_ai_kp_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_proposals") as batch_op:
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.execute(
        sa.text(
            "UPDATE ai_proposals "
            "SET expires_at = datetime(COALESCE(created_at, CURRENT_TIMESTAMP), '+1 hour') "
            "WHERE expires_at IS NULL"
        )
    )
    with op.batch_alter_table("ai_proposals") as batch_op:
        batch_op.alter_column("expires_at", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_proposals") as batch_op:
        batch_op.drop_column("expires_at")
