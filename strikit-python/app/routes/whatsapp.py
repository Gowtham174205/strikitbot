"""
WhatsApp Bot — Complete state machine for:
1. Owner onboarding flow
2. Owner commands (revenue, settings, blocking)
3. Player booking flow (centralized + legacy)
4. Single player join flow
5. Captain join request approval
6. Developer WhatsApp commands

Ported from whatsappBot.js (2180 lines) with payment hardening built in.
All money handled via amount_service (paise only).
"""
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BotOwner, BotTurfSlot, BotBooking, BotJoinRequest, BotSession, BotPayoutLedger, BotPaymentAuditLog
from app.services import whatsapp_service, telegram_service, payment_service, amount_service
from app.services.pdf_generator import generate_revenue_report
from app.middleware.security import verify_whatsapp_signature, sanitize_input
from app.middleware.rate_limiter import limiter
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WhatsApp"])


def extract_search_keywords(address: str, turf_name: str) -> str:
    """Extract clean, unique search keywords from address and turf name."""
    if not address:
        address = ""
    if not turf_name:
        turf_name = ""
    text = f"{address} {turf_name}".lower()
    for char in [",", ".", "-", ";", ":", "/", "\\", "(", ")", "[", "]", "#"]:
        text = text.replace(char, " ")
    words = text.split()
    ignored = {
        "no", "near", "opposite", "street", "road", "tamil", "nadu", "india", "and", 
        "the", "pin", "code", "pincode", "behind", "beside", "floor", "door", "block", 
        "sector", "nagar", "city", "town", "district", "state", "turf", "ground", "arena"
    }
    keywords = []
    for w in words:
        w_clean = w.strip()
        if len(w_clean) >= 3 and w_clean not in ignored:
            keywords.append(w_clean)
    seen = set()
    unique_keywords = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique_keywords.append(k)
    return ",".join(unique_keywords)


# ══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ══════════════════════════════════════════════════════════════════

@router.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    """WhatsApp webhook verification challenge (Meta setup)."""
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp Webhook Verified.")
        return JSONResponse(status_code=200, content=int(challenge) if challenge.isdigit() else challenge)
    return JSONResponse(status_code=403, content={"error": "Forbidden"})


@router.post("/webhook/whatsapp", dependencies=[Depends(verify_whatsapp_signature)])
@limiter.limit(settings.RATE_LIMIT_WHATSAPP)
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Main WhatsApp webhook — processes incoming messages."""
    try:
        body = await request.json()
        entry = (body.get("entry") or [{}])[0]
        change = (entry.get("changes") or [{}])[0]
        value = change.get("value", {})

        if value and value.get("messages"):
            message = value["messages"][0]
            from_phone = message["from"]
            to_phone = (
                value.get("metadata", {}).get("phone_number_id")
                or value.get("metadata", {}).get("display_phone_number")
                or settings.ONBOARDING_NUMBER
            )

            text = ""
            media_id = ""
            media_type = ""

            if message.get("type") == "text":
                text = message["text"]["body"]
            elif message.get("type") == "interactive":
                interactive = message["interactive"]
                if interactive.get("type") == "button_reply":
                    text = interactive["button_reply"]["id"]
                elif interactive.get("type") == "list_reply":
                    text = interactive["list_reply"]["id"]
            elif message.get("type") == "image":
                media_id = message["image"]["id"]
                media_type = "image"
                text = message["image"].get("caption", "")
            elif message.get("type") == "document":
                media_id = message["document"]["id"]
                media_type = "document"
                text = message["document"].get("caption", "")
            elif message.get("type") == "location":
                lat = message["location"]["latitude"]
                lng = message["location"]["longitude"]
                text = f"location:{lat},{lng}"

            logger.info(f"[WA] From: {from_phone} → To: {to_phone} | Text: \"{text[:80]}\"")
            await handle_whatsapp_message(from_phone, to_phone, text, db, media_id, media_type)

        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception as e:
        logger.error(f"[WA Webhook Error] {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ══════════════════════════════════════════════════════════════════
# MAIN ROUTING
# ══════════════════════════════════════════════════════════════════

async def show_role_selection(phone: str):
    """Show main welcome role selection buttons to the user."""
    await whatsapp_service.send_buttons(
        phone,
        "👋 *Welcome to STRIKIT!*\n\nPlease select your role to continue:",
        [
            {"id": "role_player", "title": "🏟️ I'm a Player"},
            {"id": "role_owner", "title": "💼 I'm an Owner"},
        ],
    )


async def process_ticket_verification(phone: str, booking_id: int, db: AsyncSession):
    """Processes a QR-code based ticket verification scan from a turf owner."""
    booking = await db.get(BotBooking, booking_id)
    if not booking:
        await whatsapp_service.send_text(phone, "❌ *Invalid Ticket!*\n\nNo booking record found for this ticket ID.")
        return

    slot = await db.get(BotTurfSlot, booking.slotId)
    if not slot:
        await whatsapp_service.send_text(phone, "❌ *Invalid Ticket!*\n\nAssociated turf slot could not be found.")
        return

    owner = await db.get(BotOwner, slot.ownerId)
    if not owner:
        await whatsapp_service.send_text(phone, "❌ *Invalid Ticket!*\n\nAssociated turf owner could not be found.")
        return

    # Check if the sender is the actual turf owner or platform developer/admin
    dev_numbers = settings.developer_numbers_list
    if phone != owner.mobile and phone not in dev_numbers:
        await whatsapp_service.send_text(
            phone,
            f"❌ *Verification Denied!*\n\nYou are not authorized to verify tickets for *{owner.turfName}*.\nOnly the registered owner mobile ({owner.mobile}) can scan and verify this ticket."
        )
        return

    # Prepare status indicators
    status_emoji = "🟢"
    status_text = "PAID & CONFIRMED"
    if booking.status == "CANCELLED":
        status_emoji = "🔴"
        status_text = "CANCELLED"
    elif booking.paymentStatus == "PENDING":
        status_emoji = "🟡"
        status_text = "PAYMENT PENDING"

    # Send verification details
    msg = (
        f"✅ *Booking Ticket Verified!* {status_emoji}\n\n"
        f"• Turf: *{owner.turfName}*\n"
        f"• Slot Time: *{slot.timeSlot}* ({slot.date})\n"
        f"• Captain Name: *{booking.captainName}* ({booking.captainPhone})\n"
        f"• Team Name: *{booking.teamName}*\n"
        f"• Sport/Event: *{booking.sport}*\n"
        f"• Total Paid: *₹{amount_service.paise_to_rupees(booking.totalPaidPaise)}*\n"
        f"• Ticket Status: *{status_text}*\n\n"
        f"_Powered by STRIKIT_"
    )
    await whatsapp_service.send_text(phone, msg)


async def handle_whatsapp_message(
    phone: str, to: str, text: str, db: AsyncSession,
    media_id: str = "", media_type: str = "",
):
    """Central routing for all WhatsApp messages."""
    text = (text or "").strip()
    lower = text.lower().strip()

    # Ticket QR Code Verification Intercept
    if lower.startswith("verify_"):
        booking_id_str = lower.replace("verify_", "").strip()
        if booking_id_str.isdigit():
            booking_id = int(booking_id_str)
            await process_ticket_verification(phone, booking_id, db)
            return

    # Developer commands
    dev_numbers = settings.developer_numbers_list
    if phone in dev_numbers and lower.startswith(("/approve", "/reject", "/deactivate", "/activate")):
        await handle_developer_command(phone, text, db)
        return

    # Direct refund command intercept
    if lower in ("/refund", "/refunt", "refund", "refunt"):
        owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
        if owner:
            if not owner.verified:
                await whatsapp_service.send_text(phone, "⏳ Your turf verification is pending developer approval.")
                return
            
            eligible = False
            now = datetime.utcnow()
            if owner.subscriptionActive:
                ref_date = owner.subscriptionStartedAt or owner.createdAt
                if ref_date and (now - ref_date) <= timedelta(days=7):
                    eligible = True
            
            if not eligible:
                await whatsapp_service.send_text(
                    phone,
                    "⚠️ *Refund Not Allowed* ⚠️\n\n"
                    "Refund requests can only be made within 7 days of subscription activation."
                )
                return

            await whatsapp_service.send_text(
                phone,
                "✍️ Please type the reason for requesting a refund. Tell us why you want to cancel your subscription:"
            )
            await update_session(phone, "AWAITING_OWNER_REFUND_REASON", {"ownerId": owner.id}, db, role="OWNER")
            return

    # Handle subscription renewal button clicks or upgrade commands
    if lower in ("sub_plan_basic", "sub_plan_premium", "sub_plan_prem3m") or lower in ("upgrade", "renew", "owner_upgrade", "owner_renew"):
        owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
        if owner:
            if lower == "sub_plan_basic":
                sub_link = payment_service.create_subscription_link(owner.id, 19900, "BASIC")
                await whatsapp_service.send_text(
                    phone,
                    f"💳 *Subscription Payment Link*\n\n"
                    f"Plan: Basic Plan (₹199 per Month - Basic booking only)\n\n"
                    f"🔗 *Pay here:* {sub_link}\n\n"
                    f"Once paid, your bot will be automatically activated.",
                )
            elif lower == "sub_plan_premium":
                sub_link = payment_service.create_subscription_link(owner.id, 39900, "PREMIUM")
                await whatsapp_service.send_text(
                    phone,
                    f"💳 *Subscription Payment Link*\n\n"
                    f"Plan: Premium Plan (₹399 per Month - All features)\n\n"
                    f"🔗 *Pay here:* {sub_link}\n\n"
                    f"Once paid, your bot will be automatically activated.",
                )
            elif lower == "sub_plan_prem3m":
                sub_link = payment_service.create_subscription_link(owner.id, 74900, "PREMIUM_3M")
                await whatsapp_service.send_text(
                    phone,
                    f"💳 *Subscription Payment Link*\n\n"
                    f"Plan: Premium 3-Month Plan (₹749 for 3 Months - All features)\n\n"
                    f"🔗 *Pay here:* {sub_link}\n\n"
                    f"Once paid, your bot will be automatically activated.",
                )
            else:
                # upgrade / renew / owner_upgrade / owner_renew text commands
                await whatsapp_service.send_buttons(
                    phone,
                    f"👋 Hello {owner.name}!\n\nSelect a subscription plan to renew or upgrade *{owner.turfName}*:",
                    [
                        {"id": "sub_plan_basic", "title": "₹199 Basic (1M)"},
                        {"id": "sub_plan_premium", "title": "₹399 Premium (1M)"},
                        {"id": "sub_plan_prem3m", "title": "₹749 Premium (3M)"},
                    ]
                )
            return

    # Centralized routing (single bot number)
    if to == settings.ONBOARDING_NUMBER or to == settings.WHATSAPP_PHONE_NUMBER_ID:
        # Player Deep-Link Handler (book_{owner_id})
        if lower.startswith("book_"):
            try:
                owner_id = int(lower.replace("book_", ""))
                owner = await db.get(BotOwner, owner_id)
                if not owner:
                    await whatsapp_service.send_text(phone, "❌ Turf not found. Please type *menu* to see available turfs.")
                    return

                context = {
                    "ownerId": owner.id,
                    "turfName": owner.turfName
                }

                caption_text = (
                    f"🏟️ *{owner.turfName}* 🏟️\n\n"
                    f"📍 *Address:* {owner.address or 'Address not configured'}\n"
                    f"💰 *Rate:* ₹{amount_service.paise_to_rupees(owner.pricePerHourPaise)}/hour\n"
                    f"⏰ *Timings:* {owner.openingTime} - {owner.closingTime}\n"
                    f"🗺️ *Google Maps:* {owner.location}"
                )

                photo_sent = False
                if owner.photoUrls:
                    photos = [p.strip() for p in owner.photoUrls.split(",") if p.strip()]
                    if photos:
                        try:
                            await whatsapp_service.send_image(phone, photos[0], caption_text)
                            photo_sent = True
                        except Exception as img_err:
                            logger.error(f"[DeepLink] Failed to send photo: {img_err}")

                if not photo_sent:
                    await whatsapp_service.send_text(phone, caption_text)

                dates = []
                for i in range(7):
                    d = datetime.utcnow() + timedelta(days=i)
                    dates.append(d.strftime("%Y-%m-%d"))

                sections = [{
                    "title": "Available Dates",
                    "rows": [{"id": f"date_{d}", "title": d, "description": ""} for d in dates],
                }]

                await whatsapp_service.send_list(
                    phone,
                    f"📅 Select a date to book at *{owner.turfName}*:",
                    "📅 Select Date",
                    sections,
                )
                await update_session(phone, "AWAITING_DATE_SELECTION", context, db, role="CUSTOMER")
                return
            except ValueError:
                pass

        # If they send 'hi' / 'hello' / 'menu' / '/menu', show role selection or owner menu
        if lower in ("hi", "hello", "menu", "/menu"):
            owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
            if owner and owner.verified:
                await update_session(phone, "OWNER_START", {"ownerId": owner.id}, db, role="OWNER")
                return await handle_owner_commands(phone, text, owner, db, media_id, media_type)
            await update_session(phone, "ROLE_SELECTION", {}, db, role="CUSTOMER")
            await show_role_selection(phone)
            return

        # Handle back to roles action
        if lower == "back_to_roles":
            await update_session(phone, "ROLE_SELECTION", {}, db, role="CUSTOMER")
            await show_role_selection(phone)
            return

        # Handle role selection button click
        if lower == "role_player":
            await update_session(phone, "PLAYER_START", {}, db, role="CUSTOMER")
            return await handle_player_flow(phone, "hi", db)

        if lower == "role_owner":
            owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
            if owner:
                # Subscription and verification check
                if owner.subscriptionActive and owner.subscriptionExpiry:
                    if datetime.utcnow() > owner.subscriptionExpiry:
                        owner.subscriptionActive = False
                        await db.commit()

                if not owner.verified:
                    return await whatsapp_service.send_text(phone, "⏳ Your turf verification is pending developer approval.")

                if not owner.subscriptionActive:
                    if owner.subscriptionExpiry is None:
                        sub_link = payment_service.create_subscription_link(owner.id, 69900, "TRIAL")
                        return await whatsapp_service.send_text(
                            phone,
                            f"💳 Please complete your onboarding subscription payment to activate (₹699 for 3 Months):\n{sub_link}\n\n_Powered by STRIKIT_",
                        )
                    else:
                        await whatsapp_service.send_buttons(
                            phone,
                            f"⚠️ *STRIKIT Subscription Expired* ⚠️\n\n"
                            f"Dear {owner.name}, your subscription for *{owner.turfName}* has expired.\n\n"
                            f"Please select a renewal plan below:",
                            [
                                {"id": "sub_plan_basic", "title": "₹199 Basic (1 Month)"},
                                {"id": "sub_plan_premium", "title": "₹399 Premium (1 Month)"},
                                {"id": "sub_plan_prem3m", "title": "₹749 Premium (3 Month)"},
                            ]
                        )
                        return

                # Route to owner dashboard
                await update_session(phone, "OWNER_START", {}, db, role="OWNER")
                return await handle_owner_commands(phone, "hi", owner, db, media_id, media_type)
            else:
                # Clean existing onboarding sessions
                sessions = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().all()
                for s in sessions:
                    await db.delete(s)
                await db.commit()
                # Start onboarding flow
                await update_session(phone, "ONBOARDING_START", {}, db, role="ONBOARDING")
                return await handle_onboarding_flow(phone, "Hi", db, media_id, media_type)

        # Get existing session
        session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()

        # Auto-detect verified active/inactive turf owners
        owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
        if owner and owner.verified:
            if not session or session.role != "OWNER":
                session = await update_session(phone, "OWNER_START", {"ownerId": owner.id}, db, role="OWNER")

        # Handle back/cancel command inside onboarding flow
        if session and session.role == "ONBOARDING" and lower in ("cancel", "/cancel", "back", "cancel_onboarding"):
            await update_session(phone, "ROLE_SELECTION", {}, db, role="CUSTOMER")
            await show_role_selection(phone)
            return

        if session:
            if session.role == "ONBOARDING":
                return await handle_onboarding_flow(phone, text, db, media_id, media_type)

            if session.role == "OWNER":
                owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
                if owner:
                    # Sync subscription status
                    if owner.subscriptionActive and owner.subscriptionExpiry:
                        if datetime.utcnow() > owner.subscriptionExpiry:
                            owner.subscriptionActive = False
                            await db.commit()

                    if not owner.subscriptionActive:
                        if owner.subscriptionExpiry is None:
                            sub_link = payment_service.create_subscription_link(owner.id, 69900, "TRIAL")
                            return await whatsapp_service.send_text(
                                phone,
                                f"💳 Please complete your onboarding subscription payment to activate (₹699 for 3 Months):\n{sub_link}\n\n_Powered by STRIKIT_",
                            )
                        else:
                            await whatsapp_service.send_buttons(
                                phone,
                                f"⚠️ *STRIKIT Subscription Expired* ⚠️\n\n"
                                f"Dear {owner.name}, your subscription for *{owner.turfName}* has expired.\n\n"
                                f"Please select a renewal plan below:",
                                [
                                    {"id": "sub_plan_basic", "title": "₹199 Basic (1 Month)"},
                                    {"id": "sub_plan_premium", "title": "₹399 Premium (1 Month)"},
                                    {"id": "sub_plan_prem3m", "title": "₹749 Premium (3 Month)"},
                                ]
                            )
                            return

                    return await handle_owner_commands(phone, text, owner, db, media_id, media_type)

            # Player flow handles customer sessions
            return await handle_player_flow(phone, text, db)

        # Captain approval check
        if await handle_captain_approval(phone, text, None, db):
            return

        # Fallback: show role selection
        await update_session(phone, "ROLE_SELECTION", {}, db, role="CUSTOMER")
        await show_role_selection(phone)


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geodesic distance between two points in km."""
    import math
    R = 6371.0  # Earth radius in km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat / 2) * math.sin(dLat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon / 2) * math.sin(dLon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


