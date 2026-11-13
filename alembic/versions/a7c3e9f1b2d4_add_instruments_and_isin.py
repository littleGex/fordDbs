"""Add instruments table and isin on ETF transactions and schedules

Revision ID: a7c3e9f1b2d4
Revises: f2a9c4e7d1b3
Create Date: 2026-11-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e9f1b2d4'
down_revision = 'f2a9c4e7d1b3'
branch_labels = None
depends_on = None

ISIN_TABLES = ('etf_transactions', 'etf_purchase_schedule')


def upgrade():
    # The app's startup create_all() makes new tables (but not new
    # columns), so instruments may already exist if the new code
    # started before this migration ran.
    if not sa.inspect(op.get_bind()).has_table('instruments'):
        op.create_table(
            'instruments',
            sa.Column('isin', sa.String(12), primary_key=True),
            sa.Column('yahoo_ticker', sa.String(), nullable=True),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('currency', sa.String(3), nullable=True),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
            sa.Column('manual_override', sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.Column('resolution_note', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(),
                      server_default=sa.func.now()),
        )

    for table in ISIN_TABLES:
        op.add_column(table, sa.Column('isin', sa.String(12), nullable=True))
        op.create_index(f'ix_{table}_isin', table, ['isin'])
        op.create_foreign_key(f'fk_{table}_isin_instruments', table,
                              'instruments', ['isin'], ['isin'])


def downgrade():
    for table in ISIN_TABLES:
        op.drop_constraint(f'fk_{table}_isin_instruments', table,
                           type_='foreignkey')
        op.drop_index(f'ix_{table}_isin', table_name=table)
        op.drop_column(table, 'isin')
    op.drop_table('instruments')
