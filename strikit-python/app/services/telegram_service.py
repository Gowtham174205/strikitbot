"""
Telegram Service — Bot API wrapper + payment failure alert functions.
Sends admin notifications, owner verification alerts, and payment-specific alerts.
"""
import httpx
import logging
from app.config import settings
from app.services.amount_service import paise_to_rupees

logger = logging.getLogger(__name__)

# ── Mock store for testing ──
mock_telegram_messages: list[dict] = []


def get_mock_messages() -> list[dict]:
    return mock_telegram_messages


def clear_mock_messages():
    mock_telegram_messages.clear()


def _escape_html(text: str) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _send_telegram_request(method: str, payload: dict) -> dict:
    """Send a request to Telegram Bot API."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        mock_telegram_messages.append(payload)
        logger.info(f"[MOCK TELEGRAM] {payload.get('text', '')[:120]}")
        return {"ok": True, "result": {"message_id": f"tg_mock_{id(payload)}"}}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/{method}",
                json={"chat_id": chat_id, **payload},
            )
            return resp.json()
    except Exception as e:
        logger.error(f"[Telegram API Error] {e}")
        return {"ok": False, "error": str(e)}


async def send_alert(text: str) -> dict:
    """Send a generic admin alert."""
    return await _send_telegram_request("sendMessage", {
        "text": f"🔔 <b>STRIKIT Alert</b>\n\n{_escape_html(text)}",
        "parse_mode": "HTML",
    })


async def send_verification_alert(owner) -> dict:
    """Send new owner verification request with approve/reject buttons."""
    msme_val = _escape_html(owner.msme or 'N/A')
    if owner.msmeCardUrl:
        msme_val = f'<a href="{owner.msmeCardUrl}">Uploaded Certificate</a>'

    util_val = "N/A"
    if owner.utilityBillUrl:
        util_val = f'<a href="{owner.utilityBillUrl}">Uploaded Bill</a>'

    text = (
        f"🆕 <b>New Owner Onboarding</b>\n\n"
        f"<b>Name:</b> {_escape_html(owner.name)}\n"
        f"<b>Phone:</b> {_escape_html(owner.mobile)}\n"
        f"<b>Turf:</b> {_escape_html(owner.turfName)}\n"
        f"<b>Location:</b> {_escape_html(owner.location)}\n"
        f"<b>Photos:</b> {_escape_html(owner.photoUrls)}\n"
        f"<b>GST:</b> {_escape_html(owner.gst or 'N/A')}\n"
        f"<b>MSME:</b> {msme_val}\n"
        f"<b>Utility Bill:</b> {util_val}\n\n"
        f"Please verify details and action below:"
    )
    return await _send_telegram_request("sendMessage", {
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Approve Owner", "callback_data": f"verify_approve_{owner.id}"},
                {"text": "❌ Reject Owner", "callback_data": f"verify_reject_{owner.id}"},
            ]]
        },
    })


# ══════════════════════════════════════════════════════════════════
# PAYMENT-SPECIFIC ALERTS (NEW — for payment hardening)
# ══════════════════════════════════════════════════════════════════


async def send_payout_failed_alert(
    owner_name: str, turf_name: str, amount_paise: int, booking_id: int, reason: str
) -> dict:
    """🔴 Alert when RazorpayX payout fails."""
    text = (
        f"🔴 <b>PAYOUT FAILED</b>\n\n"
        f"<b>Booking ID:</b> {booking_id}\n"
        f"<b>Owner:</b> {_escape_html(owner_name)}\n"
        f"<b>Turf:</b> {_escape_html(turf_name)}\n"
        f"<b>Amount:</b> ₹{paise_to_rupees(amount_paise)}\n"
        f"<b>Reason:</b> {_escape_html(reason)}\n\n"
        f"⚠️ Manual retry required from admin dashboard."
    )
    return await _send_telegram_request("sendMessage", {"text": text, "parse_mode": "HTML"})


async def send_amount_mismatch_alert(
    booking_id: int, expected_paise: int, actual_paise: int, razorpay_payment_id: str
) -> dict:
    """🟠 Alert when paid amount doesn't match expected amount."""
    text = (
        f"🟠 <b>AMOUNT MISMATCH</b>\n\n"
        f"<b>Booking ID:</b> {booking_id}\n"
        f"<b>Expected:</b> ₹{paise_to_rupees(expected_paise)} ({expected_paise} paise)\n"
        f"<b>Received:</b> ₹{paise_to_rupees(actual_paise)} ({actual_paise} paise)\n"
        f"<b>Razorpay Payment ID:</b> {razorpay_payment_id}\n\n"
        f"⚠️ Payout blocked. Marked for MANUAL_REVIEW."
    )
    return await _send_telegram_request("sendMessage", {"text": text, "parse_mode": "HTML"})