async def extract_coordinates_from_url(url: str) -> dict:
    """Resolve redirect and extract coordinates from a Google Maps link."""
    import re
    import httpx
    at_regex = r'@(-?\d+\.\d+),(-?\d+\.\d+)'
    q_regex = r'[?&](q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)'
    
    # Try direct parse
    match = re.search(at_regex, url)
    if match:
        return {"latitude": float(match.group(1)), "longitude": float(match.group(2))}
        
    match = re.search(q_regex, url)
    if match:
        return {"latitude": float(match.group(2)), "longitude": float(match.group(3))}
        
    # Resolve redirect
    if any(domain in url for domain in ['goo.gl', 'maps.app.goo.gl', 'maps.google.com', 'google.com/maps']):
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36'
                })
                target_url = str(resp.url)
                match = re.search(at_regex, target_url)
                if match:
                    return {"latitude": float(match.group(1)), "longitude": float(match.group(2))}
                match = re.search(q_regex, target_url)
                if match:
                    return {"latitude": float(match.group(2)), "longitude": float(match.group(3))}
        except Exception as e:
            logger.error(f"Error resolving Google Maps URL: {e}")
            
    return None


# ══════════════════════════════════════════════════════════════════
# SESSION HELPER
# ══════════════════════════════════════════════════════════════════

async def update_session(phone: str, state: str, context: dict, db: AsyncSession, role: str = None):
    """Update or create a bot session."""
    session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()
    ctx_json = json.dumps(context)
    if session:
        session.state = state
        session.context = ctx_json
        if role:
            session.role = role
        session.updatedAt = datetime.utcnow()
    else:
        db.add(BotSession(phone=phone, role=role or "CUSTOMER", state=state, context=ctx_json))
    await db.commit()


# ══════════════════════════════════════════════════════════════════
# ONBOARDING STATE MACHINE
# ══════════════════════════════════════════════════════════════════

