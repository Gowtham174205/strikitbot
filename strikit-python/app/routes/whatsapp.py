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
from app.models import BotOwner, BotTurfSlot, BotBooking, BotJoinRequest, BotSession
from app.services import whatsapp_service, telegram_service, payment_service, amount_service
from app.services.pdf_generator import generate_revenue_report
from app.middleware.security import verify_whatsapp_signature, sanitize_input
from app.middleware.rate_limiter import limiter
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WhatsApp"])


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


async def handle_whatsapp_message(
    phone: str, to: str, text: str, db: AsyncSession,
    media_id: str = "", media_type: str = "",
):
    """Central routing for all WhatsApp messages."""
    text = (text or "").strip()
    lower = text.lower().strip()

    # Developer commands
    dev_numbers = settings.developer_numbers_list
    if phone in dev_numbers and lower.startswith(("/approve", "/reject", "/deactivate", "/activate")):
        await handle_developer_command(phone, text, db)
        return

    # Centralized routing (single bot number)
    if to == settings.ONBOARDING_NUMBER or to == settings.WHATSAPP_PHONE_NUMBER_ID:
        # If they send 'hi' / 'hello' / 'menu' / '/menu', show role selection
        if lower in ("hi", "hello", "menu", "/menu"):
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
                    sub_link = payment_service.create_subscription_link(owner.id)
                    return await whatsapp_service.send_text(
                        phone,
                        f"⚠️ *STRIKIT Subscription Expired* ⚠️\n\n"
                        f"Dear {owner.name}, your subscription for *{owner.turfName}* has expired.\n\n"
                        f"🔗 *Renew:* {sub_link}\n\n_Powered by STRIKIT_",
                    )

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

        # Handle back/cancel command inside onboarding flow
        if session and session.role == "ONBOARDING" and lower in ("cancel", "/cancel", "back"):
            await update_session(phone, "ROLE_SELECTION", {}, db, role="CUSTOMER")
            await show_role_selection(phone)
            return

        if session:
            if session.role == "ONBOARDING":
                return await handle_onboarding_flow(phone, text, db, media_id, media_type)

            if session.role == "OWNER":
                owner = (await db.execute(select(BotOwner).where(BotOwner.mobile == phone))).scalars().first()
                if owner:
                    return await handle_owner_commands(phone, text, owner, db, media_id, media_type)

            # Player flow handles customer sessions
            return await handle_player_flow(phone, text, db)

        # Captain approval check
        if await handle_captain_approval(phone, text, None, db):
            return

        # Fallback: show role selection
        await update_session(phone, "ROLE_SELECTION", {}, db, role="CUSTOMER")
        await show_role_selection(phone)



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
            f'Got it: "{text}". Please enter the *Location* as a Google Maps link:',
            [{"id": "cancel_onboarding", "title": "🔙 Back to Menu"}]
        )
        await update_session(phone, "AWAITING_LOCATION", context, db)

    elif state == "AWAITING_LOCATION":
        context["location"] = sanitize_input(text, 500)
        # Try to extract lat/lng from Google Maps URL
        if "maps" in text.lower() or text.startswith("location:"):
            pass  # Valid location format
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
            media_url = await whatsapp_service.get_media_url(media_id)
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
            "Enter your *MSME Udyam Number*:",
            [
                {"id": "onboarding_msme_skip", "title": "⏭️ Skip MSME"},
                {"id": "cancel_onboarding", "title": "🔙 Back to Menu"}
            ]
        )
        await update_session(phone, "AWAITING_MSME", context, db)

    elif state == "AWAITING_MSME":
        context["msme"] = None if text.upper() == "SKIP" or lower == "onboarding_msme_skip" else sanitize_input(text, 50)
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
            upiId=context["upiId"],
            pricePerHourPaise=100000,  # Default ₹1000
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

    # Menu
    if lower in ("hi", "hello", "menu", "/menu", "help"):
        await whatsapp_service.send_buttons(
            phone,
            f"👋 Welcome, {owner.name}!\n\n*{owner.turfName}* Owner Dashboard\n\nSelect an option:",
            [
                {"id": "owner_bookings", "title": "📋 Today's Bookings"},
                {"id": "owner_revenue", "title": "📊 Revenue Report"},
                {"id": "owner_settings", "title": "⚙️ Settings"},
            ],
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
            await whatsapp_service.send_document(
                phone,
                f"https://bot.strikit.in/reports/{os.path.basename(pdf_path)}",
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
                ],
            }],
        )
        return

    # Settings actions
    session = (await db.execute(select(BotSession).where(BotSession.phone == phone))).scalars().first()

    if lower == "set_price":
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
            await db.commit()
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
        await db.commit()
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
            await db.commit()
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

            await db.commit()
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

    # Player menu / turf selection
    if not session or lower in ("hi", "hello", "book", "/book", "menu"):
        owners = (await db.execute(
            select(BotOwner).where(BotOwner.verified == True, BotOwner.subscriptionActive == True)
        )).scalars().all()

        if not owners:
            await whatsapp_service.send_text(phone, "No active turfs available at the moment. Please check back later!")
            return

        sections = [
            {
                "title": "Available Turfs",
                "rows": [
                    {
                        "id": f"select_turf_{o.id}",
                        "title": o.turfName[:24],
                        "description": f"₹{amount_service.paise_to_rupees(o.pricePerHourPaise)}/hr | {o.location[:30]}",
                    }
                    for o in owners[:10]
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

        await whatsapp_service.send_list(
            phone,
            "👋 *Welcome to STRIKIT!*\n\nBook a turf or join a game.\n\nSelect a turf below:",
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
        await update_session(phone, "PLAYER_START", {}, db, role="CUSTOMER")
        return

    # Context
    context = json.loads(session.context or "{}") if session else {}
    state = session.state if session else ""

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

        sections = [{
            "title": "Available Slots",
            "rows": [{"id": s, "title": s, "description": "Available"} for s in available[:10]],
        }]

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

        if slot and slot.status != "AVAILABLE":
            await whatsapp_service.send_text(phone, f"Sorry, {time_slot} is already {slot.status.lower()}. Please select another:")
            return

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
        )

        await whatsapp_service.send_text(
            phone,
            f"📋 *Booking Summary - {owner.turfName}* 📋\n\n"
            f"Hello {context['captainName']}, here is your booking summary:\n\n"
            f"• Turf: *{owner.turfName}*\n"
            f"• Date: {context['selectedDate']}\n"
            f"• Time Slot: {context['selectedSlot']}\n"
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
        owner = await db.get(BotOwner, context.get("ownerId"))
        if owner:
            split = amount_service.calculate_booking_split(owner.pricePerHourPaise)
            pay_link = payment_service.create_booking_link(
                phone=phone, owner_id=owner.id, date=context["selectedDate"],
                slot_time=context["selectedSlot"], captain_name=context["captainName"],
                team_name=context["teamName"], total_amount_paise=split["total_paise"],
            )
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

        msg = "📋 *Your Recent Bookings*\n\n"
        for b in bookings:
            slot = await db.get(BotTurfSlot, b.slotId)
            owner = await db.get(BotOwner, slot.ownerId) if slot else None
            msg += (
                f"• *{owner.turfName if owner else 'Unknown'}*\n"
                f"  Date: {slot.date if slot else 'N/A'} | {slot.timeSlot if slot else 'N/A'}\n"
                f"  Team: {b.teamName} | Paid: ₹{amount_service.paise_to_rupees(b.totalPaidPaise)}\n\n"
            )
        await whatsapp_service.send_text(phone, msg + "_Powered by STRIKIT_")
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
        sub_link = payment_service.create_subscription_link(owner_id)

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
            f"🎉 *Approved!* Your turf *{owner.turfName}* is verified.\nSubscription link: {sub_link}\n\n_Powered by STRIKIT_",
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
        owner.subscriptionActive = True
        owner.subscriptionExpiry = datetime.utcnow() + timedelta(days=30)
        await db.commit()
        await whatsapp_service.send_text(phone, f"🟢 Owner {owner.name} activated for 30 days.")


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
