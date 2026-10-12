"""Immutable scenario rules; legacy scenarios retain soft deadlines."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scenarios",
        sa.Column("must_finish_job_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("scenarios", "must_finish_job_ids")
