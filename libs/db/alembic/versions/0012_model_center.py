"""Add model center installation tracking."""

import sqlalchemy as sa
from alembic import op

revision = "0012_model_center"
down_revision = "0011_production_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_installations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("model_key", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("version", sa.String(200)),
        sa.Column("install_path", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("license_summary", sa.Text()),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_model_installations_model_key", "model_installations", ["model_key"])
    op.create_table(
        "model_install_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("model_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(200)),
        sa.Column("logs_path", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_model_install_jobs_job_id", "model_install_jobs", ["job_id"])
    op.create_index("ix_model_install_jobs_model_key", "model_install_jobs", ["model_key"])


def downgrade() -> None:
    op.drop_index("ix_model_install_jobs_model_key", table_name="model_install_jobs")
    op.drop_index("ix_model_install_jobs_job_id", table_name="model_install_jobs")
    op.drop_table("model_install_jobs")
    op.drop_index("ix_model_installations_model_key", table_name="model_installations")
    op.drop_table("model_installations")
