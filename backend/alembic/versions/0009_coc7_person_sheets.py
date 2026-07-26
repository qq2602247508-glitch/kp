"""add COC7 NPC and mythos entity sheets

Revision ID: 0009_coc7_person_sheets
Revises: 0008_ai_kp_proposal_expiry
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_coc7_person_sheets"
down_revision = "0008_ai_kp_proposal_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("case_people") as batch_op:
        batch_op.add_column(
            sa.Column(
                "person_type",
                sa.String(40),
                nullable=False,
                server_default="keeper_npc",
            )
        )
        batch_op.add_column(sa.Column("characteristics", sa.JSON()))
        batch_op.add_column(sa.Column("hit_points", sa.Integer()))
        batch_op.add_column(sa.Column("move_rate", sa.Integer()))
        batch_op.add_column(sa.Column("damage_bonus", sa.String(40)))
        batch_op.add_column(sa.Column("build", sa.Integer()))
        batch_op.add_column(sa.Column("armor", sa.String(200)))
        batch_op.add_column(sa.Column("sanity_loss", sa.String(120)))
        batch_op.add_column(sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("attacks", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(
            sa.Column(
                "special_abilities", sa.JSON(), nullable=False, server_default="[]"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("case_people") as batch_op:
        for name in (
            "special_abilities", "attacks", "skills", "sanity_loss", "armor",
            "build", "damage_bonus", "move_rate", "hit_points", "characteristics", "person_type",
        ):
            batch_op.drop_column(name)
