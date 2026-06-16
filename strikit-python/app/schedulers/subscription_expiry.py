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
                await whatsapp_service.send_buttons(
                    owner.mobile,
                    f"⏰ *STRIKIT Subscription Renewal Reminder* ⏰\n\n"
                    f"Dear {owner.name}, your subscription for *{owner.turfName}* will expire in 3 days.\n\n"
                    f"Please select a subscription plan below to renew:",
                    [
                        {"id": "sub_plan_basic", "title": "₹199 Basic (1 Month)"},
                        {"id": "sub_plan_premium", "title": "₹399 Premium (1 Month)"},
                        {"id": "sub_plan_prem3m", "title": "₹749 Premium (3 Month)"},
                    ]
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
                await whatsapp_service.send_buttons(
                    owner.mobile,
                    f"⚠️ *STRIKIT Subscription Expired* ⚠️\n\n"
                    f"Dear {owner.name}, your subscription for *{owner.turfName}* has expired.\n\n"
                    f"To keep your booking bot active, please select a plan below to renew:",
                    [
                        {"id": "sub_plan_basic", "title": "₹199 Basic (1 Month)"},
                        {"id": "sub_plan_premium", "title": "₹399 Premium (1 Month)"},
                        {"id": "sub_plan_prem3m", "title": "₹749 Premium (3 Month)"},
                    ]
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
                await whatsapp_service.send_buttons(
                    owner.mobile,
                    f"👋 *We miss you, {owner.name}!*\n\n"
                    f"Your turf *{owner.turfName}* hasn't been active on STRIKIT for a while.\n\n"
                    f"Please choose a plan below to renew and reactivate bookings:",
                    [
                        {"id": "sub_plan_basic", "title": "₹199 Basic (1 Month)"},
                        {"id": "sub_plan_premium", "title": "₹399 Premium (1 Month)"},
                        {"id": "sub_plan_prem3m", "title": "₹749 Premium (3 Month)"},
                    ]
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[Subscription Scheduler] Error: {e}")
