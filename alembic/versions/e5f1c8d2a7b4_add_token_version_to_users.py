"""Add token_version to users

Revision ID: e5f1c8d2a7b4
Revises: d3e8b6a1c5f2
Create Date: 2026-10-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f1c8d2a7b4'
down_revision = 'd3e8b6a1c5f2'
branch_labels = None
depends_on = None


def upgrade():
    # Tokens carry the version they were issued under; bumping it logs a
    # user out everywhere. Existing tokens have no version and count as
    # 0, so nobody is logged out by this migration.
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False,
                  server_default='0')
    )


def downgrade():
    op.drop_column('users', 'token_version')
