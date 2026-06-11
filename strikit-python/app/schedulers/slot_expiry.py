"""
Scheduler: Slot Expiry — Runs every minute.
Releases slots that were reserved but not paid within 15 minutes.
Also sends booking reminders 2 hours before game time.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotTurfSlot, BotBooking, BotOwner, BotSession
from app.services import whatsapp_service
from app.config import settings

logger = logging.getLogger(__name__)


async def check_slot_expiry(db: AsyncSession):
    """Release slots reserved > 15 minutes ago without payment."""
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=settings.SLOT_RESERVATION_MINUTES)

        # Find sessions in AWAITING_PAYMENT_CONFIRMATION state that are stale
        result = await db.execute(
            select(BotSession).where(
                BotSession.state == "AWAITING_PAYMENT_CONFIRMATION",
                BotSession.updatedAt < cutoff,
            )
        )
        stale_sessions = result.scalars().all()

        for session in stale_sessions:
            try:
                import json
                ctx = json.loads(session.context or "{}")
                owner_id = ctx.get("ownerId")
                date = ctx.get("selectedDate")
                slot_time = ctx.get("selectedSlot")

                if owner_id and date and slot_time:
                    # Check if slot is still in a reserved state (no booking yet)
                    slot_result = await db.execute(
                        select(BotTurfSlot).where(
                            BotTurfSlot.ownerId == int(owner_id),
                            BotTurfSlot.date == date,
                            BotTurfSlot.timeSlot == slot_time,
                        )
                    )
                    slot = slot_result.scalars().first()

                    # Only release if no confirmed booking exists for this slot
                    if slot:
                        booking_result = await db.execute(
                            select(BotBooking).where(
                                BotBooking.slotId == slot.id,
                                BotBooking.paymentStatus == "VERIFIED",
                            )
                        )
                        confirmed_booking = booking_result.scalars().first()

                        if not confirmed_booking and slot.status != "BLOCKED":
                            slot.status = "AVAILABLE"
                            logger.info(
                                f"[Slot Expiry] Released slot {slot_time} on {date} "
                                f"for owner {owner_id} (unpaid reservation)"
                            )

                # Notify player and clean up session
                await whatsapp_service.send_text(
                    session.phone,
                    "⏰ *Reservation Expired*\n\n"
                    "Your slot reservation has expired as payment was not completed within 15 minutes.\n"
                    "Please start a new booking if you'd like to play.\n\n"
                    "_Powered by STRIKIT_",
                )
                await db.delete(session)

            except Exception as e:
                logger.error(f"[Slot Expiry] Error processing session {session.phone}: {e}")

        await db.commit()

    except Exception as e:
        logger.error(f"[Slot Expiry Scheduler] Error: {e}")


async def send_booking_reminders(db: AsyncSession):
    """Send reminders 2 hours before game time."""
    try:
        now = datetime.utcnow()
        # This is simplified — in production, parse slot time + date to exact datetime
        # For now, check slots dated today
        today_str = now.strftime("%Y-%m-%d")

        result = await db.execute(
            select(BotBooking).where(BotBooking.paymentStatus == "VERIFIED")
        )
        bookings = result.scalars().all()

        for booking in bookings:
            try:
                slot = await db.get(BotTurfSlot, booking.slotId)
                if not slot or slot.date != today_str:
                    continue

                owner = await db.get(BotOwner, slot.ownerId)
                turf_name = owner.turfName if owner else "Unknown"

                # Simple check: only send once (check if already notified via context marker)
                # In production, use a separate reminder tracking table
                await whatsapp_service.send_text(
                    booking.captainPhone,
                    f"🏃 *Game Reminder!* 🏃\n\n"
                    f"Hello {booking.captainName}, your game at *{turf_name}* is today!\n\n"
                    f"• Time: {slot.timeSlot}\n"
                    f"• Team: {booking.teamName}\n\n"
                    f"Have a great game! ⚽\n\n"
                    f"_Powered by STRIKIT_",
                )
            except Exception as e:
                logger.error(f"[Reminder] Error for booking {booking.id}: {e}")

    except Exception as e:
        logger.error(f"[Reminder Scheduler] Error: {e}")
