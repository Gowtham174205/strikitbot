"""
Payment Split Safety Tests — 6 Critical test cases.
Tests the amount_service to ensure:
1. Paise-only math (no float)
2. Correct split calculation
3. Amount validation
4. Idempotency key generation
5. Overflow/underflow guards
6. UPI validation
"""
import pytest
from app.services.amount_service import (
    calculate_booking_split,
    calculate_multi_slot_split,
    validate_payment_amount,
    validate_payout_amount,
    paise_to_rupees,
    rupees_to_paise,
    generate_idempotency_key,
    validate_upi_id,
    PLATFORM_BOOKING_FEE_PAISE,
)


class TestBookingSplit:
    """Test calculate_booking_split — the core money math."""

    def test_standard_split(self):
        """₹1000/hr owner rate → Total ₹1050, Owner ₹1000, Fee ₹50"""
        result = calculate_booking_split(100000)  # 100000 paise = ₹1000
        assert result["total_paise"] == 105000      # 100000 + 5000
        assert result["owner_share_paise"] == 100000
        assert result["platform_fee_paise"] == 5000
        assert isinstance(result["total_paise"], int)
        assert isinstance(result["owner_share_paise"], int)
        assert isinstance(result["platform_fee_paise"], int)

    def test_budget_turf_split(self):
        """₹500/hr → Total ₹550, Owner ₹500, Fee ₹50"""
        result = calculate_booking_split(50000)
        assert result["total_paise"] == 55000
        assert result["owner_share_paise"] == 50000
        assert result["platform_fee_paise"] == 5000

    def test_premium_turf_split(self):
        """₹3000/hr → Total ₹3050, Owner ₹3000, Fee ₹50"""
        result = calculate_booking_split(300000)
        assert result["total_paise"] == 305000
        assert result["owner_share_paise"] == 300000
        assert result["platform_fee_paise"] == 5000

    def test_owner_share_never_exceeds_total(self):
        """Owner share must always be <= total paid."""
        result = calculate_booking_split(120000)
        assert result["owner_share_paise"] <= result["total_paise"]

    def test_zero_owner_price_raises(self):
        """Zero owner price must raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            calculate_booking_split(0)

    def test_negative_owner_price_raises(self):
        """Negative owner price must raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            calculate_booking_split(-100)

    def test_float_input_raises_type_error(self):
        """Float input must raise TypeError — enforce integer only."""
        with pytest.raises(TypeError, match="int"):
            calculate_booking_split(1000.50)

    def test_suspiciously_high_amount_raises(self):
        """₹1,00,001+ should trigger overflow guard."""
        with pytest.raises(ValueError, match="suspiciously high"):
            calculate_booking_split(10_000_100)  # >₹1,00,000


class TestMultiSlotSplit:
    """Test multi-hour booking split."""

    def test_2_hour_booking(self):
        """₹1000/hr × 2hr → Total ₹2050, Owner ₹2000, Fee ₹50"""
        result = calculate_multi_slot_split(100000, 2)
        assert result["total_paise"] == 205000
        assert result["owner_share_paise"] == 200000
        assert result["platform_fee_paise"] == 5000  # Flat fee

    def test_3_hour_booking(self):
        result = calculate_multi_slot_split(100000, 3)
        assert result["total_paise"] == 305000
        assert result["owner_share_paise"] == 300000

    def test_invalid_hours(self):
        with pytest.raises(ValueError, match="1-8"):
            calculate_multi_slot_split(100000, 0)
        with pytest.raises(ValueError, match="1-8"):
            calculate_multi_slot_split(100000, 10)


class TestAmountValidation:
    """Test validate_payment_amount — exact match required."""

    def test_exact_match(self):
        assert validate_payment_amount(105000, 105000) is True

    def test_mismatch_1_paisa(self):
        """Even 1 paisa difference must fail."""
        assert validate_payment_amount(105001, 105000) is False

    def test_mismatch_extra_zero(self):
        """The classic extra-zero bug: 1050000 vs 105000."""
        assert validate_payment_amount(1050000, 105000) is False

    def test_none_input(self):
        assert validate_payment_amount(None, 105000) is False

    def test_float_input(self):
        assert validate_payment_amount(1050.00, 105000) is False


class TestPayoutValidation:
    """Test validate_payout_amount — owner share <= total."""

    def test_valid_payout(self):
        assert validate_payout_amount(100000, 105000) is True

    def test_payout_equals_total(self):
        """Edge: owner gets 100% (no fee) — still valid."""
        assert validate_payout_amount(100000, 100000) is True

    def test_payout_exceeds_total(self):
        """CRITICAL: Must fail — prevents money loss."""
        assert validate_payout_amount(200000, 105000) is False

    def test_zero_payout(self):
        assert validate_payout_amount(0, 105000) is False

    def test_negative_payout(self):
        assert validate_payout_amount(-5000, 105000) is False


class TestPaiseConversion:
    """Test paise <-> rupees conversion."""

    def test_paise_to_rupees(self):
        assert paise_to_rupees(125000) == "1250.00"
        assert paise_to_rupees(5000) == "50.00"
        assert paise_to_rupees(900) == "9.00"
        assert paise_to_rupees(0) == "0.00"
        assert paise_to_rupees(1) == "0.01"

    def test_rupees_to_paise(self):
        assert rupees_to_paise(1250.0) == 125000
        assert rupees_to_paise(50.0) == 5000
        assert rupees_to_paise(9.0) == 900
        assert rupees_to_paise(0.01) == 1


class TestIdempotencyKey:
    """Test idempotency key generation."""

    def test_key_format(self):
        key = generate_idempotency_key(42, "pay_abc123", 7)
        assert key == "booking_42_pay_abc123_7"

    def test_unique_keys(self):
        key1 = generate_idempotency_key(1, "pay_aaa", 1)
        key2 = generate_idempotency_key(1, "pay_bbb", 1)
        key3 = generate_idempotency_key(2, "pay_aaa", 1)
        assert key1 != key2
        assert key1 != key3


class TestUPIValidation:
    """Test UPI VPA format validation."""

    def test_valid_upi(self):
        assert validate_upi_id("john@upi") is True
        assert validate_upi_id("turf.owner@oksbi") is True
        assert validate_upi_id("9876543210@paytm") is True

    def test_invalid_upi(self):
        assert validate_upi_id("") is False
        assert validate_upi_id(None) is False
        assert validate_upi_id("noemailformat.com") is False
        assert validate_upi_id("@upi") is False
