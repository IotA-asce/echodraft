"""add segment renders"""

from alembic import op
import sqlalchemy as sa

revision = "0006_segment_renders"
down_revision = "0005_direction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "segment_renders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id"), nullable=False),
        sa.Column("render_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=False),
        sa.Column("metadata_path", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("parent_render_id", sa.String(64)),
        sa.Column("request_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_segment_renders_key", "segment_renders", ["segment_id", "render_key"])


def downgrade() -> None:
    op.drop_table("segment_renders")
