"""Add local LLM run records."""

import sqlalchemy as sa
from alembic import op

revision = "0016_llm_runs"
down_revision = "0015_structure_parser_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id")),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("prompt_path", sa.Text()),
        sa.Column("response_path", sa.Text()),
        sa.Column("schema_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_llm_runs_project_id", "llm_runs", ["project_id"])
    op.create_index("ix_llm_runs_source_document_id", "llm_runs", ["source_document_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_runs_source_document_id", table_name="llm_runs")
    op.drop_index("ix_llm_runs_project_id", table_name="llm_runs")
    op.drop_table("llm_runs")
