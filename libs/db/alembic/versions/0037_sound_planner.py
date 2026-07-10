"""add deterministic sound planner provenance"""

from alembic import op
import sqlalchemy as sa

revision = "0037_sound_planner"
down_revision = "0036_scene_atmosphere_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ambience_assets", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("ambience_assets", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("ambience_assets", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column("ambience_assets", sa.Column("cache_key", sa.String(64), nullable=True))
    op.add_column(
        "ambience_assets",
        sa.Column("qa_status", sa.String(32), nullable=False, server_default="n/a"),
    )
    op.create_index("ix_ambience_assets_cache_key", "ambience_assets", ["cache_key"])
    op.add_column(
        "ambience_cues",
        sa.Column("origin", sa.String(32), nullable=False, server_default="user_created"),
    )
    op.add_column(
        "ambience_cues",
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "ambience_cues",
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "ambience_cues",
        sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "project_production_settings",
        sa.Column("auto_sound_design_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_production_settings", "auto_sound_design_json")
    op.drop_column("ambience_cues", "user_locked")
    op.drop_column("ambience_cues", "muted")
    op.drop_column("ambience_cues", "evidence_json")
    op.drop_column("ambience_cues", "origin")
    op.drop_index("ix_ambience_assets_cache_key", table_name="ambience_assets")
    op.drop_column("ambience_assets", "qa_status")
    op.drop_column("ambience_assets", "cache_key")
    op.drop_column("ambience_assets", "seed")
    op.drop_column("ambience_assets", "prompt")
    op.drop_column("ambience_assets", "model")
