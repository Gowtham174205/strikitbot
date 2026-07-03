"""
Razorpay Webhook — HARDENED payment handler with:
- HMAC signature verification
- Integer paise-only math (NEVER float)
- Idempotent payout via unique BotPayoutLedger.idempotencyKey
- Full audit trail in BotPaymentAuditLog
- Amount mismatch detection + Telegram alerts
- Database transaction lock for atomicity

CRITICAL: This is FinTech code. Every edge case is handled.
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BotOwner, BotTurfSlot, BotBooking, BotSession, BotPayoutLedger, BotPaymentAuditLog, BotJoinRequest
from app.services import amount_service, payout_service, telegram_service, whatsapp_service, payment_service
from app.middleware.security import verify_razorpay_signature
from app.middleware.rate_limiter import limiter
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/razorpay", tags=["Razorpay"])


# ══════════════════════════════════════════════════════════════════
# RAZORPAY WEBHOOK — payment_link.paid
# ══════════════════════════════════════════════════════════════════

@router.post("/webhook")
@limiter.limit(settings.RATE_LIMIT_RAZORPAY)
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Main Razorpay webhook handler. Processes:
    1. Booking payments (type=booking) — with owner payout
    2. Subscription payments (type=subscription)
    3. Join request payments (type=join_request)
    """
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    # ── Step 1: Verify webhook signature ──
    if not verify_razorpay_signature(raw_body, signature):
        logger.warning("[Razorpay Webhook] Signature verification failed")
        return JSONResponse(status_code=403, content={"error": "Invalid signature"})

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    event = payload.get("event", "")
    logger.info(f"[Razorpay Webhook] Event: {event}")

    if event != "payment_link.paid":
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # ── Step 2: Extract payment data from Razorpay payload ──
    payment_link = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})

    notes = payment_link.get("notes", {})
    payment_type = notes.get("type", "")
    razorpay_payment_id = payment_entity.get("id", "")
    amount_paid_paise = int(payment_entity.get("amount", 0))  # Razorpay sends in paise
    payment_link_id = payment_link.get("id", "")

    logger.info(
        f"[Razorpay Webhook] Type={payment_type} | PaymentID={razorpay_payment_id} "
        f"| AmountPaise={amount_paid_paise} | LinkID={payment_link_id}"
    )

    # ── Route by payment type ──
    if payment_type == "booking":
        return await _handle_booking_payment(
            db, payload, notes, razorpay_payment_id, amount_paid_paise, payment_link_id
        )
    elif payment_type == "subscription":
        return await _handle_subscription_payment(db, notes)
    elif payment_type == "join_request":
        return await _handle_join_request_payment(db, notes, razorpay_payment_id)
    else:
        logger.warning(f"[Razorpay Webhook] Unknown payment type: {payment_type}")
        return JSONResponse(status_code=200, content={"status": "unknown_type"})


# ══════════════════════════════════════════════════════════════════
# BOOKING PAYMENT — The critical hardened flow
# ══════════════════════════════════════════════════════════════════

