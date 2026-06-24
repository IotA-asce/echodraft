"""Add ambience records and chapter mix fields."""

import sqlalchemy as sa
from alembic import op

revision = "0009_ambience"
down_revision = "0008_review_patching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chapter_renders",
        sa.Column("render_mode", sa.String(32), nullable=False, server_default="speech_only"),
    )
    op.add_column("chapter_renders", sa.Column("ambience_stem_path", sa.Text()))
    op.add_column("chapter_renders", sa.Column("mixed_audio_path", sa.Text()))
    op.create_table(
        "ambience_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("asset_path", sa.Text(), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
    )
    op.create_table(
        "ambience_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("gain_db", sa.Float(), nullable=False),
    )
    op.create_table(
        "ambience_cues",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("scenes.id")),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("ambience_assets.id")),
        sa.Column("gain_db", sa.Float(), nullable=False),
        sa.Column("fade_in_ms", sa.Integer(), nullable=False),
        sa.Column("fade_out_ms", sa.Integer(), nullable=False),
        sa.Column("no_sfx", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ambience_cues")
    op.drop_table("ambience_profiles")
    op.drop_table("ambience_assets")
    op.drop_column("chapter_renders", "mixed_audio_path")
    op.drop_column("chapter_renders", "ambience_stem_path")
    op.drop_column("chapter_renders", "render_mode")
