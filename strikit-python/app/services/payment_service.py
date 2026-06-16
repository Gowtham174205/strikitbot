"""
Payment Service — Razorpay payment link creation.
All amounts passed as INTEGER PAISE. No Float-to-paise conversion happens here.
"""
import logging
from app.config import settings
from app.services.amount_service import paise_to_rupees

logger = logging.getLogger(__name__)

_razorpay_client = None


def _get_razorpay():
    """Lazy-init Razorpay client."""
    global _razorpay_client
    if _razorpay_client is None and settings.razorpay_configured:
        import razorpay
        _razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return _razorpay_client


def create_subscription_link(owner_id: int, amount_paise: int = 69900, plan_name: str = "TRIAL") -> str:
    """
    Create a Razorpay payment link for owner subscription.
    Amount is in PAISE.
    """
    client = _get_razorpay()
    if not client:
        logger.info(f"[PaymentService] Mock subscription link for owner {owner_id} with plan {plan_name}")
        return f"http://razorpay.mock/sub/{owner_id}/{plan_name}"

    try:
        link = client.payment_link.create({
            "amount": amount_paise,  # Already in paise!
            "currency": "INR",
            "accept_partial": False,
            "description": f"STRIKIT Turf Booking Bot {plan_name} Subscription (Owner ID: {owner_id})",
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {
                "type": "subscription",
                "ownerId": str(owner_id),
                "plan": plan_name,
            },
            "callback_url": "https://bot.strikit.in/payment-success",
            "callback_method": "get",
        })
        return link["short_url"]
    except Exception as e:
        logger.error(f"[PaymentService] Subscription link error for owner {owner_id} and plan {plan_name}: {e}")
        raise


def create_booking_link(
    phone: str,
    owner_id: int,
    date: str,
    slot_time: str,
    captain_name: str,
    team_name: str,
    total_amount_paise: int,
    sport: str = "",
) -> str:
    """
    Create a Razorpay payment link for a turf booking.
    total_amount_paise = ownerShare + platformFee (already calculated by amount_service).
    """
    client = _get_razorpay()
    if not client:
        logger.info(f"[PaymentService] Mock booking link for slot {slot_time} on {date}")
        return (
            f"http://razorpay.mock/pay?slot={slot_time}&date={date}"
            f"&owner={owner_id}&phone={phone}&amount_paise={total_amount_paise}&sport={sport}"
        )

    try:
        link = client.payment_link.create({
            "amount": total_amount_paise,  # Already in paise! No Math.round needed.
            "currency": "INR",
            "accept_partial": False,
            "description": f"Turf Booking Fee for slot {slot_time} on {date}",
            "customer": {
                "contact": phone if phone.startswith("+") else f"+{phone}",
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {
                "type": "booking",
                "phone": str(phone),
                "ownerId": str(owner_id),
                "date": str(date),
                "slotTime": str(slot_time),
                "captainName": str(captain_name),
                "teamName": str(team_name),
                "sport": str(sport),
                # Store expected amount in paise for cross-verification on webhook
                "expectedTotalPaise": str(total_amount_paise),
            },
            "callback_url": "https://bot.strikit.in/payment-success",
            "callback_method": "get",
        })
        return link["short_url"]
    except Exception as e:
        logger.error(f"[PaymentService] Booking link error: {e}")
        raise


def create_join_request_link(
    request_id: int,
    phone: str,
    amount_paise: int = None,
) -> str:
    """Create a payment link for ₹9 player join request platform fee."""
    if amount_paise is None:
        amount_paise = settings.PLATFORM_JOIN_FEE_PAISE  # 900

    client = _get_razorpay()
    if not client:
        logger.info(f"[PaymentService] Mock join link for request {request_id}")
        return f"http://razorpay.mock/joinpay?id={request_id}&phone={phone}"

    try:
        link = client.payment_link.create({
            "amount": amount_paise,  # Already in paise!
            "currency": "INR",
            "accept_partial": False,
            "description": f"STRIKIT Player Join Request Platform Fee (Request ID: {request_id})",
            "customer": {
                "contact": phone if phone.startswith("+") else f"+{phone}",
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {
                "type": "join_request",
                "requestId": str(request_id),
                "phone": str(phone),
            },
            "callback_url": "https://bot.strikit.in/payment-success",
            "callback_method": "get",
        })
        return link["short_url"]
    except Exception as e:
        logger.error(f"[PaymentService] Join request link error: {e}")
        raise
