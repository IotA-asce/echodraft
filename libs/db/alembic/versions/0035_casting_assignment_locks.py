"""add casting assignment locks and decision links"""

from alembic import op
import sqlalchemy as sa

revision = "0035_casting_assignment_locks"
down_revision = "0034_casting_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("character_voice_assignments") as batch_op:
        batch_op.add_column(
            sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("locked_reason", sa.Text()))
        batch_op.add_column(sa.Column("casting_decision_id", sa.String(length=64)))
        batch_op.create_foreign_key(
            "fk_character_voice_assignments_casting_decision",
            "casting_decisions",
            ["casting_decision_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_character_voice_assignments_casting_decision_id",
            ["casting_decision_id"],
        )
    op.execute(
        "UPDATE character_voice_assignments "
        "SET casting_decision_id = ("
        "SELECT casting_decisions.id FROM casting_decisions "
        "WHERE casting_decisions.character_id = character_voice_assignments.character_id "
        "AND casting_decisions.role = 'character' "
        "AND casting_decisions.superseded_by_id IS NULL LIMIT 1"
        ") WHERE EXISTS ("
        "SELECT 1 FROM casting_decisions "
        "WHERE casting_decisions.character_id = character_voice_assignments.character_id "
        "AND casting_decisions.role = 'character' "
        "AND casting_decisions.superseded_by_id IS NULL"
        ")"
    )
    op.execute(
        "UPDATE character_voice_assignments "
        "SET user_locked = 1, locked_reason = 'Legacy hand assignment preserved during v2 migration' "
        "WHERE casting_decision_id IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("character_voice_assignments") as batch_op:
        batch_op.drop_index("ix_character_voice_assignments_casting_decision_id")
        batch_op.drop_constraint(
            "fk_character_voice_assignments_casting_decision", type_="foreignkey"
        )
        batch_op.drop_column("casting_decision_id")
        batch_op.drop_column("locked_reason")
        batch_op.drop_column("user_locked")