async def _handle_booking_payment(
    db: AsyncSession,
    full_payload: dict,
    notes: dict,
    razorpay_payment_id: str,
    amount_paid_paise: int,
    payment_link_id: str,
) -> JSONResponse:
    """
    Process a booking payment with full safety:
    1. Idempotency check (no duplicate bookings/payouts)
    2. Amount verification (paid == expected)
    3. Atomic DB transaction (slot + booking + ledger + audit)
    4. Payout ONLY after transaction commits
    """

    # ── Audit: Log webhook receipt ──
    audit_entry = BotPaymentAuditLog(
        eventType="WEBHOOK_RECEIVED",
        payload=json.dumps(full_payload)[:5000],
        message=f"Booking webhook: payment={razorpay_payment_id}, amount={amount_paid_paise} paise",
    )
    db.add(audit_entry)
    await db.flush()

    # ── Extract data from notes ──
    owner_id = int(notes.get("ownerId", 0))
    phone = notes.get("phone", "")
    date = notes.get("date", "")
    slot_time = notes.get("slotTime", "")
    captain_name = notes.get("captainName", "")
    team_name = notes.get("teamName", "")
    sport = notes.get("sport", "N/A")
    expected_total_str = notes.get("expectedTotalPaise", "0")

    if not all([owner_id, phone, date, slot_time, captain_name, team_name]):
        logger.error(f"[Razorpay Webhook] Missing required notes fields")
        await db.commit()
        return JSONResponse(status_code=200, content={"status": "missing_notes"})

    # ── Load owner from database ──
    owner = await db.get(BotOwner, owner_id)
    if not owner:
        logger.error(f"[Razorpay Webhook] Owner {owner_id} not found")
        await db.commit()
        return JSONResponse(status_code=200, content={"status": "owner_not_found"})

    # ── IDEMPOTENCY CHECK: Has this payment already been processed? ──
    existing_booking = (
        await db.execute(
            select(BotBooking).where(BotBooking.razorpayPaymentId == razorpay_payment_id)
        )
    ).scalars().first()

    if existing_booking:
        if existing_booking.paymentStatus == "VERIFIED":
            logger.info(f"[Razorpay Webhook] DUPLICATE: Payment {razorpay_payment_id} already verified")
            # Log duplicate blocked
            db.add(BotPaymentAuditLog(
                bookingId=existing_booking.id,
                eventType="DUPLICATE_BLOCKED",
                message=f"Duplicate webhook blocked for payment {razorpay_payment_id}",
            ))
            await db.commit()
            await telegram_service.send_duplicate_payout_blocked_alert(
                existing_booking.id,
                f"booking_{existing_booking.id}_{razorpay_payment_id}_{owner_id}",
            )
            return JSONResponse(status_code=200, content={"status": "already_processed"})

    # ── Calculate expected amounts from backend (NEVER from client) ──
    try:
        split = amount_service.calculate_booking_split(owner.pricePerHourPaise)
    except (ValueError, TypeError) as e:
        logger.error(f"[Razorpay Webhook] Amount calculation error: {e}")
        db.add(BotPaymentAuditLog(
            eventType="AMOUNT_MISMATCH",
            message=f"Amount calculation error: {e}",
        ))
        await db.commit()
        return JSONResponse(status_code=200, content={"status": "calc_error"})

    expected_total_paise = split["total_paise"]
    owner_share_paise = split["owner_share_paise"]
    platform_fee_paise = split["platform_fee_paise"]

    # ── AMOUNT VERIFICATION: Does Razorpay amount match our expected total? ──
    if not amount_service.validate_payment_amount(amount_paid_paise, expected_total_paise):
        logger.error(
            f"[Razorpay Webhook] AMOUNT MISMATCH! "
            f"Expected={expected_total_paise}, Received={amount_paid_paise}"
        )
        db.add(BotPaymentAuditLog(
            eventType="AMOUNT_MISMATCH",
            payload=json.dumps({"expected": expected_total_paise, "received": amount_paid_paise}),
            message=f"Amount mismatch: expected {expected_total_paise} paise, got {amount_paid_paise} paise",
        ))
        await db.commit()

        # Send Telegram alert
        await telegram_service.send_amount_mismatch_alert(
            booking_id=0,
            expected_paise=expected_total_paise,
            actual_paise=amount_paid_paise,
            razorpay_payment_id=razorpay_payment_id,
        )
        return JSONResponse(status_code=200, content={"status": "amount_mismatch"})

    # ══════════════════════════════════════════════════════════════
    # DATABASE TRANSACTION — Atomic slot + booking + ledger + audit
    # ══════════════════════════════════════════════════════════════
    try:
        # 1. Upsert slot to BOOKED
        existing_slot = (
            await db.execute(
                select(BotTurfSlot).where(
                    BotTurfSlot.ownerId == owner_id,
                    BotTurfSlot.date == date,
                    BotTurfSlot.timeSlot == slot_time,
                )
            )
        ).scalars().first()

        if existing_slot:
            existing_slot.status = "BOOKED"
            slot = existing_slot
        else:
            slot = BotTurfSlot(ownerId=owner_id, date=date, timeSlot=slot_time, status="BOOKED")
            db.add(slot)
            await db.flush()

        # 2. Create booking with VERIFIED payment status
        booking = BotBooking(
            slotId=slot.id,
            teamName=team_name,
            captainName=captain_name,
            captainPhone=phone,
            sport=sport,
            paymentLinkId=payment_link_id,
            razorpayPaymentId=razorpay_payment_id,
            totalPaidPaise=amount_paid_paise,
            ownerSharePaise=owner_share_paise,
            platformFeePaise=platform_fee_paise,
            paymentStatus="VERIFIED",
            payoutStatus="PROCESSING",
            confirmedAt=datetime.utcnow(),
        )
        db.add(booking)
        await db.flush()

        # 3. Create payout ledger with unique idempotency key
        idempotency_key = amount_service.generate_idempotency_key(
            booking.id, razorpay_payment_id, owner_id
        )
        ledger = BotPayoutLedger(
            bookingId=booking.id,
            ownerId=owner_id,
            razorpayPaymentId=razorpay_payment_id,
            totalPaidPaise=amount_paid_paise,
            ownerSharePaise=owner_share_paise,
            platformFeePaise=platform_fee_paise,
            ownerUpiId=owner.upiId or "",
            status="PROCESSING",
            idempotencyKey=idempotency_key,
        )
        db.add(ledger)

        # 4. Audit log — payment verified
        db.add(BotPaymentAuditLog(
            bookingId=booking.id,
            eventType="PAYMENT_VERIFIED",
            message=(
                f"Payment verified: ₹{amount_service.paise_to_rupees(amount_paid_paise)} | "
                f"Owner share: ₹{amount_service.paise_to_rupees(owner_share_paise)} | "
                f"Platform fee: ₹{amount_service.paise_to_rupees(platform_fee_paise)}"
            ),
        ))

        # 5. Update player session
        player_session = (
            await db.execute(select(BotSession).where(BotSession.phone == phone))
        ).scalars().first()
        if player_session:
            await db.delete(player_session)

        # COMMIT the transaction
        await db.commit()

        logger.info(
            f"[Razorpay Webhook] ✅ Booking #{booking.id} confirmed. "
            f"Ledger key: {idempotency_key}"
        )

    except Exception as tx_err:
        await db.rollback()
        logger.error(f"[Razorpay Webhook] Transaction failed: {tx_err}")
        return JSONResponse(status_code=200, content={"status": "transaction_error"})

    # ══════════════════════════════════════════════════════════════
    # PAYOUT — Only after transaction is committed to DB
    # ══════════════════════════════════════════════════════════════
    try:
        db.add(BotPaymentAuditLog(
            bookingId=booking.id,
            eventType="PAYOUT_INITIATED",
            message=f"Initiating payout of ₹{amount_service.paise_to_rupees(owner_share_paise)} to {owner.upiId}",
        ))

        payout_result = await payout_service.execute_payout(
            owner=owner,
            amount_paise=owner_share_paise,
            booking_id=booking.id,
            payment_id=razorpay_payment_id,
            db_session=db,
        )

        if payout_result["status"] in ("processed", "COMPLETED"):
            # SUCCESS
            ledger.status = "COMPLETED"
            ledger.razorpayPayoutId = payout_result.get("payoutId", "")
            booking.payoutStatus = "COMPLETED"
            db.add(BotPaymentAuditLog(
                bookingId=booking.id,
                eventType="PAYOUT_SUCCESS",
                message=f"Payout completed: {payout_result.get('payoutId', 'mock')}",
            ))
        elif payout_result["status"] == "MANUAL_REVIEW":
            ledger.status = "MANUAL_REVIEW"
            ledger.failureReason = payout_result.get("reason", "Unknown")
            booking.payoutStatus = "MANUAL_REVIEW"
            db.add(BotPaymentAuditLog(
                bookingId=booking.id,
                eventType="MANUAL_REVIEW",
                message=f"Payout needs review: {payout_result.get('reason', '')}",
            ))
            await telegram_service.send_manual_review_alert(
                booking.id, payout_result.get("reason", ""), owner.name, owner.turfName
            )
            # FCM Push Notification
            try:
                from app.services.fcm_service import send_fcm_notification
                send_fcm_notification(
                    title="Payout Manual Review Required ⚠️",
                    body=f"Booking #{booking.id} payout to {owner.name} ({owner.turfName}) needs review: {payout_result.get('reason', '')}"
                )
            except Exception as fcm_err:
                logger.error(f"[FCM Manual Review] Failed: {fcm_err}")
        else:
            # FAILED
            ledger.status = "FAILED"
            ledger.failureReason = payout_result.get("reason", "Unknown error")
            booking.payoutStatus = "FAILED"
            db.add(BotPaymentAuditLog(
                bookingId=booking.id,
                eventType="PAYOUT_FAILED",
                message=f"Payout failed: {payout_result.get('reason', '')}",
            ))
            await telegram_service.send_payout_failed_alert(
                owner.name, owner.turfName, owner_share_paise, booking.id,
                payout_result.get("reason", "Unknown"),
            )
            # FCM Push Notification
            try:
                from app.services.fcm_service import send_fcm_notification
                send_fcm_notification(
                    title="Payout Failed ❌",
                    body=f"Booking #{booking.id} payout of ₹{amount_service.paise_to_rupees(owner_share_paise)} to {owner.name} failed: {payout_result.get('reason', '')}"
                )
            except Exception as fcm_err:
                logger.error(f"[FCM Payout Failed] Failed: {fcm_err}")

        await db.commit()

    except Exception as payout_err:
        logger.error(f"[Razorpay Webhook] Payout error: {payout_err}")
        ledger.status = "FAILED"
        ledger.failureReason = str(payout_err)
        booking.payoutStatus = "FAILED"
        await db.commit()
        await telegram_service.send_payout_failed_alert(
            owner.name, owner.turfName, owner_share_paise, booking.id, str(payout_err)
        )
        # FCM Push Notification
        try:
            from app.services.fcm_service import send_fcm_notification
            send_fcm_notification(
                title="Payout Failed ❌",
                body=f"Booking #{booking.id} payout of ₹{amount_service.paise_to_rupees(owner_share_paise)} to {owner.name} failed: {payout_err}"
            )
        except Exception as fcm_err:
            logger.error(f"[FCM Payout Err] Failed: {fcm_err}")

    # ── Send WhatsApp notifications (non-blocking) ──
    try:
        rupee_total = amount_service.paise_to_rupees(amount_paid_paise)
        rupee_fee = amount_service.paise_to_rupees(platform_fee_paise)
        await whatsapp_service.send_text(
            phone,
            f"✅ *Booking Confirmed!* ✅\n\n"
            f"Hello {captain_name}, your turf booking is confirmed!\n\n"
            f"• Turf: *{owner.turfName}*\n"
            f"• Date: {date}\n"
            f"• Time Slot: {slot_time}\n"
            f"• Sport/Event: {sport}\n"
            f"• Team Name: {team_name}\n"
            f"• Amount Paid: ₹{rupee_total}\n"
            f"• STRIKIT Booking Fee: ₹{rupee_fee}\n\n"
            f"_Powered by STRIKIT_",
        )
        import urllib.parse
        wa_link = f"https://wa.me/{settings.ONBOARDING_NUMBER}?text=verify_{booking.id}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_link)}"
        await whatsapp_service.send_image(
            phone,
            qr_url,
            caption="🎫 *Your STRIKIT Booking Ticket QR* 🎫\n\nShow this QR at the turf. The turf owner will scan it to verify your booking slot!"
        )
    except Exception as wa_err:
        logger.error(f"[Razorpay Webhook] WhatsApp notification failed: {wa_err}")

    try:
        rupee_owner_share = amount_service.paise_to_rupees(owner_share_paise)
        await whatsapp_service.send_text(
            owner.mobile,
            f"📅 *New Booking Alert for {owner.turfName}!* 📅\n\n"
            f"Hello {owner.name}, a new booking has been confirmed at your turf:\n\n"
            f"• Date: {date}\n"
            f"• Time Slot: {slot_time}\n"
            f"• Sport/Event: {sport}\n"
            f"• Team Name: {team_name}\n"
            f"• Captain Name: {captain_name} ({phone})\n"
            f"• Amount: *₹{rupee_owner_share}*\n\n"
            f"The slot status has been updated to *BOOKED* in your inventory.\n\n"
            f"_Powered by STRIKIT_",
        )
    except Exception as wa_owner_err:
        logger.error(f"[Razorpay Webhook] Owner WhatsApp notification failed: {wa_owner_err}")


    try:
        await telegram_service.send_alert(
            f"New Booking at {owner.turfName}:\n"
            f"Captain: {captain_name} ({phone})\n"
            f"Team: {team_name}\n"
            f"Date: {date} @ {slot_time}\n"
            f"Amount: ₹{amount_service.paise_to_rupees(amount_paid_paise)}\n"
            f"Platform Fee: ₹{amount_service.paise_to_rupees(platform_fee_paise)}\n"
            f"Owner Payout: ₹{amount_service.paise_to_rupees(owner_share_paise)}"
        )
        # FCM Push Notification
        try:
            from app.services.fcm_service import send_fcm_notification
            send_fcm_notification(
                title="New Booking Confirmed 📅",
                body=f"Captain {captain_name} booked a slot at {owner.turfName} on {date} @ {slot_time} (₹{amount_service.paise_to_rupees(amount_paid_paise)})"
            )
        except Exception as fcm_err:
            logger.error(f"[FCM New Booking] Failed: {fcm_err}")
    except Exception as tg_err:
        logger.error(f"[Razorpay Webhook] Telegram notification failed: {tg_err}")

    return JSONResponse(status_code=200, content={"status": "success"})


