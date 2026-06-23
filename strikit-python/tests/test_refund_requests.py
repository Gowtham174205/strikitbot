import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import BotOwner, BotSession, BotOwnerRefundRequest
from app.services.whatsapp_service import mock_sent_messages, clear_mock_messages as clear_wa
from app.services.telegram_service import mock_telegram_messages, clear_mock_messages as clear_tg
from tests.test_full_flow import send_whatsapp_msg

@pytest.mark.asyncio
async def test_owner_refund_request_flow(client, db_session):
    clear_wa()
    clear_tg()

    # 1. Setup owner with active subscription, started 2 days ago (eligible)
    owner = BotOwner(
        name="John Doe",
        mobile="918888888888",
        turfName="Camp Nou",
        location="Madrid",
        photoUrls="http://pic",
        verified=True,
        subscriptionActive=True,
        subscriptionStartedAt=datetime.utcnow() - timedelta(days=2),
        subscriptionExpiry=datetime.utcnow() + timedelta(days=28),
    )
    db_session.add(owner)
    await db_session.commit()

    # 2. Setup owner session
    session = BotSession(
        phone="918888888888",
        role="OWNER",
        state="OWNER_START",
        context="{}",
    )
    db_session.add(session)
    await db_session.commit()

    # 3. Send /refund command
    response = await send_whatsapp_msg(client, "918888888888", "/refund")
    assert response.status_code == 200

    # Verify WhatsApp message asks for reason
    assert len(mock_sent_messages) > 0
    assert "Please type the reason for requesting a refund" in mock_sent_messages[-1]["text"]["body"]

    # Verify session state changed to AWAITING_OWNER_REFUND_REASON
    res = await db_session.execute(select(BotSession).where(BotSession.phone == "918888888888"))
    sess = res.scalars().first()
    assert sess is not None
    assert sess.state == "AWAITING_OWNER_REFUND_REASON"

    # 4. Send the reason
    reason_text = "I am closing my business because of relocation."
    response = await send_whatsapp_msg(client, "918888888888", reason_text)
    assert response.status_code == 200

    # Verify confirmation WhatsApp sent
    assert "Refund Request Submitted" in mock_sent_messages[-1]["text"]["body"]

    # Verify request created in DB
    res = await db_session.execute(select(BotOwnerRefundRequest).where(BotOwnerRefundRequest.ownerId == owner.id))
    req = res.scalars().first()
    assert req is not None
    assert req.reason == reason_text
    assert req.status == "PENDING"

    # Verify session cleared
    res = await db_session.execute(select(BotSession).where(BotSession.phone == "918888888888"))
    sess = res.scalars().first()
    assert sess is None

    # Verify Telegram alert sent to admin
    assert len(mock_telegram_messages) > 0
    assert "NEW REFUND REQUEST" in mock_telegram_messages[-1]["text"]

    # 5. Get stats and verify pendingRefundRequests count
    headers = {"x-admin-key": "test-admin-key-12345"}
    resp = await client.get("/api/admin/stats", headers=headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["pendingRefundRequests"] == 1

    # 6. Admin GET /api/admin/refund-requests
    resp = await client.get("/api/admin/refund-requests", headers=headers)
    assert resp.status_code == 200
    req_list = resp.json()
    assert len(req_list) == 1
    assert req_list[0]["id"] == req.id
    assert req_list[0]["ownerName"] == "John Doe"
    assert req_list[0]["reason"] == reason_text

    # 7. Admin POST /api/admin/refund-requests/{id}/reject
    resp = await client.post(f"/api/admin/refund-requests/{req.id}/reject", headers=headers)
    assert resp.status_code == 200
    
    # Verify request status in DB is REJECTED
    await db_session.refresh(req)
    assert req.status == "REJECTED"
    # Verify subscription remains active
    await db_session.refresh(owner)
    assert owner.subscriptionActive is True

    # 8. Re-activate request state to PENDING for testing resolve
    req.status = "PENDING"
    await db_session.commit()

    # 9. Admin POST /api/admin/refund-requests/{id}/resolve
    resp = await client.post(f"/api/admin/refund-requests/{req.id}/resolve", headers=headers)
    assert resp.status_code == 200

    # Verify status in DB is RESOLVED
    await db_session.refresh(req)
    assert req.status == "RESOLVED"
    # Verify owner subscription is now deactivated
    await db_session.refresh(owner)
    assert owner.subscriptionActive is False

@pytest.mark.asyncio
async def test_owner_refund_request_ineligible(client, db_session):
    clear_wa()

    # 1. Setup owner with subscription started 8 days ago (ineligible)
    owner = BotOwner(
        name="Alice Smith",
        mobile="917777777777",
        turfName="Wembley",
        location="London",
        photoUrls="http://pic",
        verified=True,
        subscriptionActive=True,
        subscriptionStartedAt=datetime.utcnow() - timedelta(days=8),
        subscriptionExpiry=datetime.utcnow() + timedelta(days=22),
    )
    db_session.add(owner)
    await db_session.commit()

    # 2. Setup owner session
    session = BotSession(
        phone="917777777777",
        role="OWNER",
        state="OWNER_START",
        context="{}",
    )
    db_session.add(session)
    await db_session.commit()

    # 3. Send /refund command
    response = await send_whatsapp_msg(client, "917777777777", "/refund")
    assert response.status_code == 200

    # Verify error message sent
    assert len(mock_sent_messages) > 0
    assert "Refund Not Allowed" in mock_sent_messages[-1]["text"]["body"]

    # Verify session state remains OWNER_START (or at least not changed to AWAITING_OWNER_REFUND_REASON)
    res = await db_session.execute(select(BotSession).where(BotSession.phone == "917777777777"))
    sess = res.scalars().first()
    assert sess is not None
    assert sess.state != "AWAITING_OWNER_REFUND_REASON"
