"""Add sound design asset and cue metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0021_sound_design"
down_revision = "0020_tts_production_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ambience_assets",
        sa.Column("asset_type", sa.String(32), nullable=False, server_default="ambience"),
    )
    op.add_column("ambience_assets", sa.Column("duration_ms", sa.Integer()))
    op.add_column(
        "ambience_cues",
        sa.Column("cue_type", sa.String(32), nullable=False, server_default="ambience"),
    )
    op.add_column(
        "ambience_cues",
        sa.Column("start_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ambience_cues",
        sa.Column("ducking", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "ambience_cues",
        sa.Column("render_mode", sa.String(32), nullable=False, server_default="light"),
    )


def downgrade() -> None:
    op.drop_column("ambience_cues", "render_mode")
    op.drop_column("ambience_cues", "ducking")
    op.drop_column("ambience_cues", "start_ms")
    op.drop_column("ambience_cues", "cue_type")
    op.drop_column("ambience_assets", "duration_ms")
    op.drop_column("ambience_assets", "asset_type")