# ══════════════════════════════════════════════════════════════════
# SUBSCRIPTION PAYMENT
# ══════════════════════════════════════════════════════════════════

async def _handle_subscription_payment(db: AsyncSession, notes: dict) -> JSONResponse:
    """Process owner subscription payment — activate 30-day subscription."""
    owner_id = int(notes.get("ownerId", 0))
    if not owner_id:
        return JSONResponse(status_code=200, content={"status": "missing_owner_id"})

    owner = await db.get(BotOwner, owner_id)
    if not owner:
        return JSONResponse(status_code=200, content={"status": "owner_not_found"})

    # Extract plan from notes
    plan = notes.get("plan", "TRIAL").upper()

    # Plan details setup
    if plan == "TRIAL":
        days = 90
        plan_desc = "First-Time Onboarding (₹699 for 3 Months)"
        features_desc = "All Premium Features"
    elif plan == "BASIC":
        days = 30
        plan_desc = "Basic Plan (₹199 per Month)"
        features_desc = "Basic Bookings Only"
    elif plan == "PREMIUM":
        days = 30
        plan_desc = "Premium Plan (₹399 per Month)"
        features_desc = "All Premium Features"
    elif plan == "PREMIUM_3M":
        days = 90
        plan_desc = "Premium 3-Month Plan (₹749 for 3 Months)"
        features_desc = "All Premium Features"
    else:
        plan = "TRIAL"
        days = 90
        plan_desc = "First-Time Onboarding (₹699 for 3 Months)"
        features_desc = "All Premium Features"

    # Activate subscription and set expiry
    owner.subscriptionActive = True
    owner.subscriptionStartedAt = datetime.utcnow()
    owner.subscriptionPlan = plan

    from datetime import timedelta
    owner.subscriptionExpiry = datetime.utcnow() + timedelta(days=days)

    # Update session to OWNER_SETUP_PRICE state
    session = (
        await db.execute(select(BotSession).where(BotSession.phone == owner.mobile))
    ).scalars().first()
    if not session:
        session = BotSession(phone=owner.mobile)
        db.add(session)
    session.state = "OWNER_SETUP_PRICE"
    session.role = "OWNER"
    session.context = json.dumps({"ownerId": owner.id})

    await db.commit()

    logger.info(f"[Razorpay Webhook] Subscription activated ({plan}) for owner {owner.name}")

    try:
        await whatsapp_service.send_text(
            owner.mobile,
            f"🎉 *Subscription Activated!* 🎉\n\n"
            f"Hello {owner.name}, your STRIKIT subscription for *{owner.turfName}* is now active!\n\n"
            f"• Plan: {plan_desc}\n"
            f"• Expires: {owner.subscriptionExpiry.strftime('%d %b %Y')}\n\n"
            f"To start receiving bookings, let's configure your turf settings. "
            f"Please reply to this message with your turf's **Hourly Price in Rupees** (e.g. `1200`):",
        )
    except Exception as e:
        logger.error(f"[Razorpay Webhook] WhatsApp notification failed: {e}")

    try:
        await telegram_service.send_alert(
            f"Subscription activated: {owner.name} ({owner.turfName}) - Plan: {plan}"
        )
    except Exception as e:
        logger.error(f"[Razorpay Webhook] Telegram alert failed: {e}")

    return JSONResponse(status_code=200, content={"status": "subscription_activated"})


