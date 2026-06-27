"""Add speaker attribution records."""

import sqlalchemy as sa
from alembic import op

revision = "0018_speaker_attributions"
down_revision = "0017_character_bible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "speaker_attributions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("segment_id", sa.String(64), sa.ForeignKey("segments.id")),
        sa.Column("character_id", sa.String(64), sa.ForeignKey("characters.id")),
        sa.Column("speaker_name", sa.String(200)),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("user_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_speaker_attributions_project_id", "speaker_attributions", ["project_id"])
    op.create_index("ix_speaker_attributions_segment_id", "speaker_attributions", ["segment_id"], unique=True)
    op.create_index("ix_speaker_attributions_character_id", "speaker_attributions", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_speaker_attributions_character_id", table_name="speaker_attributions")
    op.drop_index("ix_speaker_attributions_segment_id", table_name="speaker_attributions")
    op.drop_index("ix_speaker_attributions_project_id", table_name="speaker_attributions")
    op.drop_table("speaker_attributions")
