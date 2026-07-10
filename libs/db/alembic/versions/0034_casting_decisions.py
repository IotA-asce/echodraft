"""add automatic casting decisions and settings"""

from alembic import op
import sqlalchemy as sa

revision = "0034_casting_decisions"
down_revision = "0033_voice_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "casting_decisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64)),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("voice_catalog_entry_id", sa.String(length=64), nullable=False),
        sa.Column("prominence_class", sa.String(length=32)),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("candidate_scores_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locked_reason", sa.Text()),
        sa.Column("superseded_by_id", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["voice_catalog_entry_id"], ["voice_catalog_entries.id"]),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["casting_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_casting_decisions_project_role",
        "casting_decisions",
        ["project_id", "role"],
    )
    op.create_index(
        "uq_casting_decisions_active_character",
        "casting_decisions",
        ["project_id", "character_id"],
        unique=True,
        sqlite_where=sa.text("superseded_by_id IS NULL AND role = 'character'"),
    )
    op.create_index(
        "uq_casting_decisions_active_narrator",
        "casting_decisions",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("superseded_by_id IS NULL AND role = 'narrator'"),
    )
    with op.batch_alter_table("project_production_settings") as batch_op:
        batch_op.add_column(sa.Column("narrator_casting_decision_id", sa.String(length=64)))
        batch_op.add_column(
            sa.Column(
                "casting_style_preset",
                sa.String(length=32),
                nullable=False,
                server_default="warm_neutral",
            )
        )
        batch_op.add_column(
            sa.Column("auto_cast_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.create_foreign_key(
            "fk_production_settings_narrator_casting_decision",
            "casting_decisions",
            ["narrator_casting_decision_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("project_production_settings") as batch_op:
        batch_op.drop_constraint(
            "fk_production_settings_narrator_casting_decision", type_="foreignkey"
        )
        batch_op.drop_column("auto_cast_enabled")
        batch_op.drop_column("casting_style_preset")
        batch_op.drop_column("narrator_casting_decision_id")
    op.drop_index(
        "uq_casting_decisions_active_narrator", table_name="casting_decisions"
    )
    op.drop_index(
        "uq_casting_decisions_active_character", table_name="casting_decisions"
    )
    op.drop_index("ix_casting_decisions_project_role", table_name="casting_decisions")
    op.drop_table("casting_decisions")
