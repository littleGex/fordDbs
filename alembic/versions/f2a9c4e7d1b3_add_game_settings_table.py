"""Add game_settings table

Revision ID: f2a9c4e7d1b3
Revises: e5f1c8d2a7b4
Create Date: 2026-10-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f2a9c4e7d1b3'
down_revision = 'e5f1c8d2a7b4'
branch_labels = None
depends_on = None


def upgrade():
    # The Ford House game's names, looks and job switches, shared by
    # every family device. A single row, saved with a version check.
    op.create_table(
        'game_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('data', postgresql.JSONB(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table('game_settings')
