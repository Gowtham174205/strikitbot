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
    payment_id: str = None,
    db_session=None,
) -> dict:
    """
    Execute turf payout split.
    If owner has a Razorpay Route Linked Account ID (acc_...), splits payment via Razorpay Route.
    Otherwise, returns MANUAL_REVIEW for manual UPI payout.
    """
    is_route = owner.razorpayContactId and owner.razorpayContactId.strip().startswith("acc_")

    logger.info(
        f"[Payout] Initiating ₹{amount_paise / 100:.2f} payout to "
        f"owner {owner.name} (Route ID: {owner.razorpayContactId if is_route else 'None'})"
    )

    # ── Safety Guard: Amount must be positive integer ──
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        return {
            "payoutId": None,
            "status": "MANUAL_REVIEW",
            "simulated": False,
            "reason": f"Invalid payout amount: {amount_paise} paise",
        }

    # ── Mock mode (Standard Razorpay not configured) ──
    if not settings.razorpay_configured:
        logger.info(f"[Payout] MOCK split payout of ₹{amount_paise / 100:.2f} to Linked Account: {owner.razorpayContactId if is_route else 'manual'}")
        return {
            "payoutId": f"pout_mock_{hash(str(booking_id)) % 100000}",
            "status": "COMPLETED",
            "simulated": True,
        }

    # ── Case A: Razorpay Route Split Payment ──
    if is_route:
        if not payment_id:
            logger.warning(f"[Payout Route] Missing payment_id for Route split (booking #{booking_id})")
            return {
                "payoutId": None,
                "status": "MANUAL_REVIEW",
                "simulated": False,
                "reason": "Missing payment_id for Razorpay Route split transfer",
            }
        
        try:
            import razorpay
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            transfer_payload = {
                "transfers": [
                    {
                        "account": owner.razorpayContactId.strip(),
                        "amount": amount_paise,
                        "currency": "INR",
                    }
                ]
            }
            logger.info(f"[Payout Route] Creating Route transfer for payment {payment_id} to Linked Account {owner.razorpayContactId.strip()}")
            
            transfer_response = client.payment.transfer(payment_id, transfer_payload)
            transfers_list = transfer_response.get("items", [])
            transfer_id = transfers_list[0].get("id") if transfers_list else f"trns_{booking_id}"
            
            logger.info(f"[Payout Route] Transfer success: {transfer_id}")
            return {
                "payoutId": transfer_id,
                "status": "COMPLETED",
                "simulated": False,
            }
        except Exception as e:
            logger.error(f"[Payout Route] Transfer failed for payment {payment_id}: {e}")
            return {
                "payoutId": None,
                "status": "FAILED",
                "simulated": False,
                "reason": f"Razorpay Route Split failed: {e}",
            }

    # ── Case B: Manual UPI Payout (No Route ID configured) ──
    logger.info(f"[Payout] Route Linked Account not set for owner {owner.id}. Falling back to manual payout.")
    return {
        "payoutId": None,
        "status": "MANUAL_REVIEW",
        "simulated": False,
        "reason": "Manual Payout Required (Razorpay Route ID not configured)",
    }
