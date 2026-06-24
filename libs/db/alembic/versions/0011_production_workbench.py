"""Add persisted production choices and export archives."""

import sqlalchemy as sa
from alembic import op

revision = "0011_production_workbench"
down_revision = "0010_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "voice_profiles",
        sa.Column("provider_voice_id", sa.String(200), nullable=False, server_default=""),
    )
    op.add_column("export_packages", sa.Column("archive_path", sa.Text()))
    op.create_table(
        "project_production_settings",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("narrator_voice_profile_id", sa.String(64), sa.ForeignKey("voice_profiles.id")),
        sa.Column("default_direction_json", sa.Text()),
    )
    op.create_table(
        "segment_production_overrides",
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id"), primary_key=True),
        sa.Column("voice_profile_id", sa.String(64), sa.ForeignKey("voice_profiles.id")),
        sa.Column("direction_json", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("segment_production_overrides")
    op.drop_table("project_production_settings")
    op.drop_column("export_packages", "archive_path")
    op.drop_column("voice_profiles", "provider_voice_id")
