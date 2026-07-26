"""add AI KP pending proposals and decision audits

Revision ID: 0007_ai_kp_proposals
Revises: 0006_chase_engine
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_ai_kp_proposals"
down_revision = "0006_chase_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.String(36),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ruleset", sa.String(20), nullable=False, server_default="coc7e"),
        sa.Column("proposal_type", sa.String(40), nullable=False),
        sa.Column("case_kind", sa.String(40), nullable=False),
        sa.Column("target_entity_id", sa.String(36)),
        sa.Column("campaign_version", sa.Integer(), nullable=False),
        sa.Column("target_version", sa.Integer()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("citation_ids", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("applied_entity_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_ai_proposal_ruleset_coc7e"),
        sa.CheckConstraint(
            "proposal_type IN ('case_state_create', 'case_state_replace')",
            name="ck_ai_proposal_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_ai_proposal_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_ai_proposal_version_positive"),
    )
    op.create_index("ix_ai_proposals_campaign_id", "ai_proposals", ["campaign_id"])
    op.create_index(
        "ix_ai_proposals_target_entity_id", "ai_proposals", ["target_entity_id"]
    )
    op.create_table(
        "proposal_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("ai_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.String(36),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ruleset", sa.String(20), nullable=False, server_default="coc7e"),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=False),
        sa.Column("after_data", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_proposal_audit_ruleset_coc7e"),
    )
    op.create_index("ix_proposal_audits_proposal_id", "proposal_audits", ["proposal_id"])
    op.create_index("ix_proposal_audits_campaign_id", "proposal_audits", ["campaign_id"])


def downgrade() -> None:
    op.drop_table("proposal_audits")
    op.drop_table("ai_proposals")
