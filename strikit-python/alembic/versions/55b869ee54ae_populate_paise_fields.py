"""populate_paise_fields

Revision ID: 55b869ee54ae
Revises: 435f1063e5c7
Create Date: 2026-06-12 08:40:07.779847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55b869ee54ae'
down_revision: Union[str, None] = '435f1063e5c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update BotOwner pricePerHourPaise
    op.execute(
        'UPDATE "BotOwner" SET "pricePerHourPaise" = CAST("pricePerHour" * 100 AS INTEGER) '
        'WHERE "pricePerHourPaise" IS NULL AND "pricePerHour" IS NOT NULL'
    )
    op.execute(
        'UPDATE "BotOwner" SET "pricePerHourPaise" = 100000 '
        'WHERE "pricePerHourPaise" IS NULL'
    )

    # 2. Update BotBooking totalPaidPaise, platformFeePaise, ownerSharePaise
    op.execute(
        'UPDATE "BotBooking" SET "totalPaidPaise" = CAST("amountPaid" * 100 AS INTEGER) '
        'WHERE "totalPaidPaise" IS NULL AND "amountPaid" IS NOT NULL'
    )
    op.execute(
        'UPDATE "BotBooking" SET "totalPaidPaise" = 0 '
        'WHERE "totalPaidPaise" IS NULL'
    )
    op.execute(
        'UPDATE "BotBooking" SET "platformFeePaise" = CASE WHEN "totalPaidPaise" >= 5000 THEN 5000 ELSE 0 END '
        'WHERE "platformFeePaise" IS NULL'
    )
    op.execute(
        'UPDATE "BotBooking" SET "ownerSharePaise" = "totalPaidPaise" - "platformFeePaise" '
        'WHERE "ownerSharePaise" IS NULL'
    )

    # 3. Copy old payment IDs to new columns if missing
    op.execute(
        'UPDATE "BotBooking" SET "razorpayPaymentId" = "paymentId" '
        'WHERE "razorpayPaymentId" IS NULL AND "paymentId" IS NOT NULL'
    )
    op.execute(
        'UPDATE "BotBooking" SET "paymentLinkId" = "paymentId" '
        'WHERE "paymentLinkId" IS NULL AND "paymentId" IS NOT NULL'
    )


def downgrade() -> None:
    pass

