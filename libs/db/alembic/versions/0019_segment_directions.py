"""Add segment direction records."""

import sqlalchemy as sa
from alembic import op

revision = "0019_segment_directions"
down_revision = "0018_speaker_attributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "segment_directions",
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id"), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("direction_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("direction_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_segment_directions_project_id", "segment_directions", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_segment_directions_project_id", table_name="segment_directions")
    op.drop_table("segment_directions")
