"""add measured voice catalog"""

from alembic import op
import sqlalchemy as sa

revision = "0033_voice_catalog"
down_revision = "0032_extraction_review_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_catalog_entries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("engine", sa.String(length=100), nullable=False),
        sa.Column("engine_version", sa.String(length=200), nullable=False),
        sa.Column("engine_voice_id", sa.String(length=200), nullable=False),
        sa.Column("synthesis_kind", sa.String(length=32), nullable=False, server_default="fixed"),
        sa.Column("gender", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("age_range", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("accent", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("locale", sa.String(length=32), nullable=False, server_default="und"),
        sa.Column("timbre_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("energy_default", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("acoustics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("embedding_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sample_paths_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("license_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("labeled_by_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("schema_version", sa.String(length=32), nullable=False, server_default="0.1.0"),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "engine", "engine_version", "engine_voice_id", name="uq_voice_catalog_engine_voice"
        ),
    )
    op.create_index("ix_voice_catalog_entries_engine", "voice_catalog_entries", ["engine"])
    with op.batch_alter_table("voice_profiles") as batch_op:
        batch_op.add_column(sa.Column("voice_catalog_entry_id", sa.String(length=64)))
        batch_op.create_foreign_key(
            "fk_voice_profiles_catalog_entry",
            "voice_catalog_entries",
            ["voice_catalog_entry_id"],
            ["id"],
        )
        batch_op.create_index("ix_voice_profiles_voice_catalog_entry_id", ["voice_catalog_entry_id"])


def downgrade() -> None:
    with op.batch_alter_table("voice_profiles") as batch_op:
        batch_op.drop_index("ix_voice_profiles_voice_catalog_entry_id")
        batch_op.drop_constraint("fk_voice_profiles_catalog_entry", type_="foreignkey")
        batch_op.drop_column("voice_catalog_entry_id")
    op.drop_index("ix_voice_catalog_entries_engine", table_name="voice_catalog_entries")
    op.drop_table("voice_catalog_entries")
