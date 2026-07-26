"""Add immutable roll records and mutation audits.

Revision ID: 0002_roll_records_and_audits
Revises: 0001_coc7_native_core
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_roll_records_and_audits"
down_revision: str | None = "0001_coc7_native_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roll_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("investigator_id", sa.String(length=36), nullable=True),
        sa.Column("ruleset", sa.String(length=20), nullable=False),
        sa.Column("skill_key", sa.String(length=80), nullable=True),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("request_data", sa.JSON(), nullable=False),
        sa.Column("resolution_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_roll_record_ruleset_coc7e"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investigator_id"], ["investigators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roll_records_campaign_id"), "roll_records", ["campaign_id"])
    op.create_index(
        op.f("ix_roll_records_investigator_id"), "roll_records", ["investigator_id"]
    )
    op.create_table(
        "state_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=True),
        sa.Column("ruleset", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=True),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_state_audit_ruleset_coc7e"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_state_audits_campaign_id"), "state_audits", ["campaign_id"])
    op.create_index(op.f("ix_state_audits_entity_id"), "state_audits", ["entity_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_state_audits_entity_id"), table_name="state_audits")
    op.drop_index(op.f("ix_state_audits_campaign_id"), table_name="state_audits")
    op.drop_table("state_audits")
    op.drop_index(op.f("ix_roll_records_investigator_id"), table_name="roll_records")
    op.drop_index(op.f("ix_roll_records_campaign_id"), table_name="roll_records")
    op.drop_table("roll_records")
