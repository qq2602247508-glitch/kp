"""Add normalized native case state.

Revision ID: 0003_native_case_state
Revises: 0002_roll_records_and_audits
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_native_case_state"
down_revision: str | None = "0002_roll_records_and_audits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _core_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("player_visible_text", sa.Text(), nullable=False),
        sa.Column("keeper_truth", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
    ]


def _version_columns() -> list[sa.Column[object]]:
    return [
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
    ]


def _finish_table(table_name: str, version_constraint: str) -> None:
    op.create_index(op.f(f"ix_{table_name}_campaign_id"), table_name, ["campaign_id"])


def upgrade() -> None:
    op.create_table(
        "case_sessions",
        *_core_columns(),
        sa.Column("time_label", sa.String(length=120), nullable=True),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_session_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_sessions", "ck_case_session_version_positive")

    op.create_table(
        "case_people",
        *_core_columns(),
        sa.Column("role", sa.String(length=120), nullable=True),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_person_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_people", "ck_case_person_version_positive")

    op.create_table(
        "case_locations",
        *_core_columns(),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_location_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_locations", "ck_case_location_version_positive")

    op.create_table(
        "case_scenes",
        *_core_columns(),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_scene_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["case_locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["case_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_scenes", "ck_case_scene_version_positive")
    op.create_index(op.f("ix_case_scenes_location_id"), "case_scenes", ["location_id"])
    op.create_index(op.f("ix_case_scenes_session_id"), "case_scenes", ["session_id"])

    op.create_table(
        "case_clues",
        *_core_columns(),
        sa.Column("scene_id", sa.String(length=36), nullable=True),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("discovered", sa.Boolean(), nullable=False),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_clue_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["case_locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["person_id"], ["case_people.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scene_id"], ["case_scenes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_clues", "ck_case_clue_version_positive")
    op.create_index(op.f("ix_case_clues_location_id"), "case_clues", ["location_id"])
    op.create_index(op.f("ix_case_clues_person_id"), "case_clues", ["person_id"])
    op.create_index(op.f("ix_case_clues_scene_id"), "case_clues", ["scene_id"])

    op.create_table(
        "case_relationships",
        *_core_columns(),
        sa.Column("source_clue_id", sa.String(length=36), nullable=False),
        sa.Column("target_clue_id", sa.String(length=36), nullable=False),
        sa.Column("relationship_type", sa.String(length=80), nullable=False),
        *_version_columns(),
        sa.CheckConstraint("source_clue_id <> target_clue_id", name="ck_clue_link_distinct"),
        sa.CheckConstraint("version >= 1", name="ck_case_relationship_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_clue_id"], ["case_clues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_clue_id"], ["case_clues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_relationships", "ck_case_relationship_version_positive")
    op.create_index(
        op.f("ix_case_relationships_source_clue_id"),
        "case_relationships",
        ["source_clue_id"],
    )
    op.create_index(
        op.f("ix_case_relationships_target_clue_id"),
        "case_relationships",
        ["target_clue_id"],
    )

    op.create_table(
        "case_handouts",
        *_core_columns(),
        sa.Column("clue_id", sa.String(length=36), nullable=True),
        sa.Column("revealed", sa.Boolean(), nullable=False),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_handout_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clue_id"], ["case_clues.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_handouts", "ck_case_handout_version_positive")
    op.create_index(op.f("ix_case_handouts_clue_id"), "case_handouts", ["clue_id"])

    op.create_table(
        "case_timeline_events",
        *_core_columns(),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("scene_id", sa.String(length=36), nullable=True),
        sa.Column("time_label", sa.String(length=120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_version_columns(),
        sa.CheckConstraint("version >= 1", name="ck_case_timeline_version_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["case_scenes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["case_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _finish_table("case_timeline_events", "ck_case_timeline_version_positive")
    op.create_index(
        op.f("ix_case_timeline_events_scene_id"), "case_timeline_events", ["scene_id"]
    )
    op.create_index(
        op.f("ix_case_timeline_events_session_id"), "case_timeline_events", ["session_id"]
    )


def downgrade() -> None:
    for table_name in (
        "case_timeline_events",
        "case_handouts",
        "case_relationships",
        "case_clues",
        "case_scenes",
        "case_locations",
        "case_people",
        "case_sessions",
    ):
        op.drop_table(table_name)
