"""Add export packages."""

import sqlalchemy as sa
from alembic import op

revision = "0010_exports"
down_revision = "0009_ambience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_packages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id")),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("export_packages")
