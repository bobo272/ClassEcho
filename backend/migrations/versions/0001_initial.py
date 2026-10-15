"""Initial local schema; usage ledger survives material deletion."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "courses",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=False),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_table(
        "lectures",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("course_id", sa.String, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("sha256", sa.String, nullable=False),
        sa.Column("duration", sa.Float, nullable=False),
        sa.Column("media_suffix", sa.String, nullable=False),
        sa.Column("active_transcript_id", sa.String),
        sa.Column("is_demo", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_table(
        "transcripts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("lecture_id", sa.String, sa.ForeignKey("lectures.id"), nullable=False),
        sa.Column("parent_id", sa.String),
        sa.Column("engine", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("revision", sa.String, nullable=False),
        sa.Column("segments", sa.JSON, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("lecture_id", sa.String, sa.ForeignKey("lectures.id"), nullable=False),
        sa.Column("transcript_id", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("prompt_version", sa.String, nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("user_markdown", sa.String),
        sa.Column("edit_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("lecture_id", sa.String, sa.ForeignKey("lectures.id"), nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("parameters", sa.JSON, nullable=False),
        sa.Column("checkpoint", sa.JSON, nullable=False),
        sa.Column("error", sa.String),
        sa.Column("result_id", sa.String),
        sa.Column("created_at", sa.String, nullable=False),
        sa.Column("updated_at", sa.String, nullable=False),
    )
    op.create_table(
        "usage_records",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("job_id", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("reserved_cny", sa.Float, nullable=False),
        sa.Column("actual_cny", sa.Float),
        sa.Column("billing_state", sa.String, nullable=False),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_table(
        "bookmarks",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("lecture_id", sa.String, sa.ForeignKey("lectures.id"), nullable=False),
        sa.Column("position_ms", sa.Integer, nullable=False),
        sa.Column("question", sa.String, nullable=False),
        sa.Column("created_at", sa.String, nullable=False),
    )
    for table, column in [
        ("lectures", "course_id"),
        ("transcripts", "lecture_id"),
        ("notes", "lecture_id"),
        ("jobs", "lecture_id"),
        ("usage_records", "job_id"),
        ("bookmarks", "lecture_id"),
    ]:
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in (
        "bookmarks",
        "usage_records",
        "jobs",
        "notes",
        "transcripts",
        "lectures",
        "courses",
    ):
        op.drop_table(table)
