"""add direction profiles"""

from alembic import op
import sqlalchemy as sa

revision = "0005_direction"
down_revision = "0004_casting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "direction_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_direction_scope", "direction_profiles", ["scope_type", "scope_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("direction_profiles")
