"""add llm provider settings"""

from alembic import op
import sqlalchemy as sa

revision = "0038_llm_settings"
down_revision = "0037_sound_planner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default="ollama"),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("cloud_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("llm_settings")
