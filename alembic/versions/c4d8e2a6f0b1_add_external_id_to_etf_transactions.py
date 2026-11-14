"""Add external_id to ETF transactions for import dedupe

Revision ID: c4d8e2a6f0b1
Revises: a7c3e9f1b2d4
Create Date: 2026-11-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d8e2a6f0b1'
down_revision = 'a7c3e9f1b2d4'
branch_labels = None
depends_on = None

CONSTRAINT = 'uq_etf_transactions_external_id'


def upgrade():
    # Trade Republic transaction_id (or liquidation:<ISIN>) of an
    # imported row; unique so a re-import skips stored rows.
    op.add_column('etf_transactions',
                  sa.Column('external_id', sa.String(), nullable=True))
    op.create_unique_constraint(CONSTRAINT, 'etf_transactions',
                                ['external_id'])


def downgrade():
    op.drop_constraint(CONSTRAINT, 'etf_transactions', type_='unique')
    op.drop_column('etf_transactions', 'external_id')
