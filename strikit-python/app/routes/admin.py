"""
Admin API — Owner management + Payout monitoring + Manual retry.
All endpoints require x-admin-key header (timing-safe verification).
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.security import require_admin_key
from app.middleware.rate_limiter import limiter
from app.models import BotOwner, BotBooking, BotTurfSlot, BotSession, BotJoinRequest, BotPayoutLedger, BotPaymentAuditLog, BotOwnerRefundRequest
from app.services import whatsapp_service, payment_service, payout_service, amount_service, telegram_service
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin_key)])


# ══════════════════════════════════════════════════════════════════
# OWNER MANAGEMENT
# ══════════════════════════════════════════════════════════════════

@router.get("/owners")
async def list_owners(
    request: Request,
    search: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all turf owners, with optional search by name/phone/turf."""
    query = select(BotOwner).order_by(desc(BotOwner.createdAt))
    if search:
        search = search.strip()
        query = query.where(
            BotOwner.name.ilike(f"%{search}%")
            | BotOwner.mobile.ilike(f"%{search}%")
            | BotOwner.turfName.ilike(f"%{search}%")
        )
    result = await db.execute(query)
    owners = result.scalars().all()
    return [
        {
            "id": o.id, "name": o.name, "mobile": o.mobile, "turfName": o.turfName,
            "location": o.location, "verified": o.verified,
            "subscriptionActive": o.subscriptionActive,
            "subscriptionExpiry": o.subscriptionExpiry.isoformat() if o.subscriptionExpiry else None,
            "upiId": o.upiId, "pricePerHourPaise": o.pricePerHourPaise,
            "msme": o.msme,
            "msmeCardUrl": o.msmeCardUrl,
            "utilityBillUrl": o.utilityBillUrl,
            "createdAt": o.createdAt.isoformat() if o.createdAt else None,
        }
        for o in owners
    ]


