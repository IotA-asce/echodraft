"""add structure extraction tables"""
from alembic import op
import sqlalchemy as sa

revision = "0003_structure"
down_revision = "0002_source_documents"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("chapters", sa.Column("id", sa.String(64), primary_key=True), sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False), sa.Column("order_index", sa.Integer(), nullable=False), sa.Column("title", sa.String(512)), sa.Column("start_offset", sa.Integer(), nullable=False), sa.Column("end_offset", sa.Integer(), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("status", sa.String(32), nullable=False))
    op.create_index("ix_chapters_project_id", "chapters", ["project_id"])
    op.create_table("scenes", sa.Column("id", sa.String(64), primary_key=True), sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id"), nullable=False), sa.Column("order_index", sa.Integer(), nullable=False), sa.Column("start_offset", sa.Integer(), nullable=False), sa.Column("end_offset", sa.Integer(), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("status", sa.String(32), nullable=False))
    op.create_index("ix_scenes_chapter_id", "scenes", ["chapter_id"])
    op.create_table("segments", sa.Column("id", sa.String(64), primary_key=True), sa.Column("scene_id", sa.String(64), sa.ForeignKey("scenes.id"), nullable=False), sa.Column("order_index", sa.Integer(), nullable=False), sa.Column("text_content", sa.Text(), nullable=False), sa.Column("normalized_text", sa.Text(), nullable=False), sa.Column("segment_type", sa.String(32), nullable=False), sa.Column("speaker_candidate", sa.String(128)), sa.Column("speaker_confidence", sa.Float(), nullable=False), sa.Column("start_offset", sa.Integer(), nullable=False), sa.Column("end_offset", sa.Integer(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False))
    op.create_index("ix_segments_scene_id", "segments", ["scene_id"])
    op.create_table("segment_revisions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id"), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("text_content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_segment_revisions_segment_id", "segment_revisions", ["segment_id"])

def downgrade() -> None:
    op.drop_table("segment_revisions")
    op.drop_table("segments")
    op.drop_table("scenes")
    op.drop_table("chapters")
