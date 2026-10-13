"""Add status to users

Revision ID: c7d1a2f4b9e0
Revises: 441b8e33aa67
Create Date: 2026-10-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d1a2f4b9e0'
down_revision = '441b8e33aa67'
branch_labels = None
depends_on = None


def upgrade():
    # Everyone who already has an account stays able to log in; only
    # new self-registrations start out as 'pending'.
    op.add_column(
        'users',
        sa.Column('status', sa.String(), nullable=False,
                  server_default='active')
    )


def downgrade():
    op.drop_column('users', 'status')