@router.post("/owners/{owner_id}/approve")
async def approve_owner(owner_id: int, db: AsyncSession = Depends(get_db)):
    """Approve an owner — set verified, send subscription link."""
    owner = await db.get(BotOwner, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

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

    try:
        await whatsapp_service.send_text(
            owner.mobile,
            f"🎉 *Congratulations {owner.name}! Your STRIKIT Registration has been APPROVED!* 🎉\n\n"
            f"Your turf *{owner.turfName}* has been verified.\n\n"
            f"💳 *Subscription Link:* Please pay ₹699 for 3 Months (All features included) to activate your bot:\n"
            f"{sub_link}\n\n"
            f"_Powered by STRIKIT_",
        )
    except Exception as e:
        logger.error(f"[Admin Approve] WhatsApp failed: {e}")

    return {"message": f"Owner {owner.name} approved successfully."}


@router.post("/owners/{owner_id}/reject")
async def reject_owner(owner_id: int, db: AsyncSession = Depends(get_db)):
    """Reject/deactivate an owner."""
    owner = await db.get(BotOwner, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    owner.verified = False
    owner.subscriptionActive = False
    owner.subscriptionExpiry = None

    # Delete session
    sessions = (await db.execute(select(BotSession).where(BotSession.phone == owner.mobile))).scalars().all()
    for s in sessions:
        await db.delete(s)

    await db.commit()

    try:
        await whatsapp_service.send_text(
            owner.mobile,
            f"❌ Hello {owner.name}, your STRIKIT registration for *{owner.turfName}* was rejected. Please contact support.\n\n_Powered by STRIKIT_",
        )
    except Exception as e:
        logger.error(f"[Admin Reject] WhatsApp failed: {e}")

    return {"message": f"Owner {owner.name} rejected."}


@router.delete("/owners/{owner_id}")
async def delete_owner(owner_id: int, db: AsyncSession = Depends(get_db)):
    """Completely purge an owner and all related data."""
    owner = await db.get(BotOwner, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    # Delete related data in order
    slots = (await db.execute(select(BotTurfSlot).where(BotTurfSlot.ownerId == owner_id))).scalars().all()
    slot_ids = [s.id for s in slots]

    if slot_ids:
        bookings = (await db.execute(select(BotBooking).where(BotBooking.slotId.in_(slot_ids)))).scalars().all()
        booking_ids = [b.id for b in bookings]

        if booking_ids:
            # Delete audit logs
            audits = (await db.execute(select(BotPaymentAuditLog).where(BotPaymentAuditLog.bookingId.in_(booking_ids)))).scalars().all()
            for a in audits:
                await db.delete(a)

            # Delete payout ledgers
            ledgers = (await db.execute(select(BotPayoutLedger).where(BotPayoutLedger.bookingId.in_(booking_ids)))).scalars().all()
            for l in ledgers:
                await db.delete(l)

            # Delete join requests
            joins = (await db.execute(select(BotJoinRequest).where(BotJoinRequest.bookingId.in_(booking_ids)))).scalars().all()
            for j in joins:
                await db.delete(j)

            for b in bookings:
                await db.delete(b)

        for s in slots:
            await db.delete(s)

    # Delete sessions
    phones = [p for p in [owner.mobile, owner.businessPhone] if p]
    if phones:
        sessions = (await db.execute(select(BotSession).where(BotSession.phone.in_(phones)))).scalars().all()
        for s in sessions:
            await db.delete(s)

    # Delete owner payout ledgers
    owner_ledgers = (await db.execute(select(BotPayoutLedger).where(BotPayoutLedger.ownerId == owner_id))).scalars().all()
    for l in owner_ledgers:
        await db.delete(l)

    await db.delete(owner)
    await db.commit()

    return {"message": f"Owner {owner.name} ({owner.turfName}) and all related data deleted."}


# ══════════════════════════════════════════════════════════════════
# ADMINISTRATIVE STATS (NEW)
# ══════════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_admin_stats(db: AsyncSession = Depends(get_db)):
    """Retrieve administrative metrics and stats."""
    from sqlalchemy import func
    
    # Active Turfs (verified = True, subscriptionActive = True)
    active_turfs = (await db.execute(
        select(func.count()).select_from(BotOwner).where(BotOwner.verified == True, BotOwner.subscriptionActive == True)
    )).scalar() or 0
    
    # Pending Verifications (verified = False)
    pending_verifications = (await db.execute(
        select(func.count()).select_from(BotOwner).where(BotOwner.verified == False)
    )).scalar() or 0
    
    # Failed Payouts
    failed_payouts = (await db.execute(
        select(func.count()).select_from(BotPayoutLedger).where(BotPayoutLedger.status == "FAILED")
    )).scalar() or 0

    # Total Bookings
    total_bookings = (await db.execute(
        select(func.count()).select_from(BotBooking)
    )).scalar() or 0

    # Total Revenue (sum of totalPaidPaise for bookings)
    total_revenue_paise = (await db.execute(
        select(func.sum(BotBooking.totalPaidPaise))
    )).scalar() or 0

    # Pending Refund Requests
    pending_refund_requests = (await db.execute(
        select(func.count()).select_from(BotOwnerRefundRequest).where(BotOwnerRefundRequest.status == "PENDING")
    )).scalar() or 0

    return {
        "activeTurfs": active_turfs,
        "pendingVerifications": pending_verifications,
        "failedPayouts": failed_payouts,
        "totalBookings": total_bookings,
        "totalRevenuePaise": total_revenue_paise,
        "pendingRefundRequests": pending_refund_requests
    }


# ══════════════════════════════════════════════════════════════════
# PAYOUT MONITORING (NEW)
# ══════════════════════════════════════════════════════════════════

@router.get("/payouts")
async def list_payouts(
    request: Request,
    status: str = Query(None, description="Filter by status: PROCESSING, COMPLETED, FAILED, MANUAL_REVIEW"),
    db: AsyncSession = Depends(get_db),
):
    """List all payout ledger entries with booking/owner details."""
    query = select(BotPayoutLedger).order_by(desc(BotPayoutLedger.createdAt))
    if status:
        query = query.where(BotPayoutLedger.status == status.upper())

    result = await db.execute(query)
    ledgers = result.scalars().all()

    output = []
    for l in ledgers:
        owner = await db.get(BotOwner, l.ownerId)
        output.append({
            "id": l.id,
            "bookingId": l.bookingId,
            "ownerId": l.ownerId,
            "ownerName": owner.name if owner else "Unknown",
            "turfName": owner.turfName if owner else "Unknown",
            "razorpayPaymentId": l.razorpayPaymentId,
            "razorpayPayoutId": l.razorpayPayoutId,
            "totalPaid": f"₹{amount_service.paise_to_rupees(l.totalPaidPaise)}",
            "ownerShare": f"₹{amount_service.paise_to_rupees(l.ownerSharePaise)}",
            "platformFee": f"₹{amount_service.paise_to_rupees(l.platformFeePaise)}",
            "ownerUpiId": l.ownerUpiId,
            "status": l.status,
            "idempotencyKey": l.idempotencyKey,
            "attemptCount": l.attemptCount,
            "failureReason": l.failureReason,
            "createdAt": l.createdAt.isoformat() if l.createdAt else None,
            "updatedAt": l.updatedAt.isoformat() if l.updatedAt else None,
        })
    return output


@router.get("/payouts/{payout_id}")
async def get_payout_detail(payout_id: int, db: AsyncSession = Depends(get_db)):
    """Get single payout detail with full audit trail."""
    ledger = await db.get(BotPayoutLedger, payout_id)
    if not ledger:
        raise HTTPException(status_code=404, detail="Payout ledger not found")

    owner = await db.get(BotOwner, ledger.ownerId)

    # Fetch audit logs for this booking
    audit_result = await db.execute(
        select(BotPaymentAuditLog)
        .where(BotPaymentAuditLog.bookingId == ledger.bookingId)
        .order_by(BotPaymentAuditLog.createdAt)
    )
    audit_logs = audit_result.scalars().all()

    return {
        "payout": {
            "id": ledger.id,
            "bookingId": ledger.bookingId,
            "ownerName": owner.name if owner else "Unknown",
            "turfName": owner.turfName if owner else "Unknown",
            "razorpayPaymentId": ledger.razorpayPaymentId,
            "razorpayPayoutId": ledger.razorpayPayoutId,
            "totalPaid": f"₹{amount_service.paise_to_rupees(ledger.totalPaidPaise)}",
            "ownerShare": f"₹{amount_service.paise_to_rupees(ledger.ownerSharePaise)}",
            "platformFee": f"₹{amount_service.paise_to_rupees(ledger.platformFeePaise)}",
            "ownerUpiId": ledger.ownerUpiId,
            "status": ledger.status,
            "idempotencyKey": ledger.idempotencyKey,
            "attemptCount": ledger.attemptCount,
            "failureReason": ledger.failureReason,
        },
        "auditTrail": [
            {
                "eventType": a.eventType,
                "message": a.message,
                "createdAt": a.createdAt.isoformat() if a.createdAt else None,
            }
            for a in audit_logs
        ],
    }


@router.post("/payouts/{payout_id}/retry")
async def retry_payout(payout_id: int, db: AsyncSession = Depends(get_db)):
    """
    Manual retry for FAILED payouts only.
    BLOCKS retry for COMPLETED or PROCESSING payouts.
    """
    ledger = await db.get(BotPayoutLedger, payout_id)
    if not ledger:
        raise HTTPException(status_code=404, detail="Payout ledger not found")

    # ── Safety: NEVER retry COMPLETED payouts ──
    if ledger.status == "COMPLETED":
        raise HTTPException(status_code=400, detail="Cannot retry: payout already COMPLETED")

    if ledger.status == "PROCESSING":
        raise HTTPException(status_code=400, detail="Cannot retry: payout currently PROCESSING")

    # Only FAILED and MANUAL_REVIEW can be retried
    if ledger.status not in ("FAILED", "MANUAL_REVIEW"):
        raise HTTPException(status_code=400, detail=f"Cannot retry payout with status: {ledger.status}")

    owner = await db.get(BotOwner, ledger.ownerId)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    # ── Execute retry ──
    ledger.status = "PROCESSING"
    ledger.attemptCount += 1
    ledger.failureReason = None
    await db.commit()

    db.add(BotPaymentAuditLog(
        bookingId=ledger.bookingId,
        eventType="PAYOUT_INITIATED",
        message=f"Admin manual retry (attempt #{ledger.attemptCount})",
    ))

    payout_result = await payout_service.execute_payout(
        owner=owner,
        amount_paise=ledger.ownerSharePaise,
        booking_id=ledger.bookingId,
        db_session=db,
    )

    booking = await db.get(BotBooking, ledger.bookingId)

    if payout_result["status"] in ("processed", "COMPLETED"):
        ledger.status = "COMPLETED"
        ledger.razorpayPayoutId = payout_result.get("payoutId", "")
        if booking:
            booking.payoutStatus = "COMPLETED"
        db.add(BotPaymentAuditLog(
            bookingId=ledger.bookingId,
            eventType="PAYOUT_SUCCESS",
            message=f"Manual retry successful: {payout_result.get('payoutId', '')}",
        ))
    else:
        ledger.status = "FAILED"
        ledger.failureReason = payout_result.get("reason", "Unknown")
        if booking:
            booking.payoutStatus = "FAILED"
        db.add(BotPaymentAuditLog(
            bookingId=ledger.bookingId,
            eventType="PAYOUT_FAILED",
            message=f"Manual retry failed: {payout_result.get('reason', '')}",
        ))

    await db.commit()

    return {
        "message": f"Retry {'succeeded' if ledger.status == 'COMPLETED' else 'failed'}",
        "status": ledger.status,
        "attemptCount": ledger.attemptCount,
        "payoutId": ledger.razorpayPayoutId,
    }


# ══════════════════════════════════════════════════════════════════
# OWNER SUBSCRIPTION REFUND REQUESTS
# ══════════════════════════════════════════════════════════════════

@router.get("/refund-requests")
async def list_refund_requests(
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List subscription refund requests with owner details."""
    query = (
        select(BotOwnerRefundRequest)
        .options(selectinload(BotOwnerRefundRequest.owner))
        .join(BotOwner)
        .order_by(desc(BotOwnerRefundRequest.createdAt))
    )
    if status:
        query = query.where(BotOwnerRefundRequest.status == status)
    
    result = await db.execute(query)
    reqs = result.scalars().all()
    
    return [
        {
            "id": r.id,
            "ownerId": r.ownerId,
            "ownerName": r.owner.name,
            "turfName": r.owner.turfName,
            "ownerMobile": r.owner.mobile,
            "reason": r.reason,
            "status": r.status,
            "createdAt": r.createdAt.isoformat() if r.createdAt else None,
        }
        for r in reqs
    ]


@router.post("/refund-requests/{id}/resolve")
async def resolve_refund_request(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mark refund request as resolved and deactivate owner's subscription."""
    req = await db.get(BotOwnerRefundRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Refund request not found")
        
    req.status = "RESOLVED"
    
    # Deactivate subscription
    owner = await db.get(BotOwner, req.ownerId)
    if owner:
        owner.subscriptionActive = False
        try:
            await whatsapp_service.send_text(
                owner.mobile,
                f"ℹ️ *STRIKIT Subscription Refunded* ⚠️\n\n"
                f"Hello {owner.name}, your refund request for subscription of *{owner.turfName}* has been approved and processed. "
                f"Your subscription is now inactive."
            )
        except Exception as e:
            logger.error(f"[Admin Resolve Refund] Failed to notify owner: {e}")

    await db.commit()
    return {"message": "Refund request resolved and owner subscription deactivated"}


@router.post("/refund-requests/{id}/reject")
async def reject_refund_request(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mark refund request as rejected."""
    req = await db.get(BotOwnerRefundRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Refund request not found")
        
    req.status = "REJECTED"
    
    # Notify owner
    owner = await db.get(BotOwner, req.ownerId)
    if owner:
        try:
            await whatsapp_service.send_text(
                owner.mobile,
                f"ℹ️ *STRIKIT Subscription Refund Request Update* ⚠️\n\n"
                f"Hello {owner.name}, your refund request for subscription of *{owner.turfName}* has been reviewed and rejected. "
                f"Your subscription remains active."
            )
        except Exception as e:
            logger.error(f"[Admin Reject Refund] Failed to notify owner: {e}")

    await db.commit()
    return {"message": "Refund request rejected"}


# ══════════════════════════════════════════════════════════════════
# TELEGRAM WEBHOOK SETUP
# ══════════════════════════════════════════════════════════════════

@router.post("/telegram/setup-webhook")
async def setup_telegram_webhook(request: Request):
    """Register Telegram webhook URL with Telegram servers."""
    import httpx

    token = settings.TELEGRAM_BOT_TOKEN
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN not set")
    if not secret:
        raise HTTPException(status_code=400, detail="TELEGRAM_WEBHOOK_SECRET not set")

    host = request.headers.get("host", "localhost:5000")
    protocol = "https" if "localhost" not in host else "http"
    webhook_url = f"{protocol}://{host}/webhook/telegram"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "secret_token": secret},
        )
        return {"message": "Webhook registered", "telegramResponse": resp.json(), "registeredUrl": webhook_url}


# ══════════════════════════════════════════════════════════════════
# CMS PDF REPORTS (NEW)
# ══════════════════════════════════════════════════════════════════

@router.get("/reports/turfs")
async def download_turfs_report(
    search: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Generates and streams a PDF containing turf details list."""
    import os
    from app.services.pdf_generator import generate_turfs_pdf

    query = select(BotOwner).order_by(desc(BotOwner.createdAt))
    if search:
        search = search.strip()
        query = query.where(
            BotOwner.name.ilike(f"%{search}%")
            | BotOwner.mobile.ilike(f"%{search}%")
            | BotOwner.turfName.ilike(f"%{search}%")
        )
    result = await db.execute(query)
    owners = result.scalars().all()

    # Store report temporarily in workspace temp folder
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp_dir = os.path.join(base_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    filepath = generate_turfs_pdf(owners, tmp_dir)
    return FileResponse(filepath, media_type="application/pdf", filename=os.path.basename(filepath))


@router.get("/reports/bookings")
async def download_bookings_report(
    startDate: str = Query(None),
    endDate: str = Query(None),
    turfId: int = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Generates and streams a PDF containing bookings/slots list within date range."""
    import os
    from app.services.pdf_generator import generate_bookings_pdf

    # Join with BotTurfSlot to get date and owner ID
    query = select(BotBooking).join(BotBooking.slot).options(
        selectinload(BotBooking.slot).selectinload(BotTurfSlot.owner)
    ).order_by(desc(BotTurfSlot.date))

    if turfId:
        query = query.where(BotTurfSlot.ownerId == turfId)
    if startDate:
        query = query.where(BotTurfSlot.date >= startDate)
    if endDate:
        query = query.where(BotTurfSlot.date <= endDate)

    result = await db.execute(query)
    bookings = result.scalars().all()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp_dir = os.path.join(base_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    filepath = generate_bookings_pdf(bookings, tmp_dir)
    return FileResponse(filepath, media_type="application/pdf", filename=os.path.basename(filepath))


@router.get("/reports/users")
async def download_users_report(
    startDate: str = Query(None),
    endDate: str = Query(None),
    turfId: int = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Generates and streams a PDF containing booking user details list."""
    import os
    from app.services.pdf_generator import generate_users_pdf

    query = select(BotBooking).join(BotBooking.slot).options(
        selectinload(BotBooking.slot).selectinload(BotTurfSlot.owner)
    ).where(BotBooking.paymentStatus == "VERIFIED").order_by(desc(BotBooking.createdAt))

    if turfId:
        query = query.where(BotTurfSlot.ownerId == turfId)
    if startDate:
        query = query.where(BotTurfSlot.date >= startDate)
    if endDate:
        query = query.where(BotTurfSlot.date <= endDate)

    result = await db.execute(query)
    bookings = result.scalars().all()

    # Aggregate by captain phone
    players = {}
    for b in bookings:
        phone = b.captainPhone
        if phone not in players:
            players[phone] = {
                "phone": phone,
                "name": b.captainName,
                "team": b.teamName,
                "bookings_count": 0,
                "total_paid_paise": 0
            }
        players[phone]["bookings_count"] += 1
        players[phone]["total_paid_paise"] += b.totalPaidPaise

    users_data = sorted(players.values(), key=lambda x: x["total_paid_paise"], reverse=True)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp_dir = os.path.join(base_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    filepath = generate_users_pdf(users_data, tmp_dir)
    return FileResponse(filepath, media_type="application/pdf", filename=os.path.basename(filepath))
