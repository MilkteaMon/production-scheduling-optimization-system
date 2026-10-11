"""Presentation metadata; job inputs and calculated results remain immutable."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "datasets", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="0")
    )
    op.add_column(
        "datasets", sa.Column("is_test", sa.Boolean(), nullable=False, server_default="0")
    )
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE datasets SET is_test = 1 WHERE name LIKE 'Browser verification%'")
    )
    # The pre-release browser CSV fixture was imported under the default name.
    # Match its exact data hash and cutoff, leaving later user imports untouched.
    fixture = [
        {
            "job_id": "A",
            "processing_time_min": 3,
            "release_time_min": 0,
            "due_time_min": 2,
            "priority_weight": 1,
        },
        {
            "job_id": "B",
            "processing_time_min": 2,
            "release_time_min": 0,
            "due_time_min": 2,
            "priority_weight": 3,
        },
    ]
    digest = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()
    connection.execute(
        sa.text(
            "UPDATE datasets SET is_test = 1 WHERE name = :name AND source_kind = 'csv' AND job_hash = :hash AND created_at < :cutoff"
        ),
        {
            "name": "Synthetic production demo",
            "hash": digest,
            "cutoff": "2026-10-11T15:27:10+00:00",
        },
    )


def downgrade():
    op.drop_column("datasets", "is_test")
    op.drop_column("datasets", "is_archived")
