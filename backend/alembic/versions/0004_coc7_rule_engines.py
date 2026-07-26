"""Add deterministic COC7 rule engine state and logs.

Revision ID: 0004_coc7_rule_engines
Revises: 0003_native_case_state
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_coc7_rule_engines"
down_revision: str | None = "0003_native_case_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("case_session_id", sa.String(length=36), nullable=True),
        sa.Column("session_key", sa.String(length=120), nullable=True),
        sa.Column("ruleset", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_chase_ruleset_coc7e"),
        sa.CheckConstraint("version >= 1", name="ck_chase_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["case_session_id"], ["case_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chases_campaign_id"), "chases", ["campaign_id"])
    op.create_index(op.f("ix_chases_case_session_id"), "chases", ["case_session_id"])
    op.create_index(op.f("ix_chases_session_key"), "chases", ["session_key"])

    op.create_table(
        "rule_operation_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("case_session_id", sa.String(length=36), nullable=True),
        sa.Column("session_key", sa.String(length=120), nullable=True),
        sa.Column("ruleset", sa.String(length=20), nullable=False),
        sa.Column("operation_type", sa.String(length=60), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=False),
        sa.Column("citation_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ruleset = 'coc7e'", name="ck_rule_operation_ruleset_coc7e"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["case_session_id"], ["case_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rule_operation_logs_campaign_id"),
        "rule_operation_logs",
        ["campaign_id"],
    )
    op.create_index(
        op.f("ix_rule_operation_logs_case_session_id"),
        "rule_operation_logs",
        ["case_session_id"],
    )
    op.create_index(
        op.f("ix_rule_operation_logs_operation_type"),
        "rule_operation_logs",
        ["operation_type"],
    )
    op.create_index(
        op.f("ix_rule_operation_logs_session_key"),
        "rule_operation_logs",
        ["session_key"],
    )
    op.create_index(
        op.f("ix_rule_operation_logs_subject_id"),
        "rule_operation_logs",
        ["subject_id"],
    )


def downgrade() -> None:
    op.drop_table("rule_operation_logs")
    op.drop_table("chases")
