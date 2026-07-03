"""Add structure_signals_path to source documents.

Container ingestion (DOCX heading styles, EPUB spine/TOC) writes chapter signal
JSON to the filesystem; the DB stores only its path, never the payload.
"""

from alembic import op
import sqlalchemy as sa

revision = "0026_source_structure_signals"
down_revision = "0025_schema_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("structure_signals_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_documents", "structure_signals_path")
