"""add_missing_columns

Revision ID: 435f1063e5c7
Revises: e725ab5d4f07
Create Date: 2026-06-12 08:17:47.657070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '435f1063e5c7'
down_revision: Union[str, None] = 'e725ab5d4f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Add missing columns to BotSession
    if 'BotSession' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('BotSession')]
        if 'language' not in columns:
            op.add_column('BotSession', sa.Column('language', sa.String(), nullable=True))

    # Add missing columns to BotBooking
    if 'BotBooking' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('BotBooking')]
        if 'paymentLinkId' not in columns:
            op.add_column('BotBooking', sa.Column('paymentLinkId', sa.String(), nullable=True))
        if 'razorpayPaymentId' not in columns:
            op.add_column('BotBooking', sa.Column('razorpayPaymentId', sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'BotSession' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('BotSession')]
        if 'language' in columns:
            op.drop_column('BotSession', 'language')

    if 'BotBooking' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('BotBooking')]
        if 'paymentLinkId' in columns:
            op.drop_column('BotBooking', 'paymentLinkId')
        if 'razorpayPaymentId' in columns:
            op.drop_column('BotBooking', 'razorpayPaymentId')

