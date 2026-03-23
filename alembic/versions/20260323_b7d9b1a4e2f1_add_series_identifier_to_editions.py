"""Add series_identifier to editions

Revision ID: b7d9b1a4e2f1
Revises: a5ee359c2d31
Create Date: 2026-03-23 00:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d9b1a4e2f1"
down_revision = "a5ee359c2d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("editions", sa.Column("series_identifier", sa.Unicode(), nullable=True))
    op.create_index(
        op.f("ix_editions_series_identifier"),
        "editions",
        ["series_identifier"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_editions_series_identifier"), table_name="editions")
    op.drop_column("editions", "series_identifier")
