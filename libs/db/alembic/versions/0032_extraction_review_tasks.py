"""add extraction confidence tiers and grouped review tasks"""

from alembic import op
import sqlalchemy as sa

revision = "0032_extraction_review_tasks"
down_revision = "0031_orchestrator_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("cause_key", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_tasks_project_id", "review_tasks", ["project_id"])
    op.create_index(
        "ix_review_tasks_project_status", "review_tasks", ["project_id", "status"]
    )
    op.create_index(
        "uq_review_tasks_open_cause",
        "review_tasks",
        ["project_id", "cause_key"],
        unique=True,
        sqlite_where=sa.text("status = 'open'"),
    )

    for table_name in ("chapters", "scenes", "segments"):
        op.add_column(
            table_name,
            sa.Column("auto_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(table_name, sa.Column("decision_tier", sa.String(length=16)))
    op.add_column(
        "segments",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.9"),
    )

    with op.batch_alter_table("speaker_attributions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auto_accepted", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(sa.Column("decision_tier", sa.String(length=16)))
        batch_op.add_column(sa.Column("review_task_id", sa.String(length=64)))
        batch_op.create_foreign_key(
            "fk_speaker_attributions_review_task_id",
            "review_tasks",
            ["review_task_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_speaker_attributions_review_task_id", ["review_task_id"]
        )

    with op.batch_alter_table("issues") as batch_op:
        batch_op.add_column(sa.Column("review_task_id", sa.String(length=64)))
        batch_op.create_foreign_key(
            "fk_issues_review_task_id",
            "review_tasks",
            ["review_task_id"],
            ["id"],
        )
        batch_op.create_index("ix_issues_review_task_id", ["review_task_id"])


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.drop_index("ix_issues_review_task_id")
        batch_op.drop_constraint("fk_issues_review_task_id", type_="foreignkey")
        batch_op.drop_column("review_task_id")

    with op.batch_alter_table("speaker_attributions") as batch_op:
        batch_op.drop_index("ix_speaker_attributions_review_task_id")
        batch_op.drop_constraint(
            "fk_speaker_attributions_review_task_id", type_="foreignkey"
        )
        batch_op.drop_column("review_task_id")
        batch_op.drop_column("decision_tier")
        batch_op.drop_column("auto_accepted")

    for table_name in ("segments", "scenes", "chapters"):
        op.drop_column(table_name, "decision_tier")
        op.drop_column(table_name, "auto_accepted")
    op.drop_column("segments", "confidence")

    op.drop_index("uq_review_tasks_open_cause", table_name="review_tasks")
    op.drop_index("ix_review_tasks_project_status", table_name="review_tasks")
    op.drop_index("ix_review_tasks_project_id", table_name="review_tasks")
    op.drop_table("review_tasks")
