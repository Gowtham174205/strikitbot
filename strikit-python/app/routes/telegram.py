"""
Telegram Bot webhook handler — processes /monthlyreport command and
owner approve/reject callback buttons.
"""
import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.security import verify_telegram_token
from app.middleware.rate_limiter import limiter
from app.models import BotOwner, BotBooking, BotJoinRequest, BotTurfSlot, BotSession
from app.services import telegram_service, whatsapp_service, payment_service
from app.services.pdf_generator import generate_platform_report, generate_revenue_report
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["Telegram"])


@router.post("/telegram", dependencies=[Depends(verify_telegram_token)])
@limiter.limit(settings.RATE_LIMIT_TELEGRAM)
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Main Telegram webhook endpoint."""
    body = await request.json()

    # 1. Handle text commands
    if body.get("message") and body["message"].get("text"):
        text = body["message"]["text"].strip()
        chat_id = str(body["message"]["chat"]["id"])

        if text == "/monthlyreport":
            admin_chat = settings.TELEGRAM_CHAT_ID
            if admin_chat and chat_id != admin_chat:
                await telegram_service.send_message(chat_id, "❌ Unauthorized. Restricted to admin group.")
                return JSONResponse(status_code=200, content={"status": "unauthorized"})

            try:
                await telegram_service.send_message(chat_id, "🔄 Generating monthly platform report...")
                await _trigger_monthly_report(db, previous_month=False)
            except Exception as e:
                logger.error(f"[Telegram] /monthlyreport error: {e}")
                await telegram_service.send_message(chat_id, f"❌ Error: {e}")

            return JSONResponse(status_code=200, content={"status": "report_sent"})

    # 2. Handle callback queries (approve/reject buttons)
    if body.get("callback_query"):
        callback = body["callback_query"]
        data = callback.get("data", "")
        message = callback.get("message", {})
        callback_id = callback.get("id", "")

        owner_id = None
        action = ""

        if data.startswith("verify_approve_"):
            owner_id = int(data.replace("verify_approve_", ""))
            action = "APPROVE"
        elif data.startswith("verify_reject_"):
            owner_id = int(data.replace("verify_reject_", ""))
            action = "REJECT"

        if owner_id and action:
            owner = await db.get(BotOwner, owner_id)
            if not owner:
                await telegram_service.answer_callback_query(callback_id, "Owner not found.")
                return JSONResponse(status_code=200, content={"status": "not_found"})

            if action == "APPROVE":
                owner.verified = True
                owner.subscriptionActive = False
                owner.subscriptionExpiry = None

                sub_link = payment_service.create_subscription_link(owner_id)

                # Update session
                session = (await db.execute(select(BotSession).where(BotSession.phone == owner.mobile))).scalars().first()
                ctx = json.loads(session.context) if session and session.context else {}
                ctx["ownerId"] = owner_id
                if session:
                    session.role = "ONBOARDING"
                    session.state = "AWAITING_SUBSCRIPTION"
                    session.context = json.dumps(ctx)
                else:
                    db.add(BotSession(phone=owner.mobile, role="ONBOARDING", state="AWAITING_SUBSCRIPTION", context=json.dumps(ctx)))

                await db.commit()

                # Edit telegram message
                updated_text = message.get("text", "") + "\n\n✅ <b>Status: APPROVED</b>"
                await telegram_service.edit_message(str(message["chat"]["id"]), message["message_id"], updated_text)

                try:
                    await whatsapp_service.send_text(
                        owner.mobile,
                        f"🎉 *Congratulations {owner.name}! Your STRIKIT Registration has been APPROVED!* 🎉\n\n"
                        f"Your turf *{owner.turfName}* has been verified.\n\n"
                        f"💳 *Subscription Link:* Please pay ₹699 for 3 Months (All features included) to activate:\n{sub_link}\n\n"
                        f"_Powered by STRIKIT_",
                    )
                except Exception as e:
                    logger.error(f"[Telegram Approve] WhatsApp failed: {e}")

                await telegram_service.answer_callback_query(callback_id, "Owner approved successfully!")

            elif action == "REJECT":
                owner.verified = False
                owner.subscriptionActive = False
                await db.commit()

                updated_text = message.get("text", "") + "\n\n❌ <b>Status: REJECTED</b>"
                await telegram_service.edit_message(str(message["chat"]["id"]), message["message_id"], updated_text)

                try:
                    await whatsapp_service.send_text(
                        owner.mobile,
                        f"❌ Hello {owner.name}, your STRIKIT registration for {owner.turfName} was rejected. Please contact support.",
                    )
                except Exception as e:
                    logger.error(f"[Telegram Reject] WhatsApp failed: {e}")

                await telegram_service.answer_callback_query(callback_id, "Owner rejected.")

    return JSONResponse(status_code=200, content={"status": "ok"})


async def _trigger_monthly_report(db: AsyncSession, previous_month: bool = True):
    """Generate and send monthly platform report to Telegram."""
    now = datetime.utcnow()
    if previous_month:
        if now.month == 1:
            start = datetime(now.year - 1, 12, 1)
        else:
            start = datetime(now.year, now.month - 1, 1)
        end = datetime(now.year, now.month, 1)
    else:
        start = datetime(now.year, now.month, 1)
        end = now

    start_str = start.strftime("%Y-%m")

    # Query bookings
    result = await db.execute(
        select(BotBooking).options(
            selectinload(BotBooking.slot).selectinload(BotTurfSlot.owner)
        ).where(BotBooking.createdAt >= start, BotBooking.createdAt <= end)
    )
    bookings = result.scalars().all()

    # Query join requests
    jr_result = await db.execute(
        select(BotJoinRequest).options(
            selectinload(BotJoinRequest.booking)
            .selectinload(BotBooking.slot)
            .selectinload(BotTurfSlot.owner)
        ).where(
            BotJoinRequest.status == "ACCEPTED",
            BotJoinRequest.createdAt >= start,
            BotJoinRequest.createdAt <= end,
        )
    )
    join_requests = jr_result.scalars().all()

    # Generate PDF
    reports_dir = os.path.join(os.getcwd(), "reports")
    pdf_path = generate_platform_report(bookings, join_requests, reports_dir)

    # Send to Telegram
    month_name = start.strftime("%B %Y")
    booking_fee_paise = len(bookings) * settings.PLATFORM_BOOKING_FEE_PAISE
    join_fee_paise = len(join_requests) * settings.PLATFORM_JOIN_FEE_PAISE
    total_paise = booking_fee_paise + join_fee_paise

    from app.services.amount_service import paise_to_rupees
    caption = (
        f"📊 *STRIKIT Platform Revenue Report - {month_name}*\n\n"
        f"• Total Bookings: {len(bookings)} (₹{paise_to_rupees(booking_fee_paise)} fees)\n"
        f"• Total Joins: {len(join_requests)} (₹{paise_to_rupees(join_fee_paise)} fees)\n"
        f"• Net Platform Revenue: ₹{paise_to_rupees(total_paise)}"
    )

    await telegram_service.send_platform_report(pdf_path, caption)
    return pdf_path
