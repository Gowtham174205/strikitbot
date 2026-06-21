"""
Scheduler: Slot Expiry — Runs every minute.
Releases slots that were reserved but not paid within 15 minutes.
Also sends booking reminders 2 hours before game time (once per booking).
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_
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

                        if not confirmed_booking and slot.status not in ("BLOCKED", "BOOKED"):
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
    """
    Send reminders 2 hours before game time.
    Uses reminderSent flag to ensure each booking only gets ONE reminder.
    """
    try:
        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")

        # Only fetch bookings that are verified AND haven't been reminded yet
        result = await db.execute(
            select(BotBooking).where(
                and_(
                    BotBooking.paymentStatus == "VERIFIED",
                    BotBooking.reminderSent == False,
                )
            )
        )
        bookings = result.scalars().all()

        reminders_sent = 0
        for booking in bookings:
            try:
                slot = await db.get(BotTurfSlot, booking.slotId)
                if not slot or slot.date != today_str:
                    continue

                # Parse slot time to check if game is within 2 hours
                try:
                    # Slot time format: "06:00 AM - 07:00 AM" or "18:00 - 19:00"
                    start_time_str = slot.timeSlot.split("-")[0].strip()

                    # Try 12-hour format first, then 24-hour
                    game_time = None
                    for fmt in ("%I:%M %p", "%H:%M"):
                        try:
                            parsed = datetime.strptime(start_time_str, fmt)
                            game_time = now.replace(
                                hour=parsed.hour,
                                minute=parsed.minute,
                                second=0,
                                microsecond=0,
                            )
                            break
                        except ValueError:
                            continue

                    if not game_time:
                        # Can't parse time — skip this booking
                        continue

                    # Only send reminder if game is 1-3 hours away
                    hours_until_game = (game_time - now).total_seconds() / 3600
                    if hours_until_game < 0 or hours_until_game > 3:
                        continue

                except Exception:
                    # If time parsing fails, send reminder for all today's games
                    pass

                owner = await db.get(BotOwner, slot.ownerId)
                turf_name = owner.turfName if owner else "Unknown"

                await whatsapp_service.send_text(
                    booking.captainPhone,
                    f"🏃 *Game Reminder!* 🏃\n\n"
                    f"Hello {booking.captainName}, your game at *{turf_name}* is today!\n\n"
                    f"• Time: {slot.timeSlot}\n"
                    f"• Team: {booking.teamName}\n\n"
                    f"Have a great game! ⚽\n\n"
                    f"_Powered by STRIKIT_",
                )

                # Mark as reminded — will NOT be sent again
                booking.reminderSent = True
                reminders_sent += 1

            except Exception as e:
                logger.error(f"[Reminder] Error for booking {booking.id}: {e}")

        if reminders_sent > 0:
            await db.commit()
            logger.info(f"[Reminder] Sent {reminders_sent} booking reminders")

    except Exception as e:
        logger.error(f"[Reminder Scheduler] Error: {e}")
