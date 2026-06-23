"""Add chapter renders."""

import sqlalchemy as sa
from alembic import op

revision = "0007_chapter_renders"
down_revision = "0006_segment_renders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chapter_renders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id")),
        sa.Column("status", sa.String(32)),
        sa.Column("speech_path", sa.Text()),
        sa.Column("manifest_path", sa.Text()),
        sa.Column("duration_ms", sa.Integer()),
    )


def downgrade() -> None:
    op.drop_table("chapter_renders")