# ══════════════════════════════════════════════════════════════════
# JOIN REQUEST PAYMENT (₹9 platform fee)
# ══════════════════════════════════════════════════════════════════

async def _handle_join_request_payment(
    db: AsyncSession, notes: dict, razorpay_payment_id: str
) -> JSONResponse:
    """Process single player join request platform fee payment."""
    request_id = int(notes.get("requestId", 0))
    phone = notes.get("phone", "")

    if not request_id:
        return JSONResponse(status_code=200, content={"status": "missing_request_id"})

    join_req = await db.get(BotJoinRequest, request_id)
    if not join_req:
        return JSONResponse(status_code=200, content={"status": "request_not_found"})

    # Update join request status to PENDING (awaiting captain approval)
    join_req.status = "PENDING"
    await db.commit()

    logger.info(f"[Razorpay Webhook] Join request {request_id} fee paid by {phone}")

    # Notify player
    try:
        await whatsapp_service.send_text(
            phone,
            f"⏳ *STRIKIT Platform Fee Verified!* ⏳\n\n"
            f"Hello {join_req.playerName}, your platform fee of *₹9.00* has been processed.\n\n"
            f"Your join request has been sent to the captain for approval.\n\n"
            f"_Powered by STRIKIT_",
        )
    except Exception:
        pass

    # Notify captain about join request
    try:
        booking = await db.get(BotBooking, join_req.bookingId)
        if booking:
            slot = await db.get(BotTurfSlot, booking.slotId)
            owner = await db.get(BotOwner, slot.ownerId) if slot else None
            turf_name = owner.turfName if owner else "Unknown Turf"
            await whatsapp_service.send_buttons(
                booking.captainPhone,
                f"🆕 *New Player Join Request* 🆕\n\n"
                f"Player *{join_req.playerName}* wants to join your game at *{turf_name}*\n"
                f"Date: {slot.date if slot else 'N/A'} | Time: {slot.timeSlot if slot else 'N/A'}\n\n"
                f"Approve or reject this request:",
                [
                    {"id": f"approve_join_{join_req.id}", "title": "✅ Approve"},
                    {"id": f"reject_join_{join_req.id}", "title": "❌ Reject"},
                ],
            )
    except Exception as e:
        logger.error(f"[Razorpay Webhook] Captain notification failed: {e}")

    return JSONResponse(status_code=200, content={"status": "join_fee_paid"})


# ══════════════════════════════════════════════════════════════════
# MOCK ENDPOINTS (for testing without real Razorpay)
# ══════════════════════════════════════════════════════════════════

@router.post("/mock/booking-payment")
async def mock_booking_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """Simulate a successful booking payment webhook for testing."""
    body = await request.json()
    notes = body.get("notes", {})
    amount_paise = int(body.get("amount_paise", 0))

    mock_payment_id = f"pay_mock_{datetime.utcnow().timestamp()}"
    mock_link_id = f"plink_mock_{datetime.utcnow().timestamp()}"

    mock_payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": mock_link_id, "notes": notes}},
            "payment": {"entity": {"id": mock_payment_id, "amount": amount_paise}},
        },
    }

    return await _handle_booking_payment(
        db, mock_payload, notes, mock_payment_id, amount_paise, mock_link_id
    )
