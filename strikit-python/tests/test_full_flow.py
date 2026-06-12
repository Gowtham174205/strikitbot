"""
Full Bot Flow Verification Test.
Simulates owner onboarding, developer approval, subscription activation,
player turf slot selection, booking creation, and payment verification.
"""
import pytest
from sqlalchemy import select
from app.models import BotOwner, BotBooking, BotTurfSlot, BotSession, BotPayoutLedger
from app.services.whatsapp_service import mock_sent_messages, clear_mock_messages as clear_wa
from app.services.telegram_service import mock_telegram_messages, clear_mock_messages as clear_tg


async def send_whatsapp_msg(
    client,
    from_phone: str,
    text: str,
    to_phone: str = "919360756749",
    msg_type: str = "text",
    reply_id: str = None,
    media_id: str = None,
    media_type: str = None,
):
    """Helper to post WhatsApp webhook messages."""
    msg = {
        "from": from_phone,
        "id": f"wamid.mock_{from_phone}_{text[:10]}",
        "timestamp": "1718000000",
        "type": msg_type,
    }
    if msg_type == "text":
        msg["text"] = {"body": text}
    elif msg_type == "interactive":
        msg["interactive"] = {
            "type": "button_reply",
            "button_reply": {"id": reply_id or text, "title": text},
        }
    elif msg_type == "image":
        msg["image"] = {"id": media_id or "media_123", "caption": text}
    elif msg_type == "location":
        # Simulate location coords
        lat, lng = text.replace("location:", "").split(",")
        msg["type"] = "location"
        msg["location"] = {"latitude": float(lat), "longitude": float(lng)}

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "mock_id",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": to_phone,
                        "phone_number_id": to_phone,
                    },
                    "messages": [msg],
                },
                "field": "messages",
            }],
        }],
    }
    return await client.post("/webhook/whatsapp", json=payload)


def assert_wa_message_contains(phone: str, substring: str):
    """Verify that any mock WhatsApp message sent to `phone` contains `substring`."""
    matching = [m for m in mock_sent_messages if m.get("to") == phone]
    assert matching, f"No messages sent to {phone}."
    
    bodies = []
    for m in matching:
        body = ""
        if m.get("type") == "text":
            body = m["text"]["body"]
        elif m.get("type") == "interactive":
            body = m["interactive"].get("body", {}).get("text", "")
            buttons = m["interactive"].get("action", {}).get("buttons", [])
            body += " " + " ".join([b["reply"]["title"] for b in buttons])
            sections = m["interactive"].get("action", {}).get("sections", [])
            for sec in sections:
                body += " " + " ".join([row["title"] for row in sec.get("rows", [])])
                body += " " + " ".join([row.get("description", "") for row in sec.get("rows", [])])
        bodies.append(body.lower())

    assert any(substring.lower() in b for b in bodies), (
        f"Expected substring '{substring}' in any message to {phone}, but not found. Sent messages:\n" + "\n---\n".join(bodies)
    )


