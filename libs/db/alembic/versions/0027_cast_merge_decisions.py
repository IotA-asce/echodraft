"""Add cast_merge_decisions table.

Remembers human rulings on whether two cast names are the same character so
corrections teach the pipeline: rejected pairs stop being re-flagged and both
confirmed/rejected decisions seed the cast merge LLM prompt. The DB stores only
the normalized name pair, decision, and reason -- no manuscript text.
"""

from alembic import op
import sqlalchemy as sa

revision = "0027_cast_merge_decisions"
down_revision = "0026_source_structure_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cast_merge_decisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name_a", sa.String(length=200), nullable=False),
        sa.Column("name_b", sa.String(length=200), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cast_merge_decisions_project_id", "cast_merge_decisions", ["project_id"]
    )
    op.create_index(
        "ix_cast_merge_decisions_pair",
        "cast_merge_decisions",
        ["project_id", "name_a", "name_b"],
    )


def downgrade() -> None:
    op.drop_index("ix_cast_merge_decisions_pair", table_name="cast_merge_decisions")
    op.drop_index("ix_cast_merge_decisions_project_id", table_name="cast_merge_decisions")
    op.drop_table("cast_merge_decisions")
