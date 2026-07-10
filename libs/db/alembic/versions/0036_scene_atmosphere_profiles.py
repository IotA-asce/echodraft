"""add scene atmosphere profiles"""

from alembic import op
import sqlalchemy as sa

revision = "0036_scene_atmosphere_profiles"
down_revision = "0035_casting_assignment_locks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenes",
        sa.Column("atmosphere_profile_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("scenes", "atmosphere_profile_json")
