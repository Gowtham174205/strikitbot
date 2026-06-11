"""Tamil message templates for STRIKIT bot."""

MESSAGES = {
    # ── Onboarding ──
    "onboarding_welcome": "STRIKIT-க்கு வரவேற்கிறோம்! உங்கள் மைதானத்தை அமைப்போம். உரிமையாளர் பெயரை உள்ளிடவும்:",
    "onboarding_ask_turf": "நன்றி, {name}. இப்போது உங்கள் மைதான பெயரை உள்ளிடவும்:",
    "onboarding_ask_location": '"{turf}" பதிவாகிவிட்டது. Google Maps இணைப்பை அனுப்புங்கள்:',
    "onboarding_ask_photos": "உங்கள் மைதான புகைப்படங்களை அனுப்புங்கள்:",
    "onboarding_ask_gst": "GST எண் உள்ளிடவும் (அல்லது SKIP):",
    "onboarding_ask_msme": "MSME Udyam எண் உள்ளிடவும் (அல்லது SKIP):",
    "onboarding_ask_upi": "பணம் பெற UPI ID உள்ளிடவும் (எ.கா. name@upi):",
    "onboarding_pending": "⏳ உங்கள் மைதான சரிபார்ப்பு நிலுவையில் உள்ளது. அங்கீகரிக்கப்பட்டதும் தெரிவிப்போம்!",

    # ── Booking Flow ──
    "booking_select_date": "📅 புக்கிங்கிற்கு தேதியை தேர்ந்தெடுக்கவும்:",
    "booking_select_slot": "⏰ {date} அன்று கிடைக்கும் நேரங்கள்:",
    "booking_ask_details": "உங்கள் பெயர் மற்றும் டீம் பெயர் உள்ளிடவும் (Format: பெயர் - டீம், எ.கா. ராஜா - HawksFC):",
    "booking_format_error": "தவறான வடிவம். இந்த வடிவத்தில் உள்ளிடவும்: பெயர் - டீம் பெயர்",
    "booking_summary": (
        "📋 *புக்கிங் சுருக்கம் - {turf}* 📋\n\n"
        "வணக்கம் {captain}, உங்கள் புக்கிங் விவரம்:\n\n"
        "• மைதானம்: *{turf}*\n"
        "• தேதி: {date}\n"
        "• நேரம்: {slot}\n"
        "• கேப்டன்: {captain}\n"
        "• டீம்: {team}\n\n"
        "*கட்டண விவரம்:*\n"
        "• மைதான கட்டணம்: ₹{rate}\n"
        "• STRIKIT கட்டணம்: ₹{fee}\n"
        "• *மொத்தம்:* *₹{total}*\n\n"
        "🔗 *கட்டண இணைப்பு:* {link}\n\n"
        "_Powered by STRIKIT_"
    ),
    "booking_confirmed": (
        "✅ *புக்கிங் உறுதிசெய்யப்பட்டது!* ✅\n\n"
        "வணக்கம் {captain}, உங்கள் மைதான புக்கிங் உறுதி!\n\n"
        "• மைதானம்: *{turf}*\n"
        "• தேதி: {date}\n"
        "• நேரம்: {slot}\n"
        "• டீம்: {team}\n"
        "• செலுத்திய தொகை: ₹{total}\n\n"
        "_Powered by STRIKIT_"
    ),

    # ── Subscription ──
    "subscription_expired": (
        "⚠️ *STRIKIT சந்தா காலாவதி* ⚠️\n\n"
        "அன்புள்ள {name}, *{turf}* சந்தா காலாவதியாகிவிட்டது.\n\n"
        "புதுப்பிக்க: ₹699.00\n"
        "🔗 *கட்டண இணைப்பு:* {link}\n\n"
        "_Powered by STRIKIT_"
    ),

    # ── Player ──
    "player_welcome": "👋 *{turf}* க்கு வரவேற்கிறோம்! என்ன செய்ய விரும்புகிறீர்கள்?",
    "player_no_slots": "மன்னிக்கவும், {date} அன்று நேரம் இல்லை. வேறு தேதி முயற்சிக்கவும்.",

    # ── Join Request ──
    "join_fee_prompt": (
        "💳 *STRIKIT கட்டணம்* 💳\n\n"
        "வணக்கம் {name}, சேர கோரிக்கை அனுப்ப ₹9.00 செலுத்துங்கள்:\n{link}\n\n"
        "_Powered by STRIKIT_"
    ),
    "join_approved": "✅ உங்கள் சேர கோரிக்கை கேப்டனால் அங்கீகரிக்கப்பட்டது!",
    "join_rejected": "❌ உங்கள் சேர கோரிக்கை நிராகரிக்கப்பட்டது.",

    # ── Reminder ──
    "booking_reminder": (
        "🏃 *விளையாட்டு நினைவூட்டல்!* 🏃\n\n"
        "வணக்கம் {captain}, *{turf}* இல் 2 மணி நேரத்தில் ஆட்டம் தொடங்கும்!\n\n"
        "நல்ல ஆட்டம் ஆடுங்கள்! ⚽\n\n"
        "_Powered by STRIKIT_"
    ),
}
