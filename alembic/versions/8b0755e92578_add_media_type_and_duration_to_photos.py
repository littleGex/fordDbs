"""Add media_type and duration_seconds to Photo

Revision ID: 8b0755e92578
Revises: 26a815029608
Create Date: 2026-08-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b0755e92578'
down_revision = '26a815029608'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'photos',
        sa.Column('media_type', sa.String(), nullable=False,
                  server_default='image')
    )
    op.add_column(
        'photos',
        sa.Column('duration_seconds', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('photos', 'duration_seconds')
    op.drop_column('photos', 'media_type')
