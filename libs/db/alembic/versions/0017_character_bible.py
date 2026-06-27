"""Expand character bible metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0017_character_bible"
down_revision = "0016_llm_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("canonical_name", sa.String(200)))
    op.add_column("characters", sa.Column("traits_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("characters", sa.Column("first_seen_source_id", sa.String(64)))
    op.add_column("characters", sa.Column("first_seen_chapter_id", sa.String(64)))
    op.add_column("characters", sa.Column("first_seen_segment_id", sa.String(64)))
    op.add_column("characters", sa.Column("merge_history_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("characters", sa.Column("split_history_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("characters", sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("characters", sa.Column("lock_reason", sa.Text()))
    op.add_column("characters", sa.Column("merged_into_character_id", sa.String(64)))


def downgrade() -> None:
    op.drop_column("characters", "merged_into_character_id")
    op.drop_column("characters", "lock_reason")
    op.drop_column("characters", "user_locked")
    op.drop_column("characters", "split_history_json")
    op.drop_column("characters", "merge_history_json")
    op.drop_column("characters", "first_seen_segment_id")
    op.drop_column("characters", "first_seen_chapter_id")
    op.drop_column("characters", "first_seen_source_id")
    op.drop_column("characters", "traits_json")
    op.drop_column("characters", "canonical_name")
