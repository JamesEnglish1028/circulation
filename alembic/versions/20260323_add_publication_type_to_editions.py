"""Add publication_type to editions for magazine/journal/newspaper distinction

Revision ID: 20260323_publication_type
Revises: b7d9b1a4e2f1
Create Date: 2026-03-23 12:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260323_publication_type"
down_revision = "b7d9b1a4e2f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "editions",
        sa.Column(
            "publication_type",
            sa.Unicode(),
            nullable=True,
            comment="Type of periodical: magazine, journal, newspaper, or periodical",
        ),
    )
    op.create_index(
        op.f("ix_editions_publication_type"),
        "editions",
        ["publication_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_editions_publication_type"), table_name="editions")
    op.drop_column("editions", "publication_type")
