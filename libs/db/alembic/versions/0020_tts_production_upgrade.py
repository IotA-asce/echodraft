"""Add TTS render queue rows."""

from alembic import op
import sqlalchemy as sa

revision = "0020_tts_production_upgrade"
down_revision = "0019_segment_directions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "render_queue_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id"), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("voice_profile_id", sa.String(64), sa.ForeignKey("voice_profiles.id")),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("render_key", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_render_queue_project", "render_queue_items", ["project_id"])
    op.create_index("ix_render_queue_chapter", "render_queue_items", ["chapter_id"])
    op.create_index("ix_render_queue_segment", "render_queue_items", ["segment_id"])
    op.create_index("ix_render_queue_job", "render_queue_items", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_render_queue_job", table_name="render_queue_items")
    op.drop_index("ix_render_queue_segment", table_name="render_queue_items")
    op.drop_index("ix_render_queue_chapter", table_name="render_queue_items")
    op.drop_index("ix_render_queue_project", table_name="render_queue_items")
    op.drop_table("render_queue_items")
