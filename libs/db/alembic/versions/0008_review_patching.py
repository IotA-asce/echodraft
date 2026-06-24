"""Add review and selective patching records."""

import sqlalchemy as sa
from alembic import op

revision = "0008_review_patching"
down_revision = "0007_chapter_renders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id")),
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id")),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(256), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("issue_id", sa.String(64), sa.ForeignKey("issues.id")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "patch_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("issue_id", sa.String(64), sa.ForeignKey("issues.id")),
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id")),
        sa.Column("old_render_id", sa.String(64), sa.ForeignKey("segment_renders.id")),
        sa.Column("new_render_id", sa.String(64), sa.ForeignKey("segment_renders.id")),
        sa.Column("chapter_render_id", sa.String(64), sa.ForeignKey("chapter_renders.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("patch_attempts")
    op.drop_table("comments")
    op.drop_table("issues")
