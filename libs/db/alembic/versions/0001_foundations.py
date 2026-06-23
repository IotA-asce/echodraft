"""create foundation tables

Revision ID: 0001_foundations
Revises:
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_foundations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("author", sa.String(length=200)),
        sa.Column("description", sa.Text()),
        sa.Column("rights_status", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("projects.id")),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "rights_declarations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("declaration_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence_path", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rights_declarations_project_id", "rights_declarations", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_rights_declarations_project_id", table_name="rights_declarations")
    op.drop_table("rights_declarations")
    op.drop_table("jobs")
    op.drop_table("projects")
