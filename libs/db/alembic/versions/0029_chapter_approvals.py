"""Add append-only chapter approval attestations."""

from alembic import op
import sqlalchemy as sa

revision = "0029_chapter_approvals"
down_revision = "0028_segment_direction_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chapter_approvals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_render_id", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.ForeignKeyConstraint(["chapter_render_id"], ["chapter_renders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chapter_approvals_project_id", "chapter_approvals", ["project_id"])
    op.create_index("ix_chapter_approvals_chapter_id", "chapter_approvals", ["chapter_id"])
    op.create_index(
        "ix_chapter_approvals_chapter_render_id",
        "chapter_approvals",
        ["chapter_render_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chapter_approvals_chapter_render_id", table_name="chapter_approvals")
    op.drop_index("ix_chapter_approvals_chapter_id", table_name="chapter_approvals")
    op.drop_index("ix_chapter_approvals_project_id", table_name="chapter_approvals")
    op.drop_table("chapter_approvals")