async def handle_onboarding_flow(
    phone: str, text: str, db: AsyncSession,
    media_id: str = "", media_type: str = "",
):
    """Owner onboarding state machine."""
    # Prevent duplicate registrations for the same phone number
    existing_owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
    if existing_owner:
        await whatsapp_service.send_text(
            phone,
            f"⚠️ *Already Registered*\n\nYour mobile number is already registered for turf *{existing_owner.turfName}*.\n\nYou cannot register again."
        )
        # Reset session to owner dashboard
        await update_session(phone, "OWNER_START", {}, db, role="OWNER")
        return

    session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()

    if not session or session.role != "ONBOARDING":
        session_obj = BotSession(phone=phone, role="ONBOARDING", state="ONBOARDING_START", context="{}")
        db.add(session_obj)
        await db.commit()
        session = session_obj

    context = json.loads(session.context or "{}")
    state = session.state
    lower = text.lower().strip()

    if state == "ONBOARDING_START":
        await whatsapp_service.send_buttons(
            phone,
            "Welcome to STRIKIT Onboarding! Let's get your turf set up.\n\nPlease enter the *Owner Name*:",
            [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
        )
        await update_session(phone, "AWAITING_OWNER_NAME", context, db, role="ONBOARDING")

    elif state == "AWAITING_OWNER_NAME":
        context["ownerName"] = sanitize_input(text, 100)
        await whatsapp_service.send_buttons(
            phone,
            f"Thank you, {context['ownerName']}. Now, please enter your *Turf Name*:",
            [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
        )
        await update_session(phone, "AWAITING_TURF_NAME", context, db)

    elif state == "AWAITING_TURF_NAME":
        context["turfName"] = sanitize_input(text, 100)
        await whatsapp_service.send_buttons(
            phone,
            f'Got it: "{text}". Now, please enter the *full address* of the turf (e.g. Street, Area, City, Pincode):',
            [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
        )
        await update_session(phone, "AWAITING_ADDRESS", context, db)

    elif state == "AWAITING_ADDRESS":
        context["address"] = sanitize_input(text, 250)
        await whatsapp_service.send_buttons(
            phone,
            "Address saved. Now, please enter the *Location* as a Google Maps link:",
            [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
        )
        await update_session(phone, "AWAITING_LOCATION", context, db)

    elif state == "AWAITING_LOCATION":
        context["location"] = sanitize_input(text, 500)
        # Try to extract lat/lng from Google Maps URL
        coords = await extract_coordinates_from_url(text)
        if coords:
            context["latitude"] = coords["latitude"]
            context["longitude"] = coords["longitude"]
        await whatsapp_service.send_buttons(
            phone,
            "Please upload your *turf photos* (send as images). Click Done when finished:",
            [
                {"id": "onboarding_photos_done", "title": "✅ Done Uploading"},
                {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
            ]
        )
        context["photoUrls"] = []
        await update_session(phone, "AWAITING_PHOTOS", context, db)

    elif state == "AWAITING_PHOTOS":
        if text.upper() == "DONE" or lower == "onboarding_photos_done":
            photos = context.get("photoUrls", [])
            if not photos:
                context["photoUrls"] = "No photos uploaded"
            else:
                context["photoUrls"] = ", ".join(photos)
            await whatsapp_service.send_buttons(
                phone,
                "Enter your *GST Number*:",
                [
                    {"id": "onboarding_gst_skip", "title": "⏭️ Skip GST"},
                    {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
                ]
            )
            await update_session(phone, "AWAITING_GST", context, db)
        elif media_id and media_type == "image":
            media_url = await whatsapp_service.download_whatsapp_media(media_id, "photos")
            photos = context.get("photoUrls", [])
            photos.append(media_url)
            context["photoUrls"] = photos
            await whatsapp_service.send_buttons(
                phone,
                f"📷 Photo {len(photos)} received! Send more or click Done.",
                [
                    {"id": "onboarding_photos_done", "title": "✅ Done Uploading"},
                    {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
                ]
            )
            await update_session(phone, "AWAITING_PHOTOS", context, db)
        else:
            await whatsapp_service.send_buttons(
                phone,
                "Please send photos as images, or click Done to continue.",
                [
                    {"id": "onboarding_photos_done", "title": "✅ Done Uploading"},
                    {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
                ]
            )

    elif state == "AWAITING_GST":
        context["gst"] = None if text.upper() == "SKIP" or lower == "onboarding_gst_skip" else sanitize_input(text, 50)
        await whatsapp_service.send_buttons(
            phone,
            "Please upload your *MSME Certificate* as a photo or PDF document:",
            [
                {"id": "onboarding_msme_skip", "title": "⏭️ Skip MSME"},
                {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
            ]
        )
        await update_session(phone, "AWAITING_MSME", context, db)

    elif state == "AWAITING_MSME":
        if lower == "onboarding_msme_skip" or text.upper() == "SKIP":
            context["msme"] = None
            context["msmeCardUrl"] = None
        elif media_id and media_type in ("image", "document"):
            media_url = await whatsapp_service.download_whatsapp_media(media_id, "msme")
            context["msme"] = "Uploaded File"
            context["msmeCardUrl"] = media_url
        else:
            await whatsapp_service.send_buttons(
                phone,
                "⚠️ Invalid input. Please upload a photo or PDF of your *MSME Certificate*, or click Skip:",
                [
                    {"id": "onboarding_msme_skip", "title": "⏭️ Skip MSME"},
                    {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
                ]
            )
            return

        await whatsapp_service.send_buttons(
            phone,
            "Please upload your *Utility Bill* (e.g. EB, water, postpaid, fiber bill) as a photo or PDF:",
            [
                {"id": "onboarding_utility_skip", "title": "⏭️ Skip Utility"},
                {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
            ]
        )
        await update_session(phone, "AWAITING_UTILITY_BILL", context, db)

    elif state == "AWAITING_UTILITY_BILL":
        if lower == "onboarding_utility_skip" or text.upper() == "SKIP":
            context["utilityBillUrl"] = None
        elif media_id and media_type in ("image", "document"):
            media_url = await whatsapp_service.download_whatsapp_media(media_id, "utility")
            context["utilityBillUrl"] = media_url
        else:
            await whatsapp_service.send_buttons(
                phone,
                "⚠️ Invalid input. Please upload a photo or PDF of your *Utility Bill*, or click Skip:",
                [
                    {"id": "onboarding_utility_skip", "title": "⏭️ Skip Utility"},
                    {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
                ]
            )
            return

        await whatsapp_service.send_buttons(
            phone,
            "Enter your *UPI ID* for receiving payouts (e.g. name@upi):",
            [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
        )
        await update_session(phone, "AWAITING_UPI", context, db)

    elif state == "AWAITING_UPI":
        context["upiId"] = sanitize_input(text, 100)

        # Validate UPI format
        if not amount_service.validate_upi_id(context["upiId"]):
            await whatsapp_service.send_buttons(
                phone,
                "⚠️ Invalid UPI format. Please enter a UPI ID for payouts (e.g. name@upi):",
                [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
            )
            return

        # Create owner record
        photo_str = context.get("photoUrls", "")
        if isinstance(photo_str, list):
            photo_str = ", ".join(photo_str)

        owner = BotOwner(
            name=context["ownerName"],
            mobile=phone,
            turfName=context["turfName"],
            location=context["location"],
            photoUrls=photo_str,
            gst=context.get("gst"),
            msme=context.get("msme"),
            msmeCardUrl=context.get("msmeCardUrl"),
            utilityBillUrl=context.get("utilityBillUrl"),
            upiId=context["upiId"],
            pricePerHourPaise=100000,  # Default ₹1000
            latitude=context.get("latitude"),
            longitude=context.get("longitude"),
            address=context.get("address"),
            searchKeywords=extract_search_keywords(context.get("address", ""), context["turfName"]),
        )
        db.add(owner)
        await db.flush()

        context["ownerId"] = owner.id
        await update_session(phone, "AWAITING_VERIFICATION", context, db)

        await whatsapp_service.send_text(
            phone,
            f"✅ *Registration Complete!*\n\n"
            f"Your details have been submitted for verification:\n"
            f"• Name: {owner.name}\n"
            f"• Turf: {owner.turfName}\n"
            f"• UPI: {owner.upiId}\n\n"
            f"⏳ Please wait for developer approval.\n\n_Powered by STRIKIT_",
        )

        # Notify developers
        await whatsapp_service.send_developer_verification_alert(owner)
        await telegram_service.send_verification_alert(owner)
        
        # FCM Push Notification
        try:
            from app.services.fcm_service import send_fcm_notification
            send_fcm_notification(
                title="New Turf Onboarding 🏟️",
                body=f"Owner {owner.name} registered {owner.turfName}. Awaiting approval."
            )
        except Exception as e:
            logger.error(f"[Onboarding FCM] Failed: {e}")

        await db.commit()


    elif state == "AWAITING_VERIFICATION":
        await whatsapp_service.send_text(phone, "⏳ Your verification is still pending. We'll notify you once approved!")

    elif state == "AWAITING_SUBSCRIPTION":
        owner_id = context.get("ownerId")
        if owner_id:
            sub_link = payment_service.create_subscription_link(owner_id)
            await whatsapp_service.send_text(
                phone,
                f"💳 Please complete your subscription payment to activate:\n{sub_link}\n\n_Powered by STRIKIT_",
            )


# ══════════════════════════════════════════════════════════════════
# OWNER COMMANDS
# ══════════════════════════════════════════════════════════════════

async def handle_owner_commands(
    phone: str, text: str, owner: BotOwner, db: AsyncSession,
    media_id: str = "", media_type: str = "",
):
    """Handle commands from verified, subscribed owners."""
    lower = text.lower().strip()

    # Refund request command inside owner commands
    if lower in ("owner_refund", "/refund", "refund", "/refunt", "refunt"):
        from datetime import timedelta
        eligible = False
        now = datetime.utcnow()
        if owner.subscriptionActive:
            ref_date = owner.subscriptionStartedAt or owner.createdAt
            if ref_date and (now - ref_date) <= timedelta(days=7):
                eligible = True
        
        if not eligible:
            await whatsapp_service.send_text(
                phone,
                "⚠️ *Refund Not Allowed* ⚠️\n\n"
                "Refund requests can only be made within 7 days of subscription activation."
            )
            return

        await whatsapp_service.send_text(
            phone,
            "✍️ Please type the reason for requesting a refund. Tell us why you want to cancel your subscription:"
        )
        await update_session(phone, "AWAITING_OWNER_REFUND_REASON", {"ownerId": owner.id}, db, role="OWNER")
        return

    # Enforce Basic plan limits
    if owner.subscriptionPlan == "BASIC":
        # Get active session
        session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()
        if session and session.state.startswith("OWNER_") and session.state != "OWNER_START":
            # Reset session to OWNER_START to prevent getting stuck in setting inputs
            await db.delete(session)
            await db.commit()

        # Intercept setting/revenue commands
        if lower in (
            "owner_revenue", "/revenue", "revenue",
            "owner_settings", "/settings", "settings",
            "set_price", "set_upi", "set_timing", "block_slot"
        ):
            await whatsapp_service.send_text(
                phone,
                f"⚠️ *Feature Locked* ⚠️\n\n"
                f"This feature requires a STRIKIT Premium Plan.\n\n"
                f"To unlock revenue reports, blocking slots, and settings management, please type *upgrade* to choose a premium plan."
            )
            return

    # Menu
    if lower in ("hi", "hello", "menu", "/menu", "help"):
        if owner.subscriptionPlan == "BASIC":
            buttons = [
                {"id": "owner_bookings", "title": "📋 Today's Bookings"},
                {"id": "owner_upgrade", "title": "⭐ Upgrade Plan"},
            ]
        else:
            buttons = [
                {"id": "owner_bookings", "title": "📋 Today's Bookings"},
                {"id": "owner_revenue", "title": "📊 Revenue Report"},
                {"id": "owner_settings", "title": "⚙️ Settings"},
            ]

        await whatsapp_service.send_buttons(
            phone,
            f"👋 Welcome, {owner.name}!\n\n*{owner.turfName}* Owner Dashboard\n\nSelect an option:",
            buttons,
        )
        return

    # Today's bookings
    if lower in ("owner_bookings", "/bookings", "bookings"):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        slots = (await db.execute(
            select(BotTurfSlot).where(BotTurfSlot.ownerId == owner.id, BotTurfSlot.date == today)
        )).scalars().all()

        if not slots:
            await whatsapp_service.send_text(phone, f"📋 No bookings for today ({today}).")
            return

        msg = f"📋 *Today's Bookings ({today})*\n\n"
        for slot in slots:
            bookings = (await db.execute(
                select(BotBooking).where(BotBooking.slotId == slot.id, BotBooking.paymentStatus == "VERIFIED")
            )).scalars().all()

            status_emoji = "🟢" if slot.status == "BOOKED" else "⚪" if slot.status == "AVAILABLE" else "🔴"
            msg += f"{status_emoji} *{slot.timeSlot}* — {slot.status}\n"
            for b in bookings:
                msg += f"   Team: {b.teamName} | Captain: {b.captainName}\n"
                msg += f"   Paid: ₹{amount_service.paise_to_rupees(b.totalPaidPaise)}\n"

        await whatsapp_service.send_text(phone, msg + "\n_Powered by STRIKIT_")
        return

    # Revenue report
    if lower in ("owner_revenue", "/revenue", "revenue"):
        import os
        slots = (await db.execute(
            select(BotTurfSlot).where(BotTurfSlot.ownerId == owner.id)
        )).scalars().all()
        slot_ids = [s.id for s in slots]

        bookings = []
        if slot_ids:
            bookings = (await db.execute(
                select(BotBooking).where(
                    BotBooking.slotId.in_(slot_ids),
                    BotBooking.paymentStatus == "VERIFIED",
                )
            )).scalars().all()

        total_paise = sum(b.totalPaidPaise for b in bookings)
        fees_paise = sum(b.platformFeePaise for b in bookings)
        net_paise = total_paise - fees_paise

        msg = (
            f"📊 *Revenue Summary — {owner.turfName}*\n\n"
            f"• Total Bookings: {len(bookings)}\n"
            f"• Gross Revenue: ₹{amount_service.paise_to_rupees(total_paise)}\n"
            f"• Platform Fees: ₹{amount_service.paise_to_rupees(fees_paise)}\n"
            f"• *Net Earnings: ₹{amount_service.paise_to_rupees(net_paise)}*\n\n"
            f"_Powered by STRIKIT_"
        )
        await whatsapp_service.send_text(phone, msg)

        # Generate PDF
        try:
            reports_dir = os.path.join(os.getcwd(), "reports")
            pdf_path = generate_revenue_report(owner, bookings, reports_dir)
            import os
            base_url = settings.BASE_URL if hasattr(settings, 'BASE_URL') and settings.BASE_URL else 'https://bot.strikit.in'
            await whatsapp_service.send_document(
                phone,
                f"{base_url}/reports/{os.path.basename(pdf_path)}",
                f"revenue_report_{owner.id}.pdf",
                "📄 Detailed revenue report attached.",
            )
        except Exception as e:
            logger.error(f"[Owner Revenue] PDF generation error: {e}")

        return

    # Settings
    if lower in ("owner_settings", "/settings", "settings"):
        await whatsapp_service.send_list(
            phone,
            f"⚙️ *Settings — {owner.turfName}*\n\nCurrent Config:\n"
            f"• Price/Hour: ₹{amount_service.paise_to_rupees(owner.pricePerHourPaise)}\n"
            f"• Opening: {owner.openingTime}\n"
            f"• Closing: {owner.closingTime}\n"
            f"• UPI: {owner.upiId or 'Not set'}\n",
            "Change Settings",
            [{
                "title": "Settings",
                "rows": [
                    {"id": "set_price", "title": "💰 Change Price", "description": "Set hourly rate"},
                    {"id": "set_timing", "title": "⏰ Change Timings", "description": "Opening/closing hours"},
                    {"id": "set_upi", "title": "🏦 Change UPI ID", "description": "Payout UPI address"},
                    {"id": "block_slot", "title": "🔒 Block Slot", "description": "Block a time slot"},
                    {"id": "get_qr", "title": "🖼️ Get Booking QR & Link", "description": "Download turf QR Code & Link"},
                ],
            }],
        )
        return

    # Settings actions
    session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()

    if lower == "get_qr":
        import urllib.parse
        wa_link = f"https://wa.me/{settings.ONBOARDING_NUMBER}?text=book_{owner.id}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_link)}"
        await whatsapp_service.send_image(
            phone,
            qr_url,
            caption=(
                f"🏟️ *Your Turf Booking QR Code & Direct Link* 🏟️\n\n"
                f"• Turf Name: *{owner.turfName}*\n"
                f"• Hourly Price: ₹{amount_service.paise_to_rupees(owner.pricePerHourPaise)}/hr\n"
                f"• Timings: {owner.openingTime} - {owner.closingTime}\n\n"
                f"🔗 *Your Direct Booking Link:* \n"
                f"{wa_link}\n\n"
                f"Print this QR code and display it at your turf entrance, or share your booking link on Instagram/WhatsApp!"
            )
        )
        return

    if session and session.state == "AWAITING_OWNER_REFUND_REASON":
        reason_text = text.strip()
        if not reason_text:
            await whatsapp_service.send_text(phone, "Please enter a valid reason:")
            return

        from app.models.bot_owner_refund_request import BotOwnerRefundRequest
        refund_req = BotOwnerRefundRequest(
            ownerId=owner.id,
            reason=reason_text,
            status="PENDING",
            createdAt=datetime.utcnow()
        )
        db.add(refund_req)
        await db.delete(session)
        await db.commit()

        # Send Telegram alert to admin
        try:
            alert_msg = (
                f"🚨 *NEW REFUND REQUEST* 🚨\n\n"
                f"👤 *Owner:* {owner.name}\n"
                f"📞 *Mobile:* {owner.mobile}\n"
                f"🏟️ *Turf:* {owner.turfName}\n"
                f"📅 *Activated:* {owner.subscriptionStartedAt.strftime('%Y-%m-%d %H:%M') if owner.subscriptionStartedAt else 'N/A'}\n"
                f"💬 *Reason:* {reason_text}"
            )
            await telegram_service.send_alert(alert_msg)
            
            # FCM Push Notification
            from app.services.fcm_service import send_fcm_notification
            send_fcm_notification(
                title="New Refund Request 💳",
                body=f"{owner.name} ({owner.turfName}) requested a refund: {reason_text[:100]}"
            )
        except Exception as e:
            logger.error(f"[Owner Refund Alert] Failed: {e}")

        await whatsapp_service.send_text(
            phone,
            "✅ *Refund Request Submitted*\n\n"
            "Your request has been sent to the STRIKIT Admin team for manual review. "
            "We will get back to you shortly."
        )
        return

    # Guided Owner Setup Flow (Post-Payment)
    if session and session.state == "OWNER_SETUP_PRICE":
        try:
            context = json.loads(session.context) if session.context else {}
            price = int(text.strip())
            paise = amount_service.rupees_to_paise(price)
            if paise < 10000 or paise > 5000000:
                await whatsapp_service.send_text(phone, "⚠️ Price must be between ₹100 and ₹50,000. Please enter again:")
                return
            owner.pricePerHourPaise = paise
            context["pricePerHourPaise"] = paise
            await whatsapp_service.send_text(
                phone,
                f"✅ *Price Set: ₹{price}/hour*\n\n"
                f"Next, please enter your turf's **Operating Timings** (Format: `06:00 AM - 10:00 PM`):"
            )
            await update_session(phone, "OWNER_SETUP_TIMING", context, db, role="OWNER")
        except ValueError:
            await whatsapp_service.send_text(phone, "⚠️ Please enter a valid number (e.g. 1200):")
        return

    if session and session.state == "OWNER_SETUP_TIMING":
        parts = text.split("-")
        if len(parts) >= 2:
            opening = parts[0].strip()
            closing = parts[1].strip()
            try:
                from datetime import datetime as dt
                dt.strptime(opening, "%I:%M %p")
                dt.strptime(closing, "%I:%M %p")
            except Exception:
                await whatsapp_service.send_text(phone, "⚠️ Inconsistent timing format. Please enter in this format: `06:00 AM - 10:00 PM`:")
                return

            owner.openingTime = opening
            owner.closingTime = closing
            await db.delete(session)
            await db.commit()

            import urllib.parse
            wa_link = f"https://wa.me/{settings.ONBOARDING_NUMBER}?text=book_{owner.id}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_link)}"
            await whatsapp_service.send_image(
                phone,
                qr_url,
                caption=(
                    f"🎉 *Setup Complete! Turf is Live!* 🎉\n\n"
                    f"All settings have been successfully saved for *{owner.turfName}*:\n"
                    f"• Price/Hour: ₹{amount_service.paise_to_rupees(owner.pricePerHourPaise)}/hr\n"
                    f"• Timings: {owner.openingTime} - {owner.closingTime}\n\n"
                    f"🔗 *Your Direct Booking Link:* \n"
                    f"{wa_link}\n\n"
                    f"Print this QR code and display it at your turf entrance, or share your booking link on Instagram/WhatsApp!"
                )
            )
        else:
            await whatsapp_service.send_text(phone, "⚠️ Inconsistent timing format. Please enter in this format: `06:00 AM - 10:00 PM`:")
        return

    if lower == "set_price":
        if not owner.subscriptionActive:
            await whatsapp_service.send_text(
                phone,
                "⚠️ *Subscription Required*\n\nYou can only set or change your hourly price after paying and activating your subscription! Please complete your subscription payment first."
            )
            return
        await whatsapp_service.send_text(phone, "Enter new hourly price in Rupees (e.g. 1500):")
        await update_session(phone, "OWNER_SET_PRICE", {"ownerId": owner.id}, db, role="OWNER")
        return

    if session and session.state == "OWNER_SET_PRICE":
        try:
            new_price = int(text.strip())
            new_paise = amount_service.rupees_to_paise(new_price)
            if new_paise < 10000 or new_paise > 5000000:  # ₹100 to ₹50,000
                await whatsapp_service.send_text(phone, "Price must be between ₹100 and ₹50,000.")
                return
            owner.pricePerHourPaise = new_paise
            await db.delete(session)
            await db.commit()
            await whatsapp_service.send_text(phone, f"✅ Price updated to ₹{amount_service.paise_to_rupees(new_paise)}/hour")
        except ValueError:
            await whatsapp_service.send_text(phone, "Please enter a valid number (e.g. 1500):")
        return

    if lower == "set_upi":
        await whatsapp_service.send_text(phone, "Enter new UPI ID (e.g. name@upi):")
        await update_session(phone, "OWNER_SET_UPI", {"ownerId": owner.id}, db, role="OWNER")
        return

    if session and session.state == "OWNER_SET_UPI":
        new_upi = text.strip()
        if not amount_service.validate_upi_id(new_upi):
            await whatsapp_service.send_text(phone, "⚠️ Invalid UPI format. Please try again:")
            return
        owner.upiId = new_upi
        owner.razorpayFundAccountId = None  # Reset cached fund account
        await db.delete(session)
        await db.commit()
        await whatsapp_service.send_text(phone, f"✅ UPI updated to {new_upi}")
        return

    if lower == "set_timing":
        await whatsapp_service.send_text(phone, "Enter opening and closing time (e.g. 06:00 AM - 10:00 PM):")
        await update_session(phone, "OWNER_SET_TIMING", {"ownerId": owner.id}, db, role="OWNER")
        return

    if session and session.state == "OWNER_SET_TIMING":
        parts = text.split("-")
        if len(parts) >= 2:
            owner.openingTime = parts[0].strip()
            owner.closingTime = parts[1].strip()
            await db.delete(session)
            await db.commit()
            await whatsapp_service.send_text(phone, f"✅ Timings updated: {owner.openingTime} - {owner.closingTime}")
        else:
            await whatsapp_service.send_text(phone, "Format: 06:00 AM - 10:00 PM")
        return

    if lower == "block_slot":
        await whatsapp_service.send_text(phone, "Enter date and time to block (e.g. 2026-06-15 07:00 PM):")
        await update_session(phone, "OWNER_BLOCK_SLOT", {"ownerId": owner.id}, db, role="OWNER")
        return

    if session and session.state == "OWNER_BLOCK_SLOT":
        parts = text.strip().split(" ", 1)
        if len(parts) >= 2:
            date_str = parts[0]
            time_str = parts[1] if len(parts) > 1 else ""
            slot = (await db.execute(
                select(BotTurfSlot).where(
                    BotTurfSlot.ownerId == owner.id,
                    BotTurfSlot.date == date_str,
                    BotTurfSlot.timeSlot == time_str,
                )
            )).scalars().first()

            if slot:
                slot.status = "BLOCKED"
                slot.blockedByOwner = True
            else:
                db.add(BotTurfSlot(ownerId=owner.id, date=date_str, timeSlot=time_str, status="BLOCKED", blockedByOwner=True))

            await db.delete(session)
            await db.commit()
            await whatsapp_service.send_text(phone, f"🔒 Slot blocked: {date_str} at {time_str}")
        else:
            await whatsapp_service.send_text(phone, "Format: 2026-06-15 07:00 PM")
        return

    # Default: show menu
    await whatsapp_service.send_text(phone, "Type *menu* to see available commands.")


# ══════════════════════════════════════════════════════════════════
# PLAYER BOOKING FLOW (Centralized)
# ══════════════════════════════════════════════════════════════════

async def handle_player_flow(phone: str, text: str, db: AsyncSession):
    """Handle player booking flow on the centralized STRIKIT number."""
    lower = text.lower().strip()
    session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()

    # ── Cancellation Flow Interceptors ──
    if text.startswith("cancel_select_"):
        booking_id = int(text.replace("cancel_select_", ""))
        booking = await db.get(BotBooking, booking_id)
        if not booking:
            await whatsapp_service.send_text(phone, "❌ Booking not found.")
            return

        sections = [
            {
                "title": "Cancellation Reasons",
                "rows": [
                    {"id": f"cancel_reason_{booking_id}_plans", "title": "Change of plans", "description": ""},
                    {"id": f"cancel_reason_{booking_id}_weather", "title": "Weather conditions", "description": ""},
                    {"id": f"cancel_reason_{booking_id}_injury", "title": "Injured player(s)", "description": ""},
                    {"id": f"cancel_reason_{booking_id}_wrong", "title": "Booked wrong slot/turf", "description": ""},
                    {"id": f"cancel_reason_{booking_id}_other", "title": "Other (Specify reason)", "description": "Type your custom reason"},
                ]
            }
        ]

        await whatsapp_service.send_list(
            phone,
            "❓ *Please select the reason for cancellation:*\n\nYour feedback helps us improve.",
            "Select Reason",
            sections
        )
        await update_session(phone, "AWAITING_CANCEL_REASON_SELECTION", {"cancel_booking_id": booking_id}, db)
        return

    if text.startswith("cancel_reason_"):
        parts = text.split("_")
        booking_id = int(parts[2])
        reason_id = parts[3]

        booking = await db.get(BotBooking, booking_id)
        if not booking:
            await whatsapp_service.send_text(phone, "❌ Booking not found.")
            return

        if reason_id == "other":
            await whatsapp_service.send_text(phone, "✍️ Please type the reason for cancelling your booking:")
            await update_session(phone, "AWAITING_CANCEL_REASON", {"cancel_booking_id": booking_id}, db)
            return

        reason_map = {
            "plans": "Change of plans",
            "weather": "Weather conditions",
            "injury": "Injured player(s)",
            "wrong": "Booked wrong slot/turf"
        }
        reason_text = reason_map.get(reason_id, "Unknown")
        await process_booking_cancellation(phone, booking, reason_text, db)
        return



    # Player menu / location query
    if not session or lower in ("hi", "hello", "book", "/book", "menu") or session.state == "PLAYER_START":
        await whatsapp_service.send_buttons(
            phone,
            "👋 *Welcome to STRIKIT!*\n\nTo help you find the best turfs nearby, please share your current location using the native WhatsApp Location sharing button (📎 -> Location):",
            [
                {"id": "player_join_game", "title": "🎮 Join a Game"},
                {"id": "player_my_bookings", "title": "📋 My Bookings"},
                {"id": "back_to_roles", "title": "🔙 Back to Menu"},
            ]
        )
        await update_session(phone, "AWAITING_LOCATION_OR_SEARCH", {}, db, role="CUSTOMER")
        return

    # Handle location receipt / turf list calculation
    if session and session.state == "AWAITING_LOCATION_OR_SEARCH":
        if text.startswith("location:"):
            try:
                parts = text.replace("location:", "").split(",")
                player_lat = float(parts[0])
                player_lng = float(parts[1])
            except Exception:
                await whatsapp_service.send_text(phone, "❌ Error parsing location. Please try sharing your location again:")
                return

            owners = (await db.execute(
                select(BotOwner).where(BotOwner.verified == True, BotOwner.subscriptionActive == True)
            )).scalars().all()

            nearby_turfs = []
            for o in owners:
                if o.latitude is not None and o.longitude is not None:
                    dist = calculate_distance(player_lat, player_lng, o.latitude, o.longitude)
                else:
                    dist = 999999.0
                nearby_turfs.append((o, dist))

            # Sort by distance
            nearby_turfs.sort(key=lambda item: item[1])

            # Filter within 10km
            within_10km = [item for item in nearby_turfs if item[1] <= 10.0]
            display_turfs = within_10km if within_10km else nearby_turfs[:10]

            if not display_turfs:
                await whatsapp_service.send_text(phone, "No active turfs available at the moment. Please check back later!")
                return

            sections = [
                {
                    "title": "Nearby Turfs" if within_10km else "Available Turfs",
                    "rows": [
                        {
                            "id": f"select_turf_{o.id}",
                            "title": o.turfName[:24],
                            "description": f"₹{amount_service.paise_to_rupees(o.pricePerHourPaise)}/hr | {dist:.1f} km away" if dist < 999999.0 else f"₹{amount_service.paise_to_rupees(o.pricePerHourPaise)}/hr",
                        }
                        for o, dist in display_turfs
                    ],
                },
                {
                    "title": "Go Back",
                    "rows": [
                        {
                            "id": "back_to_roles",
                            "title": "🔙 Back to Main Menu",
                            "description": "Switch between Player and Owner roles",
                        }
                    ],
                }
            ]

            msg = "🏟️ *Nearby Turfs Found (within 10km):*\n\nSelect a turf below to book:" if within_10km else "🏟️ *Available Turfs (sorted by distance):*\n\nSelect a turf below:"
            await whatsapp_service.send_list(
                phone,
                msg,
                "🏟️ View Turfs",
                sections,
            )

            await whatsapp_service.send_buttons(
                phone,
                "Or choose an option:",
                [
                    {"id": "player_join_game", "title": "🎮 Join a Game"},
                    {"id": "player_my_bookings", "title": "📋 My Bookings"},
                    {"id": "back_to_roles", "title": "🔙 Back to Roles"},
                ],
            )
            # Transition to AWAITING_TURF_SELECTION to handle select_turf_ clicks
            await update_session(phone, "AWAITING_TURF_SELECTION", {}, db, role="CUSTOMER")
            return
        else:
            search_query = text.strip()
            prefixes = [
                "book turf near", "show turf near", "turf near", "near",
                "book turf in", "show turf in", "turf in", "in",
                "book turf at", "show turf at", "turf at", "at",
                "book turf", "show turf", "book", "show", "search"
            ]
            lower_text = search_query.lower()
            for p in prefixes:
                if lower_text.startswith(p):
                    search_query = search_query[len(p):].strip()
                    break

            if search_query and lower_text not in ("done", "cancel", "menu", "hi", "hello"):
                words = [w.strip() for w in search_query.lower().split() if len(w.strip()) >= 2]
                if words:
                    owners = (await db.execute(
                        select(BotOwner).where(BotOwner.verified == True, BotOwner.subscriptionActive == True)
                    )).scalars().all()
                    
                    matched_owners = []
                    for o in owners:
                        name_lower = o.turfName.lower()
                        address_lower = (o.address or "").lower()
                        keywords_lower = (o.searchKeywords or "").lower()
                        
                        matches = True
                        for w in words:
                            if w not in name_lower and w not in address_lower and w not in keywords_lower:
                                matches = False
                                break
                        if matches:
                            matched_owners.append(o)
                            
                    if matched_owners:
                        rows = [
                            {
                                "id": f"select_turf_{o.id}",
                                "title": o.turfName[:24],
                                "description": f"₹{amount_service.paise_to_rupees(o.pricePerHourPaise)}/hr | {o.address[:24] if o.address else ''}",
                            }
                            for o in matched_owners
                        ]
                        
                        sections = [
                            {
                                "title": f"Matches for '{search_query}'",
                                "rows": rows,
                            },
                            {
                                "title": "Go Back",
                                "rows": [
                                    {
                                        "id": "back_to_roles",
                                        "title": "🔙 Back to Main Menu",
                                        "description": "Switch between Player and Owner roles",
                                    }
                                ],
                            }
                        ]
                        
                        await whatsapp_service.send_list(
                            phone,
                            f"🏟️ *Matching Turfs found near '{search_query}':*\n\nSelect a turf below to book:",
                            "🏟️ View Matches",
                            sections
                        )
                        
                        await whatsapp_service.send_buttons(
                            phone,
                            "Or search again / share location:",
                            [
                                {"id": "player_join_game", "title": "🎮 Join a Game"},
                                {"id": "player_my_bookings", "title": "📋 My Bookings"},
                                {"id": "back_to_roles", "title": "🔙 Back to Roles"},
                            ],
                        )
                        
                        await update_session(phone, "AWAITING_TURF_SELECTION", {}, db, role="CUSTOMER")
                        return

            owners = (await db.execute(
                select(BotOwner).where(BotOwner.verified == True, BotOwner.subscriptionActive == True)
            )).scalars().all()
            
            if owners:
                rows = [
                    {
                        "id": f"select_turf_{o.id}",
                        "title": o.turfName[:24],
                        "description": f"₹{amount_service.paise_to_rupees(o.pricePerHourPaise)}/hr",
                    }
                    for o in owners[:10]
                ]
                
                sections = [
                    {
                        "title": "All Available Turfs",
                        "rows": rows,
                    },
                    {
                        "title": "Go Back",
                        "rows": [
                            {
                                "id": "back_to_roles",
                                "title": "🔙 Back to Main Menu",
                                "description": "Switch between Player and Owner roles",
                            }
                        ],
                    }
                ]
                
                msg = f"Sorry, we couldn't find any turfs near '{search_query}'." if (text and lower_text not in ("done", "cancel", "menu", "hi", "hello")) else "⚠️ We couldn't detect your location."
                await whatsapp_service.send_list(
                    phone,
                    f"{msg}\n\nHere are the available turfs on our platform. Select one below to book:",
                    "🏟️ View Turfs",
                    sections,
                )
                
                await whatsapp_service.send_buttons(
                    phone,
                    "Or choose an option:",
                    [
                        {"id": "player_join_game", "title": "🎮 Join a Game"},
                        {"id": "player_my_bookings", "title": "📋 My Bookings"},
                        {"id": "back_to_roles", "title": "🔙 Back to Roles"},
                    ],
                )
                
                await update_session(phone, "AWAITING_TURF_SELECTION", {}, db, role="CUSTOMER")
            else:
                await whatsapp_service.send_text(
                    phone,
                    "No active turfs are currently registered. Please check back later!"
                )
            return

    # Context
    context = json.loads(session.context or "{}") if session else {}
    state = session.state if session else ""

    # ── Cancellation Custom Reason State ──
    if state == "AWAITING_CANCEL_REASON":
        booking_id = context.get("cancel_booking_id")
        booking = await db.get(BotBooking, booking_id)
        if not booking:
            await whatsapp_service.send_text(phone, "❌ Booking not found. Session expired.")
            await update_session(phone, "PLAYER_START", {}, db)
            return

        reason_text = text.strip()
        await process_booking_cancellation(phone, booking, reason_text, db)
        return

    # ── Join Game Flow States ──
    if state == "AWAITING_JOIN_DATE":
        try:
            datetime.strptime(text.strip(), "%Y-%m-%d")
            selected_date = text.strip()
        except ValueError:
            await whatsapp_service.send_text(phone, "⚠️ Invalid date format. Please enter date as YYYY-MM-DD (e.g. 2026-06-25):")
            return

        context["joinDate"] = selected_date

        # Find bookings on this date
        stmt = select(BotBooking).join(BotTurfSlot).where(
            BotTurfSlot.date == selected_date,
            BotBooking.paymentStatus == "VERIFIED"
        )
        bookings = (await db.execute(stmt)).scalars().all()

        if not bookings:
            await whatsapp_service.send_text(phone, f"😔 No active games found on {selected_date} to join. Try another date:")
            return

        rows = []
        for b in bookings:
            slot = await db.get(BotTurfSlot, b.slotId)
            owner = await db.get(BotOwner, slot.ownerId) if slot else None
            turf_name = owner.turfName if owner else "Unknown Turf"
            slot_time = slot.timeSlot if slot else "N/A"
            rows.append({
                "id": f"join_book_{b.id}",
                "title": f"{turf_name} | {slot_time}",
                "description": f"Team: {b.teamName} | Captain: {b.captainName}"
            })

        sections = [{
            "title": "Select Game",
            "rows": rows[:10]
        }]

        await whatsapp_service.send_list(
            phone,
            f"🎮 *Games on {selected_date}*:\n\nSelect a game below to send a join request:",
            "🎮 Select Game",
            sections
        )
        await update_session(phone, "AWAITING_JOIN_GAME_SELECTION", context, db)
        return

    if state == "AWAITING_JOIN_GAME_SELECTION":
        if not text.startswith("join_book_"):
            await whatsapp_service.send_text(phone, "⚠️ Please select a game from the menu list to join.")
            return

        booking_id = int(text.replace("join_book_", ""))
        booking = await db.get(BotBooking, booking_id)
        if not booking:
            await whatsapp_service.send_text(phone, "⚠️ Game not found. Please try again.")
            return

        context["joinBookingId"] = booking_id
        await whatsapp_service.send_text(phone, "Please enter your *name*:")
        await update_session(phone, "AWAITING_JOIN_PLAYER_NAME", context, db)
        return

    if state == "AWAITING_JOIN_PLAYER_NAME":
        player_name = sanitize_input(text, 100)
        booking = await db.get(BotBooking, context.get("joinBookingId"))
        if not booking:
            await whatsapp_service.send_text(phone, "⚠️ Booking not found. Session expired.")
            return

        join_req = BotJoinRequest(
            bookingId=booking.id,
            playerName=player_name,
            playerPhone=phone,
            status="AWAITING_PAYMENT",
            joiningAmount=settings.PLATFORM_JOIN_FEE_PAISE
        )
        db.add(join_req)
        await db.flush()

        pay_link = payment_service.create_join_request_link(
            request_id=join_req.id,
            phone=phone,
            amount_paise=settings.PLATFORM_JOIN_FEE_PAISE
        )

        await whatsapp_service.send_text(
            phone,
            f"💳 *Join Request Payment* 💳\n\n"
            f"Hello {player_name}, to send a request to join *{booking.teamName}*'s game, please pay the ₹9 platform fee:\n\n"
            f"🔗 *Payment Link:* {pay_link}\n\n"
            f"_Powered by STRIKIT_"
        )

        session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()
        if session:
            await db.delete(session)
        await db.commit()
        return

    # Turf selection
    if text.startswith("select_turf_"):
        owner_id = int(text.replace("select_turf_", ""))
        owner = await db.get(BotOwner, owner_id)
        if not owner:
            await whatsapp_service.send_text(phone, "Turf not found. Please try again.")
            return

        context["ownerId"] = owner_id
        context["turfName"] = owner.turfName

        # Show next 7 days
        dates = []
        for i in range(7):
            d = datetime.utcnow() + timedelta(days=i)
            dates.append(d.strftime("%Y-%m-%d"))

        sections = [{
            "title": "Available Dates",
            "rows": [{"id": f"date_{d}", "title": d, "description": ""} for d in dates],
        }]

        await whatsapp_service.send_list(
            phone,
            f"📅 *{owner.turfName}*\n\nSelect a date for your booking:",
            "📅 Select Date",
            sections,
        )
        await update_session(phone, "AWAITING_DATE_SELECTION", context, db)
        return

    # Date selection
    if state == "AWAITING_DATE_SELECTION" and text.startswith("date_"):
        date = text.replace("date_", "")
        context["selectedDate"] = date
        owner_id = context.get("ownerId")

        # Get available slots
        existing = (await db.execute(
            select(BotTurfSlot).where(
                BotTurfSlot.ownerId == owner_id,
                BotTurfSlot.date == date,
            )
        )).scalars().all()

        booked_or_blocked = {s.timeSlot for s in existing if s.status in ("BOOKED", "BLOCKED")}

        # Generate time slots from owner's opening to closing
        owner = await db.get(BotOwner, owner_id)
        all_slots = _generate_time_slots(owner.openingTime, owner.closingTime)
        available = [s for s in all_slots if s not in booked_or_blocked]

        if not available:
            await whatsapp_service.send_text(phone, f"Sorry, no available slots for {date}. Please try another date.")
            return

        morning_slots = []
        afternoon_slots = []
        evening_slots = []
        night_slots = []

        for s in available:
            try:
                dt_time = datetime.strptime(s.strip(), "%I:%M %p").time()
                hour = dt_time.hour
                if hour < 12:
                    morning_slots.append(s)
                elif hour < 16:
                    afternoon_slots.append(s)
                elif hour < 20:
                    evening_slots.append(s)
                else:
                    night_slots.append(s)
            except Exception:
                if "AM" in s:
                    morning_slots.append(s)
                else:
                    evening_slots.append(s)

        sections = []
        if morning_slots:
            sections.append({
                "title": "Morning Slots",
                "rows": [{"id": s, "title": s, "description": "Available"} for s in morning_slots[:10]]
            })
        if afternoon_slots:
            sections.append({
                "title": "Afternoon Slots",
                "rows": [{"id": s, "title": s, "description": "Available"} for s in afternoon_slots[:10]]
            })
        if evening_slots:
            sections.append({
                "title": "Evening Slots",
                "rows": [{"id": s, "title": s, "description": "Available"} for s in evening_slots[:10]]
            })
        if night_slots:
            sections.append({
                "title": "Night Slots",
                "rows": [{"id": s, "title": s, "description": "Available"} for s in night_slots[:10]]
            })

        await whatsapp_service.send_list(
            phone,
            f"⏰ Available slots for *{date}* at *{context.get('turfName', '')}*:",
            "⏰ Select Slot",
            sections,
        )
        await update_session(phone, "AWAITING_SLOT_SELECTION", context, db)
        return

    # Slot selection
    if state == "AWAITING_SLOT_SELECTION":
        time_slot = text.strip()
        owner_id = context.get("ownerId")

        slot = (await db.execute(
            select(BotTurfSlot).where(
                BotTurfSlot.ownerId == owner_id,
                BotTurfSlot.date == context["selectedDate"],
                BotTurfSlot.timeSlot == time_slot,
            )
        )).scalars().first()

        if slot:
            if slot.status != "AVAILABLE":
                await whatsapp_service.send_text(phone, f"Sorry, {time_slot} is already {slot.status.lower()}. Please select another:")
                return
            slot.status = "RESERVED"
        else:
            slot = BotTurfSlot(
                ownerId=owner_id,
                date=context["selectedDate"],
                timeSlot=time_slot,
                status="RESERVED"
            )
            db.add(slot)

        await db.commit()

        context["selectedSlot"] = time_slot
        await whatsapp_service.send_text(phone, "Please enter your *Name and Team Name*\n(Format: Name - TeamName, e.g. John - HawksFC):")
        await update_session(phone, "AWAITING_TEAM_DETAILS", context, db)
        return

    # Team details
    if state == "AWAITING_TEAM_DETAILS":
        parts = text.split("-")
        if len(parts) < 2:
            await whatsapp_service.send_text(phone, "Format incorrect. Please enter: Name - TeamName")
            return

        context["captainName"] = parts[0].strip()
        context["teamName"] = parts[1].strip()

        await whatsapp_service.send_text(phone, "Please enter the *Sport/Event* you are playing (e.g. Cricket, Football):")
        await update_session(phone, "AWAITING_SPORT_DETAILS", context, db)
        return

    # Sport details
    if state == "AWAITING_SPORT_DETAILS":
        context["sport"] = text.strip()

        owner = await db.get(BotOwner, context.get("ownerId"))
        if not owner:
            await whatsapp_service.send_text(phone, "Error: Turf owner not found.")
            return

        # ── Calculate split using amount_service (PAISE ONLY) ──
        split = amount_service.calculate_booking_split(owner.pricePerHourPaise)
        total_paise = split["total_paise"]
        rate_rupees = amount_service.paise_to_rupees(split["owner_share_paise"])
        fee_rupees = amount_service.paise_to_rupees(split["platform_fee_paise"])
        total_rupees = amount_service.paise_to_rupees(total_paise)

        pay_link = payment_service.create_booking_link(
            phone=phone,
            owner_id=owner.id,
            date=context["selectedDate"],
            slot_time=context["selectedSlot"],
            captain_name=context["captainName"],
            team_name=context["teamName"],
            total_amount_paise=total_paise,
            sport=context["sport"],
        )
        context["payLink"] = pay_link

        await whatsapp_service.send_text(
            phone,
            f"📋 *Booking Summary - {owner.turfName}* 📋\n\n"
            f"Hello {context['captainName']}, here is your booking summary:\n\n"
            f"• Turf: *{owner.turfName}*\n"
            f"• Date: {context['selectedDate']}\n"
            f"• Time Slot: {context['selectedSlot']}\n"
            f"• Sport/Event: {context['sport']}\n"
            f"• Captain Name: {context['captainName']}\n"
            f"• Team Name: {context['teamName']}\n\n"
            f"*Payment Breakdown:*\n"
            f"• Turf Rate: ₹{rate_rupees}\n"
            f"• STRIKIT Booking Fee: ₹{fee_rupees}\n"
            f"• *Total Amount:* *₹{total_rupees}*\n\n"
            f"🔗 *Payment Link:* {pay_link}\n\n"
            f"_Powered by STRIKIT_",
        )
        await update_session(phone, "AWAITING_PAYMENT_CONFIRMATION", context, db)
        return

    # Awaiting payment
    if state == "AWAITING_PAYMENT_CONFIRMATION":
        pay_link = context.get("payLink")
        if not pay_link:
            owner = await db.get(BotOwner, context.get("ownerId"))
            if owner:
                split = amount_service.calculate_booking_split(owner.pricePerHourPaise)
                pay_link = payment_service.create_booking_link(
                    phone=phone, owner_id=owner.id, date=context["selectedDate"],
                    slot_time=context["selectedSlot"], captain_name=context["captainName"],
                    team_name=context["teamName"], total_amount_paise=split["total_paise"],
                    sport=context.get("sport", ""),
                )
                context["payLink"] = pay_link
                await update_session(phone, "AWAITING_PAYMENT_CONFIRMATION", context, db)
        
        if pay_link:
            await whatsapp_service.send_text(
                phone,
                f"⏳ *Awaiting Payment*\n\nYour slot is temporarily held. Pay here:\n👉 {pay_link}\n\n_Powered by STRIKIT_",
            )
        return

    # My Bookings
    if lower in ("player_my_bookings", "/mybookings", "mybookings"):
        bookings = (await db.execute(
            select(BotBooking).where(
                BotBooking.captainPhone == phone,
                BotBooking.paymentStatus == "VERIFIED",
            ).order_by(desc(BotBooking.createdAt)).limit(10)
        )).scalars().all()

        if not bookings:
            await whatsapp_service.send_text(phone, "📋 No bookings found. Type *book* to make one!")
            return

        now = datetime.utcnow()
        cancellable_rows = []

        msg = "📋 *Your Recent Bookings*\n\n"
        for b in bookings:
            slot = await db.get(BotTurfSlot, b.slotId)
            owner = await db.get(BotOwner, slot.ownerId) if slot else None
            status_str = "Confirmed" if b.status != "CANCELLED" else "CANCELLED"
            msg += (
                f"• *{owner.turfName if owner else 'Unknown'}*\n"
                f"  Date: {slot.date if slot else 'N/A'} | {slot.timeSlot if slot else 'N/A'}\n"
                f"  Team: {b.teamName} | Paid: ₹{amount_service.paise_to_rupees(b.totalPaidPaise)}\n"
                f"  Status: {status_str}\n\n"
            )

            # Check if booking can be cancelled (verified, not cancelled, and in the future)
            if b.paymentStatus == "VERIFIED" and b.status == "CONFIRMED" and slot:
                try:
                    slot_date = datetime.strptime(slot.date, "%Y-%m-%d")
                    start_time_str = slot.timeSlot.split("-")[0].strip()
                    game_time = None
                    for fmt in ("%I:%M %p", "%H:%M"):
                        try:
                            parsed = datetime.strptime(start_time_str, fmt)
                            game_time = slot_date.replace(
                                hour=parsed.hour,
                                minute=parsed.minute,
                                second=0,
                                microsecond=0,
                            )
                            break
                        except ValueError:
                            continue

                    if game_time and game_time > now:
                        cancellable_rows.append({
                            "id": f"cancel_select_{b.id}",
                            "title": f"{owner.turfName if owner else 'Turf'} - {slot.date}"[:24],
                            "description": f"{slot.timeSlot} | ₹{amount_service.paise_to_rupees(b.totalPaidPaise)}",
                        })
                except Exception as e:
                    logger.error(f"[MyBookings] Parsing error for slot {slot.id}: {e}")

        await whatsapp_service.send_text(phone, msg + "_Powered by STRIKIT_")

        if cancellable_rows:
            sections = [
                {
                    "title": "Cancel a Booking",
                    "rows": cancellable_rows
                }
            ]
            await whatsapp_service.send_list(
                phone,
                "🏟️ *Booking Cancellation*\n\nIf you want to cancel one of your upcoming bookings, select it from the menu list below:",
                "❌ Cancel Booking",
                sections
            )
        return

    # Join game flow
    if lower in ("player_join_game", "/join", "join"):
        await whatsapp_service.send_text(phone, "Enter the *date* you'd like to join a game (YYYY-MM-DD):")
        await update_session(phone, "AWAITING_JOIN_DATE", {}, db)
        return

    # Default
    await whatsapp_service.send_text(
        phone,
        "👋 Welcome to *STRIKIT*!\n\nType *book* to book a turf, or *join* to join an existing game.\n\n_Powered by STRIKIT_",
    )


# ══════════════════════════════════════════════════════════════════
# CAPTAIN APPROVAL
# ══════════════════════════════════════════════════════════════════

async def handle_captain_approval(phone: str, text: str, owner, db: AsyncSession) -> bool:
    """Handle captain approving/rejecting a join request. Returns True if handled."""
    if not text.startswith(("approve_join_", "reject_join_")):
        return False

    action = "APPROVE" if text.startswith("approve_join_") else "REJECT"
    req_id = int(text.split("_")[-1])

    join_req = await db.get(BotJoinRequest, req_id)
    if not join_req:
        await whatsapp_service.send_text(phone, "Join request not found.")
        return True

    booking = await db.get(BotBooking, join_req.bookingId)
    if not booking or booking.captainPhone != phone:
        await whatsapp_service.send_text(phone, "You are not authorized to manage this request.")
        return True

    if action == "APPROVE":
        join_req.status = "ACCEPTED"
        await db.commit()
        await whatsapp_service.send_text(phone, f"✅ {join_req.playerName}'s join request APPROVED!")
        await whatsapp_service.send_text(
            join_req.playerPhone,
            f"✅ *Join Request Approved!*\n\nHello {join_req.playerName}, your request has been approved by the captain!",
        )
    else:
        join_req.status = "REJECTED"
        await db.commit()
        await whatsapp_service.send_text(phone, f"❌ {join_req.playerName}'s join request rejected.")
        await whatsapp_service.send_text(
            join_req.playerPhone,
            f"❌ Sorry {join_req.playerName}, your join request was rejected by the captain.",
        )

    return True


# ══════════════════════════════════════════════════════════════════
# DEVELOPER COMMANDS
# ══════════════════════════════════════════════════════════════════

async def handle_developer_command(phone: str, text: str, db: AsyncSession):
    """Handle /approve, /reject, /deactivate, /activate commands from developers."""
    parts = text.strip().split()
    command = parts[0].lower()
    owner_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

    if not owner_id:
        await whatsapp_service.send_text(phone, "Usage: /approve <ownerID> or /reject <ownerID>")
        return

    owner = await db.get(BotOwner, owner_id)
    if not owner:
        await whatsapp_service.send_text(phone, f"Owner ID {owner_id} not found.")
        return

    if command == "/approve":
        owner.verified = True
        sub_link = payment_service.create_subscription_link(owner_id, 69900, "TRIAL")

        session = (await db.execute(select(BotSession).where(BotSession.phone == owner.mobile))).scalars().first()
        ctx = json.loads(session.context) if session and session.context else {}
        ctx["ownerId"] = owner_id
        if session:
            session.role = "ONBOARDING"
            session.state = "AWAITING_SUBSCRIPTION"
            session.context = json.dumps(ctx)
        await db.commit()

        await whatsapp_service.send_text(
            owner.mobile,
            f"🎉 *Approved!* Your turf *{owner.turfName}* is verified.\n\n"
            f"Please complete your subscription payment to activate your bot:\n"
            f"🔗 *Subscription Link (₹699 for 3 Months):* {sub_link}\n\n"
            f"_Powered by STRIKIT_",
        )
        await whatsapp_service.send_text(phone, f"✅ Owner {owner.name} approved.")

    elif command == "/reject":
        owner.verified = False
        owner.subscriptionActive = False
        await db.commit()
        await whatsapp_service.send_text(owner.mobile, f"❌ Your registration for {owner.turfName} was rejected.")
        await whatsapp_service.send_text(phone, f"❌ Owner {owner.name} rejected.")

    elif command == "/deactivate":
        owner.subscriptionActive = False
        await db.commit()
        await whatsapp_service.send_text(phone, f"🔴 Owner {owner.name} deactivated.")

    elif command == "/activate":
        from datetime import timedelta
        plan = "TRIAL"
        days = 90
        if len(parts) > 2:
            p_arg = parts[2].upper()
            if p_arg in ("BASIC", "PREMIUM", "PREMIUM_3M", "TRIAL"):
                plan = p_arg
                if plan in ("TRIAL", "PREMIUM_3M"):
                    days = 90
                else:
                    days = 30
        owner.subscriptionActive = True
        owner.subscriptionStartedAt = datetime.utcnow()
        owner.subscriptionExpiry = datetime.utcnow() + timedelta(days=days)
        owner.subscriptionPlan = plan
        await db.commit()
        await whatsapp_service.send_text(phone, f"🟢 Owner {owner.name} activated for {days} days on {plan} plan.")


# ══════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════

def _generate_time_slots(opening: str, closing: str) -> list[str]:
    """Generate hourly time slots between opening and closing time."""
    slots = []
    try:
        from datetime import datetime as dt
        open_dt = dt.strptime(opening.strip(), "%I:%M %p")
        close_dt = dt.strptime(closing.strip(), "%I:%M %p")

        current = open_dt
        while current < close_dt:
            slots.append(current.strftime("%I:%M %p"))
            current += timedelta(hours=1)
    except Exception:
        # Fallback: default slots
        slots = [
            "06:00 AM", "07:00 AM", "08:00 AM", "09:00 AM", "10:00 AM",
            "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", "03:00 PM",
            "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM", "08:00 PM",
            "09:00 PM", "10:00 PM",
        ]
    return slots


async def process_booking_cancellation(phone: str, booking: BotBooking, reason_text: str, db: AsyncSession):
    """Process cancellation, calculate refund, issue Razorpay refund, release slot, notify player/admin."""
    try:
        slot = await db.get(BotTurfSlot, booking.slotId)
        if not slot:
            await whatsapp_service.send_text(phone, "❌ Slot details not found for this booking.")
            return

        owner = await db.get(BotOwner, slot.ownerId)
        if not owner:
            await whatsapp_service.send_text(phone, "❌ Turf owner details not found.")
            return

        # 1. Parse slot date and time
        slot_date = datetime.strptime(slot.date, "%Y-%m-%d")
        start_time_str = slot.timeSlot.split("-")[0].strip()
        game_time = None
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                parsed = datetime.strptime(start_time_str, fmt)
                game_time = slot_date.replace(
                    hour=parsed.hour,
                    minute=parsed.minute,
                    second=0,
                    microsecond=0,
                )
                break
            except ValueError:
                continue

        now = datetime.utcnow()
        if not game_time or game_time <= now:
            await whatsapp_service.send_text(phone, "❌ You cannot cancel a slot that has already started or completed.")
            await update_session(phone, "PLAYER_START", {}, db)
            return

        # 2. Calculate refund percentage and amount
        hours_until_game = (game_time - now).total_seconds() / 3600
        if hours_until_game > settings.CANCEL_FULL_REFUND_HOURS:
            refund_percentage = 80
        elif hours_until_game > settings.CANCEL_PARTIAL_REFUND_HOURS:
            refund_percentage = 50
        else:
            refund_percentage = 0

        refund_amount_paise = int(booking.totalPaidPaise * (refund_percentage / 100.0))

        # 3. Trigger Razorpay refund if amount > 0
        refund_success = False
        refund_id = None
        refund_error = None

        if refund_amount_paise > 0 and booking.razorpayPaymentId:
            try:
                refund_res = payment_service.refund_payment(booking.razorpayPaymentId, refund_amount_paise)
                refund_id = refund_res.get("id", f"rfnd_{booking.razorpayPaymentId}")
                refund_success = True
            except Exception as e:
                refund_error = str(e)
                logger.error(f"[Cancellation] Razorpay refund failed for booking {booking.id}: {e}")

        # 4. Cancel payout ledger if still pending/failed/manual review
        payout_ledger_cancelled = False
        stmt = select(BotPayoutLedger).where(BotPayoutLedger.bookingId == booking.id)
        ledger = (await db.execute(stmt)).scalars().first()
        if ledger:
            if ledger.status in ("PROCESSING", "FAILED", "MANUAL_REVIEW"):
                ledger.status = "CANCELLED"
                payout_ledger_cancelled = True

        # 5. Set slot status to AVAILABLE
        slot.status = "AVAILABLE"

        # 6. Update booking status and cancellationReason
        booking.status = "CANCELLED"
        booking.cancellationReason = reason_text

        # Only set paymentStatus to REFUNDED if non-zero refund was processed successfully
        if refund_success:
            booking.paymentStatus = "REFUNDED"
        elif refund_percentage > 0:
            # Refund was required but failed
            booking.payoutStatus = "MANUAL_REVIEW"

        # 7. Write audit log entries
        db.add(BotPaymentAuditLog(
            bookingId=booking.id,
            eventType="CANCEL_INITIATED",
            message=f"Cancelled by player. Reason: {reason_text}. Refund percentage: {refund_percentage}%. Amount: ₹{amount_service.paise_to_rupees(refund_amount_paise)}.",
        ))

        if refund_success:
            db.add(BotPaymentAuditLog(
                bookingId=booking.id,
                eventType="REFUND_COMPLETED",
                message=f"Refund processed successfully. Refund ID: {refund_id}",
            ))
        elif refund_error:
            db.add(BotPaymentAuditLog(
                bookingId=booking.id,
                eventType="REFUND_FAILED",
                message=f"Refund failed: {refund_error}",
            ))

        await db.commit()

        # 8. Send telegram alert to admins
        await telegram_service.send_cancellation_alert(
            booking_id=booking.id,
            owner_name=owner.name,
            turf_name=owner.turfName,
            refund_amount_paise=refund_amount_paise,
            refund_percentage=refund_percentage,
            reason=reason_text,
        )

        if refund_percentage > 0 and not refund_success:
            await telegram_service.send_manual_review_alert(
                booking_id=booking.id,
                reason=f"Refund failed: {refund_error}",
                owner_name=owner.name,
                turf_name=owner.turfName,
            )

        # 9. Send WhatsApp confirmation to user
        refund_msg = ""
        if refund_percentage > 0:
            if refund_success:
                refund_msg = f"• Refund Amount: *₹{amount_service.paise_to_rupees(refund_amount_paise)} ({refund_percentage}% refund)*\n" \
                             f"  (Refund has been initiated to your original payment method)\n"
            else:
                refund_msg = f"• Refund Amount: *₹{amount_service.paise_to_rupees(refund_amount_paise)} ({refund_percentage}% refund)*\n" \
                             f"  (⚠️ Refund initiation failed. Our admin will process this manually within 24 hours)\n"
        else:
            refund_msg = f"• Refund: *No refund (cancelled less than 2 hours before game time)*\n"

        await whatsapp_service.send_text(
            phone,
            f"✅ *Booking Cancelled Successfully*\n\n"
            f"Your booking has been cancelled.\n\n"
            f"• Turf: *{owner.turfName}*\n"
            f"• Date: {slot.date} | {slot.timeSlot}\n"
            f"• Reason: {reason_text}\n"
            f"{refund_msg}\n"
            f"_Powered by STRIKIT_"
        )

        # Notify Owner about the cancellation via WhatsApp
        try:
            await whatsapp_service.send_text(
                owner.mobile,
                f"❌ *Booking Cancelled Alert for {owner.turfName}* ❌\n\n"
                f"Hello {owner.name}, a booking at your turf has been cancelled:\n\n"
                f"• Date: {slot.date}\n"
                f"• Time Slot: {slot.timeSlot}\n"
                f"• Sport/Event: {booking.sport or 'N/A'}\n"
                f"• Booking ID: #{booking.id}\n"
                f"• Refund to Player: {refund_percentage}% (₹{amount_service.paise_to_rupees(refund_amount_paise)})\n\n"
                f"ℹ️ The slot has been set back to *AVAILABLE* for bookings.\n\n"
                f"_Powered by STRIKIT_"
            )
        except Exception as wa_owner_err:
            logger.error(f"[Cancellation] Failed to notify owner via WhatsApp: {wa_owner_err}")

        # 10. Reset player session context
        await update_session(phone, "PLAYER_START", {}, db)

    except Exception as e:
        logger.error(f"[Cancellation] Error during process_booking_cancellation: {e}")
        await whatsapp_service.send_text(phone, "❌ Something went wrong while cancelling your booking. Please try again.")