@pytest.mark.asyncio
async def test_complete_e2e_flow(client, db_session):
    """Test the complete onboarding, approval, subscription, booking, and payment webhook flow."""
    owner_phone = "919000000000"
    dev_phone = "919876543210"  # Also configured as developer number in conftest
    player_phone = "919999999999"
    onboarding_bot = "919360756749"

    # Clear mock message history
    clear_wa()
    clear_tg()

    # ══════════════════════════════════════════════════════════════
    # 1. OWNER ONBOARDING
    # ══════════════════════════════════════════════════════════════
    
    # 1.1 Initiate onboarding (triggers role selection first)
    resp = await send_whatsapp_msg(client, owner_phone, "hi", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "select your role")

    # Select "I'm an Owner" role
    resp = await send_whatsapp_msg(client, owner_phone, "role_owner", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "Owner Name")

    # 1.2 Send owner name
    resp = await send_whatsapp_msg(client, owner_phone, "Gowtham P", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "Turf Name")

    # 1.3 Send Turf name
    resp = await send_whatsapp_msg(client, owner_phone, "Strikers Turf", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "Location")

    # 1.4 Send Location link
    resp = await send_whatsapp_msg(client, owner_phone, "https://maps.google.com/?q=12.9715987,77.5945627", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "photos")

    # 1.5 Send Photo upload
    resp = await send_whatsapp_msg(client, owner_phone, "turf_pic.jpg", onboarding_bot, msg_type="image", media_id="media_pic_1")
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "received")

    # 1.6 Finish photo uploads
    resp = await send_whatsapp_msg(client, owner_phone, "DONE", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "GST")

    # 1.7 Send GST
    resp = await send_whatsapp_msg(client, owner_phone, "33AAAAA1111A1Z1", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "MSME")

    # 1.8 Skip MSME
    resp = await send_whatsapp_msg(client, owner_phone, "SKIP", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "UPI ID")

    # 1.9 Send UPI ID (Registration complete)
    resp = await send_whatsapp_msg(client, owner_phone, "gowtham@upi", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "Registration Complete")
    assert_wa_message_contains(owner_phone, "please wait for developer approval")

    # Verify owner in DB
    owner = (await db_session.execute(select(BotOwner).where(BotOwner.mobile == owner_phone))).scalars().first()
    assert owner is not None
    assert owner.name == "Gowtham P"
    assert owner.verified is False
    assert owner.subscriptionActive is False

    # ══════════════════════════════════════════════════════════════
    # 2. DEVELOPER APPROVAL
    # ══════════════════════════════════════════════════════════════
    
    # Approve the owner using WhatsApp developer command
    resp = await send_whatsapp_msg(client, dev_phone, f"/approve {owner.id}", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "Approved")
    assert_wa_message_contains(owner_phone, "subscription")

    # Verify owner verified in DB
    await db_session.refresh(owner)
    assert owner.verified is True
    assert owner.subscriptionActive is False

    # ══════════════════════════════════════════════════════════════
    # 3. SUBSCRIPTION PAYMENT
    # ══════════════════════════════════════════════════════════════
    
    sub_payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_sub_123",
                    "notes": {
                        "type": "subscription",
                        "ownerId": str(owner.id),
                    }
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_sub_123",
                    "amount": 69900,  # ₹699 in paise
                }
            }
        }
    }
    resp = await client.post("/razorpay/webhook", json=sub_payload)
    assert resp.status_code == 200

    # Verify owner subscription active in DB
    await db_session.refresh(owner)
    assert owner.subscriptionActive is True
    assert owner.subscriptionExpiry is not None

    # Verify that onboarding session was cleaned up
    session = (await db_session.execute(select(BotSession).where(BotSession.phone == owner_phone))).scalars().first()
    assert session is None

    # ══════════════════════════════════════════════════════════════
    # 4. PLAYER BOOKING FLOW
    # ══════════════════════════════════════════════════════════════
    
    # 4.1 Player sends menu trigger (triggers role selection first)
    resp = await send_whatsapp_msg(client, player_phone, "hi", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "select your role")

    # Select "I'm a Player" role
    resp = await send_whatsapp_msg(client, player_phone, "role_player", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "share your current location")

    # Share location coordinates (match owner's turf coordinates 12.9715987, 77.5945627)
    resp = await send_whatsapp_msg(client, player_phone, "location:12.9715987,77.5945627", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "Strikers Turf")

    # 4.2 Select turf
    resp = await send_whatsapp_msg(client, player_phone, f"select_turf_{owner.id}", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "Select a date")

    # 4.3 Select a date
    resp = await send_whatsapp_msg(client, player_phone, "date_2026-06-15", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "Available slots")

    # 4.4 Select time slot
    resp = await send_whatsapp_msg(client, player_phone, "07:00 PM", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "Name and Team Name")

    # 4.5 Send Team Details
    resp = await send_whatsapp_msg(client, player_phone, "John - HawksFC", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "Sport/Event")

    # 4.6 Send Sport Details (generates payment link)
    resp = await send_whatsapp_msg(client, player_phone, "Football", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(player_phone, "Booking Summary")
    assert_wa_message_contains(player_phone, "Total Amount")
    assert_wa_message_contains(player_phone, "Sport/Event: Football")

    # Verify slot is created/reserved (still status AVAILABLE, session exists)
    session = (await db_session.execute(select(BotSession).where(BotSession.phone == player_phone))).scalars().first()
    assert session is not None
    assert session.state == "AWAITING_PAYMENT_CONFIRMATION"

    # ══════════════════════════════════════════════════════════════
    # 5. WEBHOOK PAYMENT VERIFICATION (HARDENED FLOW)
    # ══════════════════════════════════════════════════════════════
    
    booking_payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_book_123",
                    "notes": {
                        "type": "booking",
                        "ownerId": str(owner.id),
                        "phone": player_phone,
                        "date": "2026-06-15",
                        "slotTime": "07:00 PM",
                        "captainName": "John",
                        "teamName": "HawksFC",
                        "sport": "Football",
                        "expectedTotalPaise": "105000",
                    }
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_book_123",
                    "amount": 105000,  # ₹1050 (₹1000 turf + ₹50 fee)
                }
            }
        }
    }

    # Clear WA history to isolate confirmation messages
    clear_wa()
    
    resp = await client.post("/razorpay/webhook", json=booking_payload)
    assert resp.status_code == 200

    # Verify DB state: Slot is booked, Booking verified, Ledger entry made
    slot = (await db_session.execute(
        select(BotTurfSlot).where(
            BotTurfSlot.ownerId == owner.id,
            BotTurfSlot.date == "2026-06-15",
            BotTurfSlot.timeSlot == "07:00 PM"
        )
    )).scalars().first()
    assert slot is not None
    assert slot.status == "BOOKED"

    booking = (await db_session.execute(
        select(BotBooking).where(BotBooking.razorpayPaymentId == "pay_book_123")
    )).scalars().first()
    assert booking is not None
    assert booking.paymentStatus == "VERIFIED"
    assert booking.totalPaidPaise == 105000
    assert booking.ownerSharePaise == 100000
    assert booking.platformFeePaise == 5000

    ledger = (await db_session.execute(
        select(BotPayoutLedger).where(BotPayoutLedger.bookingId == booking.id)
    )).scalars().first()
    assert ledger is not None
    assert ledger.status in ("COMPLETED", "PROCESSING")  # depending on whether payout service mocked or live (here it uses mock in config)
    assert ledger.idempotencyKey == f"booking_{booking.id}_pay_book_123_{owner.id}"

    # Verify player session cleaned up
    session = (await db_session.execute(select(BotSession).where(BotSession.phone == player_phone))).scalars().first()
    assert session is None

    # Verify customer received confirmation
    assert_wa_message_contains(player_phone, "Booking Confirmed")
    assert_wa_message_contains(player_phone, "₹1050.00")

    # Verify owner received alert
    assert_wa_message_contains(owner_phone, "New Booking Alert")
    assert_wa_message_contains(owner_phone, "Strikers Turf")


    # ══════════════════════════════════════════════════════════════
    # 6. IDEMPOTENCY / SAFETY CHECKS
    # ══════════════════════════════════════════════════════════════
    
    # 6.1 Duplicate webhook trigger - must return 200 silently and not duplicate payout
    clear_tg()
    resp = await client.post("/razorpay/webhook", json=booking_payload)
    assert resp.status_code == 200
    # Duplicate check in audit log / telegram alert
    assert any("duplicate" in msg.get("text", "").lower() for msg in mock_telegram_messages)

    # 6.2 Amount mismatch trigger
    mismatch_payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_book_456",
                    "notes": {
                        "type": "booking",
                        "ownerId": str(owner.id),
                        "phone": player_phone,
                        "date": "2026-06-15",
                        "slotTime": "08:00 PM",
                        "captainName": "John",
                        "teamName": "HawksFC",
                        "sport": "Football",
                        "expectedTotalPaise": "105000",
                    }
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_book_456",
                    "amount": 1050000,  # Paid ₹10500 (extra zero exploit)
                }
            }
        }
    }
    clear_tg()
    resp = await client.post("/razorpay/webhook", json=mismatch_payload)
    assert resp.status_code == 200
    # Telegram alert should have fired
    assert any("amount mismatch" in msg.get("text", "").lower() for msg in mock_telegram_messages)

    # Verify that the booking slot was NOT booked and booking NOT created under VERIFIED status
    failed_booking = (await db_session.execute(
        select(BotBooking).where(BotBooking.razorpayPaymentId == "pay_book_456")
    )).scalars().first()
    assert failed_booking is None


@pytest.mark.asyncio
async def test_owner_onboarding_back_button(client, db_session):
    owner_phone = "919111111111"
    onboarding_bot = "919360756749"

    clear_wa()

    # Initiate onboarding
    resp = await send_whatsapp_msg(client, owner_phone, "hi", onboarding_bot)
    assert resp.status_code == 200

    resp = await send_whatsapp_msg(client, owner_phone, "role_owner", onboarding_bot)
    assert resp.status_code == 200
    assert_wa_message_contains(owner_phone, "Owner Name")

    # Send cancel/back button payload
    resp = await send_whatsapp_msg(client, owner_phone, "cancel_onboarding", onboarding_bot)
    assert resp.status_code == 200

    # It should show role selection menu again
    assert_wa_message_contains(owner_phone, "select your role")

    # The session role should be customer/customer state
    session = (await db_session.execute(
        select(BotSession).where(BotSession.phone == owner_phone)
    )).scalars().first()
    assert session is not None
    assert session.role == "CUSTOMER"
    assert session.state == "ROLE_SELECTION"

