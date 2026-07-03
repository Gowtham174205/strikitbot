"""add_bank_details_columns

Revision ID: a1b2c3d4e5f6
Revises: 48e68e0d1260
Create Date: 2026-07-03 12:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '48e68e0d1260'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add IFSC code and account number columns to BotOwner
    op.add_column('BotOwner', sa.Column('ifscCode', sa.String(), nullable=True))
    op.add_column('BotOwner', sa.Column('accountNumber', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('BotOwner', 'accountNumber')
    op.drop_column('BotOwner', 'ifscCode')
