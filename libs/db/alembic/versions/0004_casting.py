"""add character casting tables"""

from alembic import op
import sqlalchemy as sa

revision = "0004_casting"
down_revision = "0003_structure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("aliases_json", sa.Text(), nullable=False),
        sa.Column("role_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text()),
    )
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("backend", sa.String(100), nullable=False),
        sa.Column("style_prompt", sa.Text()),
    )
    op.create_table(
        "character_voice_assignments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("character_id", sa.String(64), sa.ForeignKey("characters.id"), unique=True),
        sa.Column("voice_profile_id", sa.String(64), sa.ForeignKey("voice_profiles.id")),
    )
    op.create_table(
        "pronunciation_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("term", sa.String(200), nullable=False),
        sa.Column("phonetic", sa.String(200)),
        sa.Column("replacement_text", sa.String(200)),
    )


def downgrade() -> None:
    op.drop_table("pronunciation_entries")
    op.drop_table("character_voice_assignments")
    op.drop_table("voice_profiles")
    op.drop_table("characters")
