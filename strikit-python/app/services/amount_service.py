"""
Amount Service — THE ONLY place money math happens.

CRITICAL RULES:
1. ALL money values are INTEGER PAISE — never float, never rupees
2. Platform fees come ONLY from backend config — never from client
3. Every function has safety guards against negative/zero/overflow
4. ₹1 = 100 paise. ₹1250 = 125000 paise.

Example:
    User pays ₹1250 (125000 paise)
    Owner share = ₹1200 (120000 paise)
    Platform fee = ₹50 (5000 paise)
"""
from app.config import settings


# ── Backend-authoritative constants (from config.py) ──
PLATFORM_BOOKING_FEE_PAISE: int = settings.PLATFORM_BOOKING_FEE_PAISE    # 5000 = ₹50
PLATFORM_JOIN_FEE_PAISE: int = settings.PLATFORM_JOIN_FEE_PAISE          # 900 = ₹9
SUBSCRIPTION_FEE_PAISE: int = settings.SUBSCRIPTION_FEE_PAISE            # 69900 = ₹699


def calculate_booking_split(owner_price_per_hour_paise: int) -> dict:
    """
    Calculate the payment split for a turf booking.

    Args:
        owner_price_per_hour_paise: Owner's hourly rate in PAISE (from database)

    Returns:
        dict with total_paise, owner_share_paise, platform_fee_paise

    Raises:
        ValueError: If any safety guard fails
    """
    if not isinstance(owner_price_per_hour_paise, int):
        raise TypeError(f"owner_price_per_hour_paise must be int, got {type(owner_price_per_hour_paise)}")

    platform_fee_paise = PLATFORM_BOOKING_FEE_PAISE
    owner_share_paise = owner_price_per_hour_paise
    total_paise = owner_share_paise + platform_fee_paise

    # ── Safety Guards ──
    if owner_share_paise <= 0:
        raise ValueError(f"Owner share must be positive, got {owner_share_paise} paise")
    if platform_fee_paise < 0:
        raise ValueError(f"Platform fee cannot be negative, got {platform_fee_paise} paise")
    if owner_share_paise > total_paise:
        raise ValueError(f"Owner share ({owner_share_paise}) exceeds total ({total_paise})")
    if total_paise > 100_000_00:  # ₹1,00,000 max sanity check
        raise ValueError(f"Total amount suspiciously high: {total_paise} paise (₹{total_paise/100})")

    return {
        "total_paise": total_paise,
        "owner_share_paise": owner_share_paise,
        "platform_fee_paise": platform_fee_paise,
    }


def calculate_multi_slot_split(owner_price_per_hour_paise: int, hours: int) -> dict:
    """Calculate split for multi-hour booking."""
    if hours < 1 or hours > 8:
        raise ValueError(f"Hours must be 1-8, got {hours}")
    owner_share_paise = owner_price_per_hour_paise * hours
    platform_fee_paise = PLATFORM_BOOKING_FEE_PAISE  # Flat fee regardless of hours
    total_paise = owner_share_paise + platform_fee_paise

    if owner_share_paise <= 0:
        raise ValueError(f"Owner share must be positive, got {owner_share_paise} paise")

    return {
        "total_paise": total_paise,
        "owner_share_paise": owner_share_paise,
        "platform_fee_paise": platform_fee_paise,
    }


def validate_payment_amount(razorpay_amount_paise: int, expected_total_paise: int) -> bool:
    """
    Compare Razorpay's reported paid amount against our expected amount.
    Both MUST be integers. Exact match required.
    """
    if not isinstance(razorpay_amount_paise, int) or not isinstance(expected_total_paise, int):
        return False
    return razorpay_amount_paise == expected_total_paise


def validate_payout_amount(owner_share_paise: int, total_paid_paise: int) -> bool:
    """Ensure owner share never exceeds total paid."""
    return 0 < owner_share_paise <= total_paid_paise


def paise_to_rupees(paise: int) -> str:
    """Convert paise (int) to rupees display string. 125000 → '1250.00'"""
    return f"{paise / 100:.2f}"


def rupees_to_paise(rupees: float) -> int:
    """Convert rupees (float from external source) to paise (int). 1250.0 → 125000"""
    return int(round(rupees * 100))


def generate_idempotency_key(booking_id: int, razorpay_payment_id: str, owner_id: int) -> str:
    """Generate a unique idempotency key for payout deduplication."""
    return f"booking_{booking_id}_{razorpay_payment_id}_{owner_id}"


def validate_upi_id(upi_id: str) -> bool:
    """Basic UPI VPA format validation: handle@provider"""
    import re
    if not upi_id or not isinstance(upi_id, str):
        return False
    pattern = r'^[\w.\-]+@[\w]+$'
    return bool(re.match(pattern, upi_id.strip()))
