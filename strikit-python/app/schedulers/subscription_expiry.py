"""
Scheduler: Subscription Expiry — Runs hourly.
1. Send 3-day renewal reminder to owners expiring soon.
2. Deactivate expired subscriptions and notify owners.
3. Churn detection: remind inactive owners/players.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotOwner
from app.services import whatsapp_service, payment_service
from app.config import settings

logger = logging.getLogger(__name__)


async def check_subscription_expiry(db: AsyncSession):
    """Check and handle subscription expirations."""
    try:
        now = datetime.utcnow()

        # ── 1. Send 3-day reminder ──
        reminder_start = now + timedelta(hours=71)
        reminder_end = now + timedelta(hours=72)

        result = await db.execute(
            select(BotOwner).where(
                BotOwner.subscriptionActive == True,
                BotOwner.subscriptionExpiry >= reminder_start,
                BotOwner.subscriptionExpiry <= reminder_end,
            )
        )
        owners_to_remind = result.scalars().all()

        for owner in owners_to_remind:
            try:
                sub_link = payment_service.create_subscription_link(owner.id)
                await whatsapp_service.send_text(
                    owner.mobile,
                    f"⏰ *STRIKIT Subscription Renewal Reminder* ⏰\n\n"
                    f"Dear {owner.name}, your subscription for *{owner.turfName}* will expire in 3 days.\n\n"
                    f"🔗 *Payment Link:* {sub_link}\n\n"
                    f"_Powered by STRIKIT_",
                )
                logger.info(f"[Subscription] 3-day reminder sent to {owner.mobile}")
            except Exception as e:
                logger.error(f"[Subscription] Reminder failed for {owner.mobile}: {e}")

        # ── 2. Deactivate expired subscriptions ──
        expired_result = await db.execute(
            select(BotOwner).where(
                BotOwner.subscriptionActive == True,
                BotOwner.subscriptionExpiry < now,
            )
        )
        expired_owners = expired_result.scalars().all()

        for owner in expired_owners:
            logger.info(f"[Subscription] Deactivating expired sub for owner {owner.id} ({owner.name})")
            owner.subscriptionActive = False

            try:
                sub_link = payment_service.create_subscription_link(owner.id)
                await whatsapp_service.send_text(
                    owner.mobile,
                    f"⚠️ *STRIKIT Subscription Expired* ⚠️\n\n"
                    f"Dear {owner.name}, your subscription for *{owner.turfName}* has expired.\n\n"
                    f"To keep your booking bot active, please renew: ₹699.00\n"
                    f"🔗 *Payment Link:* {sub_link}\n\n"
                    f"_Powered by STRIKIT_",
                )
            except Exception as e:
                logger.error(f"[Subscription] Expiry notification failed for {owner.mobile}: {e}")

        await db.commit()

        # ── 3. Churn detection: 7-day inactive owners ──
        seven_days_ago = now - timedelta(days=7)
        inactive_result = await db.execute(
            select(BotOwner).where(
                BotOwner.verified == True,
                BotOwner.subscriptionActive == False,
                BotOwner.subscriptionExpiry < seven_days_ago,
                BotOwner.subscriptionExpiry != None,
            )
        )
        inactive_owners = inactive_result.scalars().all()

        for owner in inactive_owners:
            try:
                sub_link = payment_service.create_subscription_link(owner.id)
                await whatsapp_service.send_text(
                    owner.mobile,
                    f"👋 *We miss you, {owner.name}!*\n\n"
                    f"Your turf *{owner.turfName}* hasn't been active on STRIKIT for a while.\n\n"
                    f"Renew your subscription to start receiving bookings again:\n"
                    f"🔗 {sub_link}\n\n"
                    f"_Powered by STRIKIT_",
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[Subscription Scheduler] Error: {e}")
