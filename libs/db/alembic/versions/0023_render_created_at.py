"""Add created_at to segment renders, chapter renders, and export packages."""

from alembic import op
import sqlalchemy as sa

revision = "0023_render_created_at"
down_revision = "0022_readiness_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "segment_renders", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "chapter_renders", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "export_packages", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("export_packages", "created_at")
    op.drop_column("chapter_renders", "created_at")
    op.drop_column("segment_renders", "created_at")
