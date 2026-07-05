"""Add evidence metadata to segment directions."""

from alembic import op
import sqlalchemy as sa

revision = "0028_segment_direction_evidence"
down_revision = "0027_cast_merge_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "segment_directions",
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("segment_directions", "evidence_json")
