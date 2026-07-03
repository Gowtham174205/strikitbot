"""
Scheduler: Monthly Report Generation
Runs hourly, checks if the previous month's report has been sent.
"""
import os
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotOwner, BotBooking, BotTurfSlot, BotJoinRequest
from app.services import telegram_service, whatsapp_service
from app.services.pdf_generator import generate_platform_report, generate_revenue_report
from app.services.amount_service import paise_to_rupees
from app.config import settings

logger = logging.getLogger(__name__)

MARKER_FILE = os.path.join("reports", ".last_sent_monthly_report.txt")


async def check_and_send_monthly_report(db: AsyncSession):
    """Check if monthly report needs to be sent, generate and send if needed."""
    try:
        now = datetime.utcnow()
        if now.month == 1:
            prev_month_date = datetime(now.year - 1, 12, 1)
        else:
            prev_month_date = datetime(now.year, now.month - 1, 1)

        target_month_str = prev_month_date.strftime("%Y-%m")

        # Check marker
        last_sent = ""
        if os.path.exists(MARKER_FILE):
            with open(MARKER_FILE, "r") as f:
                last_sent = f.read().strip()

        if last_sent == target_month_str:
            return  # Already sent

        logger.info(f"[Scheduler] Generating monthly report for {target_month_str}")

        # Query bookings for previous month
        start = prev_month_date
        if now.month == 1:
            end = datetime(now.year, 1, 1)
        else:
            end = datetime(now.year, now.month, 1)

        bookings_result = await db.execute(
            select(BotBooking).options(
                selectinload(BotBooking.slot).selectinload(BotTurfSlot.owner)
            ).where(
                BotBooking.paymentStatus == "VERIFIED",
                BotBooking.createdAt >= start,
                BotBooking.createdAt < end,
            )
        )
        bookings = bookings_result.scalars().all()

        joins_result = await db.execute(
            select(BotJoinRequest).options(
                selectinload(BotJoinRequest.booking)
                .selectinload(BotBooking.slot)
                .selectinload(BotTurfSlot.owner)
            ).where(
                BotJoinRequest.status == "ACCEPTED",
                BotJoinRequest.createdAt >= start,
                BotJoinRequest.createdAt < end,
            )
        )
        join_requests = joins_result.scalars().all()

        # Generate platform report
        reports_dir = os.path.join(os.getcwd(), "reports")
        pdf_path = generate_platform_report(bookings, join_requests, reports_dir)

        # Send to Telegram
        booking_fees = sum(b.platformFeePaise for b in bookings)
        join_fees = len(join_requests) * settings.PLATFORM_JOIN_FEE_PAISE
        total = booking_fees + join_fees

        caption = (
            f"📊 *STRIKIT Platform Report - {prev_month_date.strftime('%B %Y')}*\n\n"
            f"• Bookings: {len(bookings)} (₹{paise_to_rupees(booking_fees)})\n"
            f"• Joins: {len(join_requests)} (₹{paise_to_rupees(join_fees)})\n"
            f"• Net Revenue: ₹{paise_to_rupees(total)}"
        )
        await telegram_service.send_platform_report(pdf_path, caption)

        # Send individual owner reports
        owners_result = await db.execute(
            select(BotOwner).where(
                BotOwner.verified == True,
                BotOwner.subscriptionActive == True,
                BotOwner.subscriptionPlan != "BASIC",
            )
        )
        active_owners = owners_result.scalars().all()

        for owner in active_owners:
            try:
                # Get owner's bookings via slots
                slots_result = await db.execute(
                    select(BotTurfSlot).where(BotTurfSlot.ownerId == owner.id)
                )
                owner_slots = slots_result.scalars().all()
                slot_ids = [s.id for s in owner_slots]

                if slot_ids:
                    owner_bookings_result = await db.execute(
                        select(BotBooking).options(
                            selectinload(BotBooking.slot)
                        ).where(
                            BotBooking.slotId.in_(slot_ids),
                            BotBooking.paymentStatus == "VERIFIED",
                            BotBooking.createdAt >= start,
                            BotBooking.createdAt < end,
                        )
                    )
                    owner_bookings = owner_bookings_result.scalars().all()
                else:
                    owner_bookings = []

                if owner_bookings:
                    owner_pdf = generate_revenue_report(owner, owner_bookings, reports_dir)
                    base_url = settings.BASE_URL if hasattr(settings, 'BASE_URL') and settings.BASE_URL else 'https://bot.strikit.in'
                    await whatsapp_service.send_document(
                        owner.mobile,
                        f"{base_url}/reports/{os.path.basename(owner_pdf)}",
                        f"monthly_report_{target_month_str}.pdf",
                        f"📅 *Monthly Revenue Report for {target_month_str}*\n\n"
                        f"Hello {owner.name}, here is your monthly report for *{owner.turfName}*.\n\n"
                        f"_Powered by STRIKIT_",
                    )
            except Exception as e:
                logger.error(f"[Scheduler] Owner report error for {owner.name}: {e}")

        # Mark as sent
        os.makedirs("reports", exist_ok=True)
        with open(MARKER_FILE, "w") as f:
            f.write(target_month_str)

        logger.info(f"[Scheduler] Monthly report for {target_month_str} sent and marked.")

    except Exception as e:
        logger.error(f"[Scheduler] Monthly report error: {e}")
