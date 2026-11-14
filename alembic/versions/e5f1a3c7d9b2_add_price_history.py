"""Add price history cache for the portfolio history chart

Revision ID: e5f1a3c7d9b2
Revises: c4d8e2a6f0b1
Create Date: 2026-11-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f1a3c7d9b2'
down_revision = 'c4d8e2a6f0b1'
branch_labels = None
depends_on = None


def upgrade():
    # The app's startup create_all() may already have made these tables
    # if the new code started before this migration ran.
    existing = sa.inspect(op.get_bind())
    if not existing.has_table('price_history'):
        op.create_table(
            'price_history',
            sa.Column('ticker', sa.String(), primary_key=True),
            sa.Column('day', sa.Date(), primary_key=True),
            sa.Column('close', sa.Numeric(14, 6), nullable=False),
            sa.Column('fetched_at', sa.DateTime(),
                      server_default=sa.func.now()),
        )
    if not existing.has_table('price_fetch_state'):
        op.create_table(
            'price_fetch_state',
            sa.Column('ticker', sa.String(), primary_key=True),
            sa.Column('fetched_from', sa.Date(), nullable=False),
            sa.Column('fetched_through', sa.Date(), nullable=False),
        )


def downgrade():
    op.drop_table('price_fetch_state')
    op.drop_table('price_history')
