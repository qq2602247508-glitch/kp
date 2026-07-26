"""allow COC7 improved skills above 100 percent

Revision ID: 0010_skill_values_above_100
Revises: 0009_coc7_person_sheets
"""

from alembic import op

revision = "0010_skill_values_above_100"
down_revision = "0009_coc7_person_sheets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("investigator_skills") as batch_op:
        batch_op.drop_constraint("ck_skill_current", type_="check")
        batch_op.create_check_constraint(
            "ck_skill_current", "current_value >= 0 AND current_value <= 999"
        )


def downgrade() -> None:
    with op.batch_alter_table("investigator_skills") as batch_op:
        batch_op.drop_constraint("ck_skill_current", type_="check")
        batch_op.create_check_constraint(
            "ck_skill_current", "current_value >= 0 AND current_value <= 100"
        )
