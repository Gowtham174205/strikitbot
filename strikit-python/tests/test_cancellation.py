import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import BotOwner, BotBooking, BotTurfSlot, BotSession, BotPayoutLedger, BotPaymentAuditLog
from app.services.whatsapp_service import mock_sent_messages, clear_mock_messages as clear_wa
from app.services.telegram_service import mock_telegram_messages, clear_mock_messages as clear_tg
from tests.test_full_flow import send_whatsapp_msg, assert_wa_message_contains


def get_slot_time_str(offset_hours: int) -> tuple[str, str]:
    target_time = datetime.utcnow() + timedelta(hours=offset_hours)
    date_str = target_time.strftime("%Y-%m-%d")
    hour = target_time.hour
    
    am_pm = "AM" if hour < 12 else "PM"
    hour_12 = hour if hour <= 12 else hour - 12
    if hour_12 == 0:
        hour_12 = 12
    
    # e.g. "06:00 PM - 07:00 PM"
    time_slot = f"{hour_12:02d}:00 {am_pm} - {(hour_12 % 12) + 1:02d}:00 {am_pm}"
    return date_str, time_slot


@pytest.mark.asyncio
async def test_booking_cancellation_full_refund(client, db_session):
    """Test full refund (> 4 hours before slot time) with pre-defined reason."""
    clear_wa()
    clear_tg()

    # Setup player session with state that doesn't trigger any interceptor
    session = BotSession(
        phone="919999999999",
        role="CUSTOMER",
        state="PLAYER_DASHBOARD",
        context="{}",
    )
    db_session.add(session)

    # 1. Setup mock owner, slot, and verified booking
    owner = BotOwner(
        name="Test Owner",
        mobile="919000000000",
        turfName="Standard Arena",
        location="Chennai",
        photoUrls="http://photo.url",
        verified=True,
        subscriptionActive=True,
        pricePerHourPaise=100000, # Rs. 1000
    )
    db_session.add(owner)
    await db_session.flush()

    # Set slot time 6 hours in the future
    date_str, slot_time = get_slot_time_str(6)
    slot = BotTurfSlot(
        ownerId=owner.id,
        date=date_str,
        timeSlot=slot_time,
        status="BOOKED",
    )
    db_session.add(slot)
    await db_session.flush()

    booking = BotBooking(
        slotId=slot.id,
        teamName="Avengers",
        captainName="Tony",
        captainPhone="919999999999",
        totalPaidPaise=110000, # Rs. 1100 (1000 turf + 100 fee)
        ownerSharePaise=100000,
        platformFeePaise=100000,
        paymentStatus="VERIFIED",
        razorpayPaymentId="pay_mock_12345",
        status="CONFIRMED",
    )
    db_session.add(booking)
    await db_session.flush()

    ledger = BotPayoutLedger(
        bookingId=booking.id,
        ownerId=owner.id,
        razorpayPaymentId="pay_mock_12345",
        totalPaidPaise=110000,
        ownerSharePaise=100000,
        platformFeePaise=100000,
        ownerUpiId="owner@upi",
        status="PROCESSING",
        idempotencyKey="idemp_123",
    )
    db_session.add(ledger)
    await db_session.commit()

    # 2. View "My Bookings" - should list the booking and show cancellation list option
    await send_whatsapp_msg(client, "919999999999", "mybookings")
    assert_wa_message_contains("919999999999", "Your Recent Bookings")
    assert_wa_message_contains("919999999999", "Booking Cancellation")

    # 3. Simulate selecting the booking to cancel
    await send_whatsapp_msg(client, "919999999999", f"cancel_select_{booking.id}")
    assert_wa_message_contains("919999999999", "Please select the reason for cancellation")
    assert_wa_message_contains("919999999999", "Change of plans")

    # 4. Simulate choosing a pre-defined reason (Plans)
    await send_whatsapp_msg(client, "919999999999", f"cancel_reason_{booking.id}_plans")
    assert_wa_message_contains("919999999999", "Booking Cancelled Successfully")
    assert_wa_message_contains("919999999999", "Refund Amount: *₹880.00 (80% refund)*")

    # 5. Verify database updates
    await db_session.refresh(booking)
    await db_session.refresh(slot)
    await db_session.refresh(ledger)

    assert booking.status == "CANCELLED"
    assert booking.cancellationReason == "Change of plans"
    assert booking.paymentStatus == "REFUNDED"
    assert slot.status == "AVAILABLE"
    assert ledger.status == "CANCELLED"

    # Verify audit logs
    stmt = select(BotPaymentAuditLog).where(BotPaymentAuditLog.bookingId == booking.id)
    logs = (await db_session.execute(stmt)).scalars().all()
    assert any(log.eventType == "CANCEL_INITIATED" for log in logs)
    assert any(log.eventType == "REFUND_COMPLETED" for log in logs)


