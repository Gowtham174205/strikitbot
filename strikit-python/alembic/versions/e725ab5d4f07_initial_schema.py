"""Initial schema

Revision ID: e725ab5d4f07
Revises: 
Create Date: 2026-06-11 12:16:06.989349

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e725ab5d4f07'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. BotOwner
    if 'BotOwner' not in existing_tables:
        op.create_table('BotOwner',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('mobile', sa.String(), nullable=False),
        sa.Column('turfName', sa.String(), nullable=False),
        sa.Column('location', sa.String(), nullable=False),
        sa.Column('photoUrls', sa.String(), nullable=False),
        sa.Column('gst', sa.String(), nullable=True),
        sa.Column('msme', sa.String(), nullable=True),
        sa.Column('upiId', sa.String(), nullable=True),
        sa.Column('razorpayContactId', sa.String(), nullable=True),
        sa.Column('razorpayFundAccountId', sa.String(), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=True),
        sa.Column('businessPhone', sa.String(), nullable=True),
        sa.Column('subscriptionActive', sa.Boolean(), nullable=True),
        sa.Column('subscriptionExpiry', sa.DateTime(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.Column('openingTime', sa.String(), nullable=True),
        sa.Column('closingTime', sa.String(), nullable=True),
        sa.Column('pricePerHourPaise', sa.Integer(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('businessPhone'),
        sa.UniqueConstraint('mobile')
        )
    else:
        columns = [c['name'] for c in inspector.get_columns('BotOwner')]
        if 'pricePerHourPaise' not in columns:
            op.add_column('BotOwner', sa.Column('pricePerHourPaise', sa.Integer(), nullable=True))

    # 2. BotSession
    if 'BotSession' not in existing_tables:
        op.create_table('BotSession',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('context', sa.String(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('updatedAt', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone')
        )

    # 3. BotTurfSlot
    if 'BotTurfSlot' not in existing_tables:
        op.create_table('BotTurfSlot',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ownerId', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('timeSlot', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('blockedByOwner', sa.Boolean(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['ownerId'], ['BotOwner.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ownerId', 'date', 'timeSlot', name='uq_owner_date_timeslot')
        )

    # 4. BotBooking
    if 'BotBooking' not in existing_tables:
        op.create_table('BotBooking',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('slotId', sa.Integer(), nullable=False),
        sa.Column('teamName', sa.String(), nullable=False),
        sa.Column('captainName', sa.String(), nullable=False),
        sa.Column('captainPhone', sa.String(), nullable=False),
        sa.Column('paymentLinkId', sa.String(), nullable=True),
        sa.Column('razorpayPaymentId', sa.String(), nullable=True),
        sa.Column('totalPaidPaise', sa.Integer(), nullable=True),
        sa.Column('ownerSharePaise', sa.Integer(), nullable=True),
        sa.Column('platformFeePaise', sa.Integer(), nullable=True),
        sa.Column('paymentStatus', sa.String(), nullable=True),
        sa.Column('payoutStatus', sa.String(), nullable=True),
        sa.Column('confirmedAt', sa.DateTime(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['slotId'], ['BotTurfSlot.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    else:
        columns = [c['name'] for c in inspector.get_columns('BotBooking')]
        if 'totalPaidPaise' not in columns:
            op.add_column('BotBooking', sa.Column('totalPaidPaise', sa.Integer(), nullable=True))
        if 'ownerSharePaise' not in columns:
            op.add_column('BotBooking', sa.Column('ownerSharePaise', sa.Integer(), nullable=True))
        if 'platformFeePaise' not in columns:
            op.add_column('BotBooking', sa.Column('platformFeePaise', sa.Integer(), nullable=True))
        if 'paymentStatus' not in columns:
            op.add_column('BotBooking', sa.Column('paymentStatus', sa.String(), nullable=True))
        if 'payoutStatus' not in columns:
            op.add_column('BotBooking', sa.Column('payoutStatus', sa.String(), nullable=True))
        if 'confirmedAt' not in columns:
            op.add_column('BotBooking', sa.Column('confirmedAt', sa.DateTime(), nullable=True))

    # 5. BotJoinRequest
    if 'BotJoinRequest' not in existing_tables:
        op.create_table('BotJoinRequest',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bookingId', sa.Integer(), nullable=False),
        sa.Column('playerName', sa.String(), nullable=False),
        sa.Column('playerPhone', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('joiningAmount', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bookingId'], ['BotBooking.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 6. BotPaymentAuditLog
    if 'BotPaymentAuditLog' not in existing_tables:
        op.create_table('BotPaymentAuditLog',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bookingId', sa.Integer(), nullable=True),
        sa.Column('eventType', sa.String(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bookingId'], ['BotBooking.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 7. BotPayoutLedger
    if 'BotPayoutLedger' not in existing_tables:
        op.create_table('BotPayoutLedger',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bookingId', sa.Integer(), nullable=False),
        sa.Column('ownerId', sa.Integer(), nullable=False),
        sa.Column('razorpayPaymentId', sa.String(), nullable=False),
        sa.Column('razorpayPayoutId', sa.String(), nullable=True),
        sa.Column('totalPaidPaise', sa.Integer(), nullable=False),
        sa.Column('ownerSharePaise', sa.Integer(), nullable=False),
        sa.Column('platformFeePaise', sa.Integer(), nullable=False),
        sa.Column('ownerUpiId', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('idempotencyKey', sa.String(), nullable=False),
        sa.Column('attemptCount', sa.Integer(), nullable=True),
        sa.Column('failureReason', sa.String(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=True),
        sa.Column('updatedAt', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bookingId'], ['BotBooking.id'], ),
        sa.ForeignKeyConstraint(['ownerId'], ['BotOwner.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotencyKey')
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('BotPayoutLedger')
    op.drop_table('BotPaymentAuditLog')
    op.drop_table('BotJoinRequest')
    op.drop_table('BotBooking')
    op.drop_table('BotTurfSlot')
    op.drop_table('BotSession')
    op.drop_table('BotOwner')
    # ### end Alembic commands ###
