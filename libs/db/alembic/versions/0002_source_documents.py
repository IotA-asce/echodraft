"""add source documents

Revision ID: 0002_source_documents
Revises: 0001_foundations
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_source_documents"
down_revision = "0001_foundations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rights_status", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("canonical_path", sa.Text()),
        sa.Column("manifest_path", sa.Text()),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_source_documents_project_id", table_name="source_documents")
    op.drop_table("source_documents")
