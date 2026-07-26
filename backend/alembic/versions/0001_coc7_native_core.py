"""Create native COC7 campaign and investigator core.

Revision ID: 0001_coc7_native_core
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_coc7_native_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("ruleset", sa.String(length=20), nullable=False),
        sa.Column("era", sa.String(length=40), nullable=False),
        sa.Column("custom_era_label", sa.String(length=100), nullable=True),
        sa.Column("in_world_date", sa.String(length=100), nullable=True),
        sa.Column("starting_location", sa.String(length=200), nullable=True),
        sa.Column("enabled_source_pack_ids", sa.JSON(), nullable=False),
        sa.Column("house_rules", sa.JSON(), nullable=False),
        sa.Column("keeper_notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)")
        ),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_campaign_ruleset_coc7e"),
        sa.CheckConstraint("version >= 1", name="ck_campaign_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "source_packs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pack_id", sa.String(length=80), nullable=False),
        sa.Column("ruleset", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("edition", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("default_enabled", sa.Boolean(), nullable=False),
        sa.Column("eras", sa.JSON(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)")
        ),
        sa.CheckConstraint("ruleset = 'coc7e'", name="ck_source_pack_ruleset_coc7e"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pack_id", "version", name="uq_source_pack_version"),
    )
    op.create_table(
        "investigators",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("player_name", sa.String(length=160), nullable=True),
        sa.Column("occupation", sa.String(length=160), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("gender", sa.String(length=80), nullable=True),
        sa.Column("residence", sa.String(length=200), nullable=True),
        sa.Column("birthplace", sa.String(length=200), nullable=True),
        sa.Column("era", sa.String(length=80), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False),
        sa.Column("constitution", sa.Integer(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("dexterity", sa.Integer(), nullable=False),
        sa.Column("appearance", sa.Integer(), nullable=False),
        sa.Column("intelligence", sa.Integer(), nullable=False),
        sa.Column("power", sa.Integer(), nullable=False),
        sa.Column("education", sa.Integer(), nullable=False),
        sa.Column("hit_points", sa.Integer(), nullable=False),
        sa.Column("magic_points", sa.Integer(), nullable=False),
        sa.Column("sanity", sa.Integer(), nullable=False),
        sa.Column("luck", sa.Integer(), nullable=False),
        sa.Column("mythos", sa.Integer(), nullable=False),
        sa.Column("move_rate", sa.Integer(), nullable=False),
        sa.Column("damage_bonus", sa.String(length=40), nullable=False),
        sa.Column("build", sa.Integer(), nullable=False),
        sa.Column("credit_rating", sa.Integer(), nullable=False),
        sa.Column("spending_level", sa.String(length=120), nullable=True),
        sa.Column("cash", sa.String(length=120), nullable=True),
        sa.Column("assets", sa.Text(), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)")
        ),
        sa.CheckConstraint("age >= 15", name="ck_investigator_age"),
        sa.CheckConstraint("hit_points >= 0", name="ck_investigator_hp"),
        sa.CheckConstraint("luck >= 0 AND luck <= 100", name="ck_investigator_luck"),
        sa.CheckConstraint("magic_points >= 0", name="ck_investigator_mp"),
        sa.CheckConstraint("mythos >= 0 AND mythos <= 100", name="ck_investigator_mythos"),
        sa.CheckConstraint("sanity >= 0 AND sanity <= 100", name="ck_investigator_sanity"),
        sa.CheckConstraint("version >= 1", name="ck_investigator_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investigators_campaign_id"), "investigators", ["campaign_id"], unique=False
    )
    op.create_table(
        "investigator_backstories",
        sa.Column("investigator_id", sa.String(length=36), nullable=False),
        sa.Column("personal_description", sa.JSON(), nullable=False),
        sa.Column("ideology_and_beliefs", sa.JSON(), nullable=False),
        sa.Column("significant_people", sa.JSON(), nullable=False),
        sa.Column("meaningful_locations", sa.JSON(), nullable=False),
        sa.Column("treasured_possessions", sa.JSON(), nullable=False),
        sa.Column("traits", sa.JSON(), nullable=False),
        sa.Column("injuries_and_scars", sa.JSON(), nullable=False),
        sa.Column("phobias_and_manias", sa.JSON(), nullable=False),
        sa.Column("mythos_tomes_spells_artifacts", sa.JSON(), nullable=False),
        sa.Column("strange_encounters", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["investigator_id"], ["investigators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("investigator_id"),
    )
    op.create_table(
        "investigator_skills",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigator_id", sa.String(length=36), nullable=False),
        sa.Column("skill_key", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("specialization", sa.String(length=100), nullable=True),
        sa.Column("specialization_key", sa.String(length=100), nullable=False),
        sa.Column("base_value", sa.Integer(), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False),
        sa.Column("improvement_mark", sa.Boolean(), nullable=False),
        sa.Column("source_pack_id", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "base_value >= 0 AND base_value <= 100",
            name="ck_skill_base",
        ),
        sa.CheckConstraint(
            "current_value >= 0 AND current_value <= 100",
            name="ck_skill_current",
        ),
        sa.ForeignKeyConstraint(["investigator_id"], ["investigators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "investigator_id",
            "skill_key",
            "specialization_key",
            name="uq_investigator_skill_identity",
        ),
    )
    op.create_index(
        op.f("ix_investigator_skills_investigator_id"),
        "investigator_skills",
        ["investigator_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_investigator_skills_investigator_id"), table_name="investigator_skills"
    )
    op.drop_table("investigator_skills")
    op.drop_table("investigator_backstories")
    op.drop_index(op.f("ix_investigators_campaign_id"), table_name="investigators")
    op.drop_table("investigators")
    op.drop_table("source_packs")
    op.drop_table("campaigns")

