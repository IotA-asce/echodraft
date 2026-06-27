"""Add canonical text cleaning tables."""

import sqlalchemy as sa
from alembic import op

revision = "0014_cleaning"
down_revision = "0013_pdf_ocr_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cleaning_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("manifest_path", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_cleaning_runs_source_document_id", "cleaning_runs", ["source_document_id"])
    op.create_table(
        "text_cleanliness_issues",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("canonical_span_start", sa.Integer(), nullable=False),
        sa.Column("canonical_span_end", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("suggested_fix", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("resolved_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_text_cleanliness_issues_source_document_id",
        "text_cleanliness_issues",
        ["source_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_text_cleanliness_issues_source_document_id", table_name="text_cleanliness_issues"
    )
    op.drop_table("text_cleanliness_issues")
    op.drop_index("ix_cleaning_runs_source_document_id", table_name="cleaning_runs")
    op.drop_table("cleaning_runs")
