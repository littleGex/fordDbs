"""Add game_key to children and users, birth_date to users

Revision ID: d3e8b6a1c5f2
Revises: c7d1a2f4b9e0
Create Date: 2026-10-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3e8b6a1c5f2'
down_revision = 'c7d1a2f4b9e0'
branch_labels = None
depends_on = None


def upgrade():
    # Which Ford House game player each person is ('girl', 'boy', 'mum',
    # 'dad'). Children already have a birth_date; parents need one too.
    op.add_column('children',
                  sa.Column('game_key', sa.String(), nullable=True))
    op.add_column('users',
                  sa.Column('game_key', sa.String(), nullable=True))
    op.add_column('users',
                  sa.Column('birth_date', sa.Date(), nullable=True))
    op.create_unique_constraint('uq_children_game_key', 'children',
                                ['game_key'])
    op.create_unique_constraint('uq_users_game_key', 'users', ['game_key'])


def downgrade():
    op.drop_constraint('uq_users_game_key', 'users', type_='unique')
    op.drop_constraint('uq_children_game_key', 'children', type_='unique')
    op.drop_column('users', 'birth_date')
    op.drop_column('users', 'game_key')
    op.drop_column('children', 'game_key')
