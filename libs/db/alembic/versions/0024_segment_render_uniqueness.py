"""Enforce a single succeeded render per (segment_id, render_key)."""

from alembic import op
import sqlalchemy as sa

revision = "0024_segment_render_uniqueness"
down_revision = "0023_render_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Defuse pre-existing duplicates before enforcing uniqueness. Segment render history is
    # append-only, so mark all but the newest succeeded render of each
    # (segment_id, render_key) group as 'superseded' (UPDATE, never DELETE).
    op.execute(
        """
        UPDATE segment_renders
        SET status = 'superseded'
        WHERE status = 'succeeded'
          AND id NOT IN (
              SELECT id FROM (
                  SELECT id,
                         ROW_NUMBER() OVER (
                             PARTITION BY segment_id, render_key
                             ORDER BY created_at DESC, rowid DESC
                         ) AS rn
                  FROM segment_renders
                  WHERE status = 'succeeded'
              ) ranked
              WHERE ranked.rn = 1
          )
        """
    )
    op.create_index(
        "uq_segment_renders_succeeded_key",
        "segment_renders",
        ["segment_id", "render_key"],
        unique=True,
        sqlite_where=sa.text("status = 'succeeded'"),
    )


def downgrade() -> None:
    op.drop_index("uq_segment_renders_succeeded_key", table_name="segment_renders")
