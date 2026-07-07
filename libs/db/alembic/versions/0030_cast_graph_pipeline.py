"""Add cast graph mention and decision persistence."""

from alembic import op
import sqlalchemy as sa

revision = "0030_cast_graph_pipeline"
down_revision = "0029_chapter_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(
            sa.Column(
                "relationships_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column(
                "speaking_style_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )

    op.create_table(
        "character_mentions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_document_id", sa.String(length=64), nullable=True),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("window_id", sa.String(length=64), nullable=False),
        sa.Column("surface_name", sa.String(length=200), nullable=False),
        sa.Column("canonical_guess", sa.String(length=200), nullable=True),
        sa.Column("normalized_key", sa.String(length=200), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("role_in_scene", sa.String(length=32), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("segment_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("atom_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("traits_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("relationships_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("llm_run_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_run_id"], ["llm_runs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_mentions_project_id", "character_mentions", ["project_id"])
    op.create_index("ix_character_mentions_scene_id", "character_mentions", ["scene_id"])
    op.create_index("ix_character_mentions_window_id", "character_mentions", ["window_id"])
    op.create_index(
        "ix_character_mentions_normalized_key", "character_mentions", ["normalized_key"]
    )
    op.create_index(
        "ix_character_mentions_source_document_id",
        "character_mentions",
        ["source_document_id"],
    )
    op.create_index("ix_character_mentions_llm_run_id", "character_mentions", ["llm_run_id"])

    op.create_table(
        "cast_graph_decisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("target_character_id", sa.String(length=64), nullable=True),
        sa.Column("target_name", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "evidence_segment_ids_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("llm_run_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_run_id"], ["llm_runs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["target_character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cast_graph_decisions_project_id", "cast_graph_decisions", ["project_id"])
    op.create_index(
        "ix_cast_graph_decisions_source_key",
        "cast_graph_decisions",
        ["project_id", "source_key"],
    )
    op.create_index(
        "ix_cast_graph_decisions_target_character_id",
        "cast_graph_decisions",
        ["target_character_id"],
    )
    op.create_index("ix_cast_graph_decisions_llm_run_id", "cast_graph_decisions", ["llm_run_id"])


def downgrade() -> None:
    op.drop_index("ix_cast_graph_decisions_llm_run_id", table_name="cast_graph_decisions")
    op.drop_index(
        "ix_cast_graph_decisions_target_character_id", table_name="cast_graph_decisions"
    )
    op.drop_index("ix_cast_graph_decisions_source_key", table_name="cast_graph_decisions")
    op.drop_index("ix_cast_graph_decisions_project_id", table_name="cast_graph_decisions")
    op.drop_table("cast_graph_decisions")

    op.drop_index("ix_character_mentions_llm_run_id", table_name="character_mentions")
    op.drop_index(
        "ix_character_mentions_source_document_id", table_name="character_mentions"
    )
    op.drop_index("ix_character_mentions_normalized_key", table_name="character_mentions")
    op.drop_index("ix_character_mentions_window_id", table_name="character_mentions")
    op.drop_index("ix_character_mentions_scene_id", table_name="character_mentions")
    op.drop_index("ix_character_mentions_project_id", table_name="character_mentions")
    op.drop_table("character_mentions")

    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_column("speaking_style_json")
        batch_op.drop_column("relationships_json")
