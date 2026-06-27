"""Add page-aware PDF OCR ingestion tables."""

import sqlalchemy as sa
from alembic import op

revision = "0013_pdf_ocr_v2"
down_revision = "0012_model_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_pages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.Text()),
        sa.Column("embedded_text_path", sa.Text()),
        sa.Column("selected_text_path", sa.Text()),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_source_pages_source_document_id", "source_pages", ["source_document_id"])
    op.create_table(
        "ocr_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_ocr_runs_source_document_id", "ocr_runs", ["source_document_id"])
    op.create_table(
        "ocr_page_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ocr_run_id", sa.String(64), sa.ForeignKey("ocr_runs.id"), nullable=False),
        sa.Column("source_page_id", sa.String(64), sa.ForeignKey("source_pages.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text_path", sa.Text(), nullable=False),
        sa.Column("json_path", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_ocr_page_results_ocr_run_id", "ocr_page_results", ["ocr_run_id"])
    op.create_index("ix_ocr_page_results_source_page_id", "ocr_page_results", ["source_page_id"])
    op.create_table(
        "canonical_spans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("canonical_start_offset", sa.Integer(), nullable=False),
        sa.Column("canonical_end_offset", sa.Integer(), nullable=False),
        sa.Column("source_text_hash", sa.String(128), nullable=False),
        sa.Column("bbox_json", sa.Text()),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_canonical_spans_source_document_id", "canonical_spans", ["source_document_id"])


def downgrade() -> None:
    op.drop_index("ix_canonical_spans_source_document_id", table_name="canonical_spans")
    op.drop_table("canonical_spans")
    op.drop_index("ix_ocr_page_results_source_page_id", table_name="ocr_page_results")
    op.drop_index("ix_ocr_page_results_ocr_run_id", table_name="ocr_page_results")
    op.drop_table("ocr_page_results")
    op.drop_index("ix_ocr_runs_source_document_id", table_name="ocr_runs")
    op.drop_table("ocr_runs")
    op.drop_index("ix_source_pages_source_document_id", table_name="source_pages")
    op.drop_table("source_pages")
