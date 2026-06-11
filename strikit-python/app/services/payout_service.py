"""
Payout Service — RazorpayX UPI payout execution. HARDENED.

CRITICAL RULES:
1. Accepts amountPaise (int) — never Float
2. No Math.round(amount * 100) — amount is ALREADY in paise
3. Validates UPI ID format before attempting payout
4. Returns MANUAL_REVIEW on validation failure instead of throwing
5. Caches Razorpay contactId and fundAccountId on BotOwner
"""
import httpx
import base64
import logging
from app.config import settings
from app.services.amount_service import validate_upi_id

logger = logging.getLogger(__name__)


def _auth_header() -> str:
    """Generate Basic auth header for RazorpayX API."""
    creds = f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}"
    return f"Basic {base64.b64encode(creds.encode()).decode()}"


async def create_contact(name: str, mobile: str, reference_id: str) -> str:
    """Create a RazorpayX contact for payout."""
    if not settings.razorpayx_configured:
        logger.info(f"[Payout] MOCK contact creation for {name}")
        return f"cont_mock_{hash(name) % 100000}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.razorpay.com/v1/contacts",
                json={
                    "name": name,
                    "contact": mobile.replace(" ", "")[-10:],  # Last 10 digits
                    "type": "vendor",
                    "reference_id": str(reference_id),
                },
                headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()["id"]
    except Exception as e:
        logger.error(f"[Payout] Contact creation failed: {e}")
        raise


async def create_fund_account(contact_id: str, upi_id: str) -> str:
    """Create a VPA (UPI) fund account in RazorpayX."""
    if not settings.razorpayx_configured:
        logger.info(f"[Payout] MOCK fund account for UPI: {upi_id}")
        return f"fa_mock_{hash(upi_id) % 100000}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.razorpay.com/v1/fund_accounts",
                json={
                    "contact_id": contact_id,
                    "account_type": "vpa",
                    "vpa": {"address": upi_id.strip()},
                },
                headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()["id"]
    except Exception as e:
        logger.error(f"[Payout] Fund account creation failed: {e}")
        raise


async def execute_payout(
    owner,
    amount_paise: int,
    booking_id: int,
    db_session=None,
) -> dict:
    """
    Execute a UPI payout to owner via RazorpayX.

    Args:
        owner: BotOwner ORM object (with id, name, mobile, upiId, razorpayContactId, etc.)
        amount_paise: Owner's share in INTEGER PAISE (not rupees!)
        booking_id: Booking ID for reference
        db_session: Optional async DB session for caching contact/fund account IDs

    Returns:
        dict with payoutId, status, simulated, reason (if failed/manual_review)
    """
    logger.info(
        f"[Payout] Initiating ₹{amount_paise / 100:.2f} payout to "
        f"owner {owner.name} (UPI: {owner.upiId})"
    )

    # ── Safety Guard: Validate UPI ID ──
    if not owner.upiId or not validate_upi_id(owner.upiId):
        logger.warning(f"[Payout] Invalid UPI ID for owner {owner.id}: '{owner.upiId}'")
        return {
            "payoutId": None,
            "status": "MANUAL_REVIEW",
            "simulated": False,
            "reason": f"Invalid or missing UPI ID: '{owner.upiId}'",
        }

    # ── Safety Guard: Amount must be positive integer ──
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        return {
            "payoutId": None,
            "status": "MANUAL_REVIEW",
            "simulated": False,
            "reason": f"Invalid payout amount: {amount_paise} paise",
        }

    # ── Mock mode ──
    if not settings.razorpayx_configured:
        logger.info(f"[Payout] MOCK payout of ₹{amount_paise / 100:.2f} to UPI: {owner.upiId}")
        return {
            "payoutId": f"pout_mock_{hash(str(booking_id)) % 100000}",
            "status": "processed",
            "simulated": True,
        }

    try:
        # 1. Create/cache Contact
        contact_id = owner.razorpayContactId
        if not contact_id:
            logger.info(f"[Payout] Creating contact for owner {owner.id}")
            contact_id = await create_contact(
                name=owner.name,
                mobile=owner.mobile,
                reference_id=f"owner_{owner.id}",
            )
            if db_session:
                owner.razorpayContactId = contact_id
                await db_session.commit()

        # 2. Create/cache Fund Account
        fund_account_id = owner.razorpayFundAccountId
        if not fund_account_id:
            logger.info(f"[Payout] Creating fund account for owner {owner.id}")
            try:
                fund_account_id = await create_fund_account(contact_id, owner.upiId)
                if db_session:
                    owner.razorpayFundAccountId = fund_account_id
                    await db_session.commit()
            except Exception as fa_err:
                logger.error(f"[Payout] Fund account creation failed: {fa_err}")
                return {
                    "payoutId": None,
                    "status": "MANUAL_REVIEW",
                    "simulated": False,
                    "reason": f"Fund account creation failed: {fa_err}",
                }

        # 3. Execute RazorpayX Payout
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.razorpay.com/v1/payouts",
                json={
                    "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
                    "fund_account_id": fund_account_id,
                    "amount": amount_paise,  # Already in paise — NO conversion!
                    "currency": "INR",
                    "mode": "UPI",
                    "purpose": "vendor bill",
                    "queue_if_low_balance": True,
                    "reference_id": f"booking_{booking_id}",
                },
                headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info(f"[Payout] Success. Payout ID: {data['id']}, Status: {data['status']}")
        return {
            "payoutId": data["id"],
            "status": data["status"],
            "simulated": False,
        }

    except Exception as e:
        logger.error(f"[Payout] Execution failed: {e}")
        return {
            "payoutId": None,
            "status": "FAILED",
            "simulated": False,
            "reason": str(e),
        }
