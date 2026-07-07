"""Add orchestrator checkpoint, cache, and event tables."""

from alembic import op
import sqlalchemy as sa

revision = "0031_orchestrator_tables"
down_revision = "0030_cast_graph_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_checkpoints",
        sa.Column("unit_key", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("stage_version", sa.String(length=64), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("output_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("unit_key"),
    )
    op.create_index("ix_job_checkpoints_job_id", "job_checkpoints", ["job_id"])
    op.create_index("ix_job_checkpoints_project_id", "job_checkpoints", ["project_id"])
    op.create_index(
        "ix_job_checkpoints_job_stage_status",
        "job_checkpoints",
        ["job_id", "stage", "status"],
    )

    op.create_table(
        "inference_cache",
        sa.Column("cache_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=True),
        sa.Column("schema_id", sa.String(length=128), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("value_path", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("cache_key"),
    )
    op.create_index("ix_inference_cache_kind", "inference_cache", ["kind"])

    op.create_table(
        "job_events",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=True),
        sa.Column("scope_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_index("ix_job_events_project_id", "job_events", ["project_id"])
    op.create_index("ix_job_events_job_event_id", "job_events", ["job_id", "event_id"])


def downgrade() -> None:
    op.drop_index("ix_job_events_job_event_id", table_name="job_events")
    op.drop_index("ix_job_events_project_id", table_name="job_events")
    op.drop_index("ix_job_events_job_id", table_name="job_events")
    op.drop_table("job_events")

    op.drop_index("ix_inference_cache_kind", table_name="inference_cache")
    op.drop_table("inference_cache")

    op.drop_index("ix_job_checkpoints_job_stage_status", table_name="job_checkpoints")
    op.drop_index("ix_job_checkpoints_project_id", table_name="job_checkpoints")
    op.drop_index("ix_job_checkpoints_job_id", table_name="job_checkpoints")
    op.drop_table("job_checkpoints")
