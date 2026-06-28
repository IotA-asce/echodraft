"""Add persisted readiness reports."""

from alembic import op
import sqlalchemy as sa

revision = "0022_readiness_reports"
down_revision = "0021_sound_design"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "readiness_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("checks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_readiness_reports_project", "readiness_reports", ["project_id"])
    op.create_index("ix_readiness_reports_chapter", "readiness_reports", ["chapter_id"])


def downgrade() -> None:
    op.drop_index("ix_readiness_reports_chapter", table_name="readiness_reports")
    op.drop_index("ix_readiness_reports_project", table_name="readiness_reports")
    op.drop_table("readiness_reports")
