"""English message templates for STRIKIT bot."""

MESSAGES = {
    # ── Onboarding ──
    "onboarding_welcome": "Welcome to STRIKIT Onboarding! Let's get your turf set up. Please enter the Owner Name:",
    "onboarding_ask_turf": "Thank you, {name}. Now, please enter your Turf Name:",
    "onboarding_ask_location": 'Got it: "{turf}". Please enter the Location of your turf as a Google Maps link:',
    "onboarding_ask_photos": "Please upload your turf photos (send as images):",
    "onboarding_ask_gst": "Enter your GST Number (or type SKIP):",
    "onboarding_ask_msme": "Enter your MSME Udyam Number (or type SKIP):",
    "onboarding_ask_upi": "Enter your UPI ID for receiving payouts (e.g., name@upi):",
    "onboarding_pending": "⏳ Your turf verification is pending developer approval. We will notify you once approved!",
    "onboarding_subscription_prompt": (
        "🎉 *Congratulations {name}! Your STRIKIT Registration has been APPROVED!* 🎉\n\n"
        "Your turf *{turf}* has been verified.\n\n"
        "💳 *Subscription Link:* Please pay ₹699.00 to activate:\n{link}\n\n"
        "_Powered by STRIKIT_"
    ),

    # ── Booking Flow ──
    "booking_select_date": "📅 Please select a date for your booking:",
    "booking_select_slot": "⏰ Available slots for {date}. Please select a time slot:",
    "booking_ask_details": "Please enter your Name and Team Name (Format: Name - TeamName, e.g. John - HawksFC):",
    "booking_format_error": "Format incorrect. Please enter in this format: Name - TeamName",
    "booking_summary": (
        "📋 *Booking Summary - {turf}* 📋\n\n"
        "Hello {captain}, here is your booking summary:\n\n"
        "• Turf: *{turf}*\n"
        "• Date: {date}\n"
        "• Time Slot: {slot}\n"
        "• Captain Name: {captain}\n"
        "• Team Name: {team}\n\n"
        "*Payment Breakdown:*\n"
        "• Turf Rate: ₹{rate}\n"
        "• STRIKIT Booking Fee: ₹{fee}\n"
        "• *Total Amount:* *₹{total}*\n\n"
        "🔗 *Payment Link:* {link}\n\n"
        "_Powered by STRIKIT_"
    ),
    "booking_confirmed": (
        "✅ *Booking Confirmed!* ✅\n\n"
        "Hello {captain}, your turf booking is confirmed!\n\n"
        "• Turf: *{turf}*\n"
        "• Date: {date}\n"
        "• Time Slot: {slot}\n"
        "• Team Name: {team}\n"
        "• Amount Paid: ₹{total}\n\n"
        "_Powered by STRIKIT_"
    ),
    "booking_awaiting_payment": (
        "⏳ *Awaiting Payment Confirmation* ⏳\n\n"
        "Your slot is temporarily held. Please click here to complete your payment:\n"
        "👉 {link}\n\n"
        "_Powered by STRIKIT_"
    ),

    # ── Subscription ──
    "subscription_expired": (
        "⚠️ *STRIKIT Subscription Expired* ⚠️\n\n"
        "Dear {name}, your subscription for *{turf}* has expired.\n\n"
        "To restore access, please renew: ₹699.00\n"
        "🔗 *Payment Link:* {link}\n\n"
        "_Powered by STRIKIT_"
    ),
    "subscription_reminder": (
        "⏰ *STRIKIT Subscription Renewal Reminder* ⏰\n\n"
        "Dear {name}, your subscription for *{turf}* will expire in 3 days.\n\n"
        "🔗 *Payment Link:* {link}\n\n"
        "_Powered by STRIKIT_"
    ),

    # ── Player ──
    "player_welcome": (
        "👋 *Welcome to {turf}!* 👋\n\n"
        "What would you like to do?"
    ),
    "player_no_slots": "Sorry, no available slots for {date}. Please try another date.",
    "slot_already_taken": "Sorry, {slot} is already booked. Please select another slot:",

    # ── Join Request ──
    "join_fee_prompt": (
        "💳 *STRIKIT Platform Fee Payment* 💳\n\n"
        "Hello {name}, to submit your join request, please pay ₹9.00:\n{link}\n\n"
        "_Powered by STRIKIT_"
    ),
    "join_request_sent": "Your join request has been sent to the captain for approval.",
    "join_approved": "✅ Your join request has been APPROVED by the captain!",
    "join_rejected": "❌ Your join request has been rejected by the captain.",

    # ── Booking Reminder ──
    "booking_reminder": (
        "🏃 *Game Reminder!* 🏃\n\n"
        "Hello {captain}, your game at *{turf}* starts in 2 hours!\n\n"
        "• Date: {date}\n"
        "• Time: {slot}\n\n"
        "Have a great game! ⚽\n\n"
        "_Powered by STRIKIT_"
    ),
    "booking_feedback": (
        "⭐ *Rate Your Experience* ⭐\n\n"
        "Hello {captain}, how was your game at *{turf}* yesterday?\n\n"
        "Reply with a rating (1-5 stars).\n\n"
        "_Powered by STRIKIT_"
    ),
}
