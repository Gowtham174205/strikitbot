import pytest
from datetime import datetime, timedelta
from app.models import BotOwner, BotBooking, BotTurfSlot

@pytest.mark.asyncio
async def test_cms_reports(client, db_session):
    # Setup test owner
    owner = BotOwner(
        name="Owner A",
        mobile="919999999999",
        turfName="Old Trafford",
        location="Manchester",
        photoUrls="http://pic",
        verified=True,
        subscriptionActive=True,
        pricePerHourPaise=120000
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)

    # Setup test turf slots
    slot1 = BotTurfSlot(
        ownerId=owner.id,
        date="2026-06-20",
        timeSlot="06:00 PM",
        status="BOOKED"
    )
    db_session.add(slot1)
    await db_session.commit()
    await db_session.refresh(slot1)

    # Setup test booking
    booking1 = BotBooking(
        slotId=slot1.id,
        teamName="Red Devils",
        captainName="Wayne Rooney",
        captainPhone="918888888888",
        totalPaidPaise=150000,
        ownerSharePaise=140000,
        platformFeePaise=10000,
        paymentStatus="VERIFIED",
        status="CONFIRMED"
    )
    db_session.add(booking1)
    await db_session.commit()

    headers = {"x-admin-key": "test-admin-key-12345"}

    # 1. Test /api/admin/reports/turfs
    resp = await client.get("/api/admin/reports/turfs", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0

    # Test /api/admin/reports/turfs with search keyword
    resp = await client.get("/api/admin/reports/turfs?search=Trafford", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0

    # 2. Test /api/admin/reports/bookings
    resp = await client.get(f"/api/admin/reports/bookings?startDate=2026-06-01&endDate=2026-06-30&turfId={owner.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0

    # Test bookings with non-matching date range
    resp = await client.get(f"/api/admin/reports/bookings?startDate=2026-07-01&endDate=2026-07-31&turfId={owner.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0

    # 3. Test /api/admin/reports/users
    resp = await client.get(f"/api/admin/reports/users?startDate=2026-06-01&endDate=2026-06-30&turfId={owner.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0

    # 4. Test security (missing / wrong admin key)
    resp = await client.get("/api/admin/reports/turfs")
    assert resp.status_code == 401

    resp = await client.get("/api/admin/reports/turfs", headers={"x-admin-key": "wrong-key"})
    assert resp.status_code == 401
