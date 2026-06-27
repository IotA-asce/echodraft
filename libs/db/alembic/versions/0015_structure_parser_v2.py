"""Add structure parser v2 metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0015_structure_parser_v2"
down_revision = "0014_cleaning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("chapters", "scenes", "segments"):
        op.add_column(
            table_name,
            sa.Column("parser_evidence_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.add_column(
            table_name,
            sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(table_name, sa.Column("lock_reason", sa.Text()))

    op.create_table(
        "structure_parser_warnings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_document_id", sa.String(64), sa.ForeignKey("source_documents.id")),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_structure_parser_warnings_project_id",
        "structure_parser_warnings",
        ["project_id"],
    )
    op.create_index(
        "ix_structure_parser_warnings_source_document_id",
        "structure_parser_warnings",
        ["source_document_id"],
    )
    op.create_index(
        "ix_structure_parser_warnings_scope_id",
        "structure_parser_warnings",
        ["scope_id"],
    )

    op.create_table(
        "structure_locks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_structure_locks_project_id", "structure_locks", ["project_id"])
    op.create_index("ix_structure_locks_scope_id", "structure_locks", ["scope_id"])


def downgrade() -> None:
    op.drop_index("ix_structure_locks_scope_id", table_name="structure_locks")
    op.drop_index("ix_structure_locks_project_id", table_name="structure_locks")
    op.drop_table("structure_locks")

    op.drop_index("ix_structure_parser_warnings_scope_id", table_name="structure_parser_warnings")
    op.drop_index(
        "ix_structure_parser_warnings_source_document_id",
        table_name="structure_parser_warnings",
    )
    op.drop_index(
        "ix_structure_parser_warnings_project_id",
        table_name="structure_parser_warnings",
    )
    op.drop_table("structure_parser_warnings")

    for table_name in ("segments", "scenes", "chapters"):
        op.drop_column(table_name, "lock_reason")
        op.drop_column(table_name, "user_locked")
        op.drop_column(table_name, "parser_evidence_json")
