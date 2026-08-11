"""Convert Wish.cost from Float to Numeric(10, 2)

Revision ID: 824ea1ae3c03
Revises: 8b0755e92578
Create Date: 2026-08-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '824ea1ae3c03'
down_revision = '8b0755e92578'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'wishes', 'cost',
        existing_type=sa.Float(),
        type_=sa.Numeric(10, 2),
        postgresql_using='cost::numeric(10,2)',
    )


def downgrade():
    op.alter_column(
        'wishes', 'cost',
        existing_type=sa.Numeric(10, 2),
        type_=sa.Float(),
    )
