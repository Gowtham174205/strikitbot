"""add_cancellation_fields

Revision ID: e2b10a5bcf41
Revises: 961d0ec5bd76
Create Date: 2026-06-22 06:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2b10a5bcf41'
down_revision: Union[str, None] = '961d0ec5bd76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('BotBooking', sa.Column('status', sa.String(), nullable=False, server_default='CONFIRMED'))
    op.add_column('BotBooking', sa.Column('cancellationReason', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('BotBooking', 'status')
    op.drop_column('BotBooking', 'cancellationReason')