async def send_duplicate_payout_blocked_alert(booking_id: int, idempotency_key: str) -> dict:
    """🟡 Alert when duplicate payout attempt is blocked."""
    text = (
        f"🟡 <b>DUPLICATE PAYOUT BLOCKED</b>\n\n"
        f"<b>Booking ID:</b> {booking_id}\n"
        f"<b>Idempotency Key:</b> {_escape_html(idempotency_key)}\n\n"
        f"ℹ️ Existing payout already exists. No action needed."
    )
    return await _send_telegram_request("sendMessage", {"text": text, "parse_mode": "HTML"})


async def send_manual_review_alert(
    booking_id: int, reason: str, owner_name: str, turf_name: str
) -> dict:
    """🟠 Alert when booking/payout requires manual developer review."""
    text = (
        f"🟠 <b>MANUAL REVIEW REQUIRED</b>\n\n"
        f"<b>Booking ID:</b> {booking_id}\n"
        f"<b>Owner:</b> {_escape_html(owner_name)}\n"
        f"<b>Turf:</b> {_escape_html(turf_name)}\n"
        f"<b>Reason:</b> {_escape_html(reason)}\n\n"
        f"⚠️ Please investigate and take manual action."
    )
    return await _send_telegram_request("sendMessage", {"text": text, "parse_mode": "HTML"})


async def send_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> dict:
    """Send a text message to a specific Telegram chat."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.info(f"[MOCK TELEGRAM → {chat_id}] {text[:100]}")
        return {"ok": True}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            return resp.json()
    except Exception as e:
        logger.error(f"[Telegram sendMessage Error] {e}")
        return {"ok": False}


async def edit_message(chat_id: str, message_id: int, text: str) -> dict:
    """Edit an existing Telegram message and remove inline keyboard."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.info(f"[MOCK TELEGRAM EDIT: Chat {chat_id}, Msg {message_id}]")
        return {"ok": True}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": []},
                },
            )
            return resp.json()
    except Exception as e:
        logger.error(f"[Telegram editMessage Error] {e}")
        return {"ok": False}


async def answer_callback_query(callback_query_id: str, text: str) -> dict:
    """Answer a Telegram inline button callback."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return {"ok": True}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )
            return resp.json()
    except Exception as e:
        logger.error(f"[Telegram answerCallback Error] {e}")
        return {"ok": False}


async def send_platform_report(pdf_path: str, caption: str) -> dict:
    """Send a PDF document to the admin Telegram chat."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        mock_telegram_messages.append({"document": pdf_path, "caption": caption})
        logger.info(f"[MOCK TELEGRAM DOC] {pdf_path}")
        return {"ok": True}

    try:
        import os
        async with httpx.AsyncClient(timeout=60) as client:
            with open(pdf_path, "rb") as f:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                    files={"document": (os.path.basename(pdf_path), f, "application/pdf")},
                )
                return resp.json()
    except Exception as e:
        logger.error(f"[Telegram sendDocument Error] {e}")
        return {"ok": False, "error": str(e)}


async def send_cancellation_alert(
    booking_id: int,
    owner_name: str,
    turf_name: str,
    refund_amount_paise: int,
    refund_percentage: int,
    reason: str,
) -> dict:
    """Alert admin when a booking is cancelled."""
    text = (
        f"⚠️ <b>BOOKING CANCELLED</b>\n\n"
        f"<b>Booking ID:</b> {booking_id}\n"
        f"<b>Owner:</b> {_escape_html(owner_name)}\n"
        f"<b>Turf:</b> {_escape_html(turf_name)}\n"
        f"<b>Refund Percentage:</b> {refund_percentage}%\n"
        f"<b>Refund Amount:</b> ₹{paise_to_rupees(refund_amount_paise)}\n"
        f"<b>Reason:</b> {_escape_html(reason)}\n\n"
        f"ℹ️ The turf slot has been released back to AVAILABLE status."
    )
    return await _send_telegram_request("sendMessage", {"text": text, "parse_mode": "HTML"})