@pytest.mark.asyncio
async def test_booking_cancellation_partial_refund(client, db_session):
    """Test partial refund (3 hours before slot time) with pre-defined reason."""
    clear_wa()
    clear_tg()

    # Setup player session
    session = BotSession(
        phone="919999999999",
        role="CUSTOMER",
        state="PLAYER_START",
        context="{}",
    )
    db_session.add(session)

    # Setup mock owner, slot, and verified booking
    owner = BotOwner(
        name="Test Owner",
        mobile="919000000000",
        turfName="Arena 2",
        location="Chennai",
        photoUrls="http://photo.url",
        verified=True,
        subscriptionActive=True,
        pricePerHourPaise=100000,
    )
    db_session.add(owner)
    await db_session.flush()

    # Set slot time 3 hours in the future (2 to 4 hour window)
    date_str, slot_time = get_slot_time_str(3)
    slot = BotTurfSlot(
        ownerId=owner.id,
        date=date_str,
        timeSlot=slot_time,
        status="BOOKED",
    )
    db_session.add(slot)
    await db_session.flush()

    booking = BotBooking(
        slotId=slot.id,
        teamName="Avengers",
        captainName="Tony",
        captainPhone="919999999999",
        totalPaidPaise=110000,
        ownerSharePaise=100000,
        platformFeePaise=100000,
        paymentStatus="VERIFIED",
        razorpayPaymentId="pay_mock_5678",
        status="CONFIRMED",
    )
    db_session.add(booking)
    await db_session.commit()

    # Simulate choosing pre-defined reason directly
    await send_whatsapp_msg(client, "919999999999", f"cancel_reason_{booking.id}_weather")
    assert_wa_message_contains("919999999999", "Booking Cancelled Successfully")
    assert_wa_message_contains("919999999999", "Refund Amount: *₹550.00 (50% refund)*")

    # Verify db updates
    await db_session.refresh(booking)
    await db_session.refresh(slot)
    assert booking.status == "CANCELLED"
    assert booking.cancellationReason == "Weather conditions"
    assert booking.paymentStatus == "REFUNDED"
    assert slot.status == "AVAILABLE"


@pytest.mark.asyncio
async def test_booking_cancellation_no_refund(client, db_session):
    """Test no refund (1 hour before slot time)."""
    clear_wa()
    clear_tg()

    # Setup player session
    session = BotSession(
        phone="919999999999",
        role="CUSTOMER",
        state="PLAYER_START",
        context="{}",
    )
    db_session.add(session)

    # Setup mock owner, slot, and verified booking
    owner = BotOwner(
        name="Test Owner",
        mobile="919000000000",
        turfName="Arena 3",
        location="Chennai",
        photoUrls="http://photo.url",
        verified=True,
        subscriptionActive=True,
        pricePerHourPaise=100000,
    )
    db_session.add(owner)
    await db_session.flush()

    # Set slot time 1 hour in the future (< 2 hour window)
    date_str, slot_time = get_slot_time_str(1)
    slot = BotTurfSlot(
        ownerId=owner.id,
        date=date_str,
        timeSlot=slot_time,
        status="BOOKED",
    )
    db_session.add(slot)
    await db_session.flush()

    booking = BotBooking(
        slotId=slot.id,
        teamName="Avengers",
        captainName="Tony",
        captainPhone="919999999999",
        totalPaidPaise=110000,
        ownerSharePaise=100000,
        platformFeePaise=100000,
        paymentStatus="VERIFIED",
        razorpayPaymentId="pay_mock_9999",
        status="CONFIRMED",
    )
    db_session.add(booking)
    await db_session.commit()

    # Cancel
    await send_whatsapp_msg(client, "919999999999", f"cancel_reason_{booking.id}_injury")
    assert_wa_message_contains("919999999999", "Booking Cancelled Successfully")
    assert_wa_message_contains("919999999999", "No refund (cancelled less than 2 hours")

    # Verify db updates
    await db_session.refresh(booking)
    await db_session.refresh(slot)
    assert booking.status == "CANCELLED"
    assert booking.cancellationReason == "Injured player(s)"
    assert booking.paymentStatus == "VERIFIED" # Kept verified because no refund was processed
    assert slot.status == "AVAILABLE"


@pytest.mark.asyncio
async def test_booking_cancellation_custom_reason(client, db_session):
    """Test custom reason flow ('Other')."""
    clear_wa()
    clear_tg()

    # Setup player session
    session = BotSession(
        phone="919999999999",
        role="CUSTOMER",
        state="PLAYER_START",
        context="{}",
    )
    db_session.add(session)

    # Setup mock owner, slot, and verified booking
    owner = BotOwner(
        name="Test Owner",
        mobile="919000000000",
        turfName="Arena 4",
        location="Chennai",
        photoUrls="http://photo.url",
        verified=True,
        subscriptionActive=True,
        pricePerHourPaise=100000,
    )
    db_session.add(owner)
    await db_session.flush()

    # Set slot time 5 hours in the future (> 4 hour window)
    date_str, slot_time = get_slot_time_str(5)
    slot = BotTurfSlot(
        ownerId=owner.id,
        date=date_str,
        timeSlot=slot_time,
        status="BOOKED",
    )
    db_session.add(slot)
    await db_session.flush()

    booking = BotBooking(
        slotId=slot.id,
        teamName="Avengers",
        captainName="Tony",
        captainPhone="919999999999",
        totalPaidPaise=110000,
        ownerSharePaise=100000,
        platformFeePaise=100000,
        paymentStatus="VERIFIED",
        razorpayPaymentId="pay_mock_custom",
        status="CONFIRMED",
    )
    db_session.add(booking)
    await db_session.commit()

    # 1. Trigger 'other' option
    await send_whatsapp_msg(client, "919999999999", f"cancel_reason_{booking.id}_other")
    assert_wa_message_contains("919999999999", "Please type the reason for cancelling your booking")

    # 2. Type custom reason
    await send_whatsapp_msg(client, "919999999999", "Going out of town for family function")
    assert_wa_message_contains("919999999999", "Booking Cancelled Successfully")
    assert_wa_message_contains("919999999999", "Going out of town for family function")

    # Verify db updates
    await db_session.refresh(booking)
    await db_session.refresh(slot)
    assert booking.status == "CANCELLED"
    assert booking.cancellationReason == "Going out of town for family function"
    assert booking.paymentStatus == "REFUNDED"
    assert slot.status == "AVAILABLE"
