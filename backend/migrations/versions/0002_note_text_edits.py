"""Keep user corrections separate from the generated note content."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notes", sa.Column("text_edits", sa.JSON, nullable=False, server_default=sa.text("'{}'"))
    )


def downgrade():
    op.drop_column("notes", "text_edits")
