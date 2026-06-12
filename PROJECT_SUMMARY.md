# STRIKIT - Centralized WhatsApp Booking Bot & Admin System

This document provides a comprehensive overview of the **STRIKIT** WhatsApp Booking Bot system, designed to be shared with ChatGPT or other LLMs for code review, modifications, or feature development.

---

## 🚀 Project Overview

**STRIKIT** is an automated turf booking platform. It functions as a **centralized WhatsApp Bot** operating on a single number. 

### Core Workflows:
1. **Turf Owner Onboarding:** Owners message the bot `register` or `onboard` to set up their profile (Name, Turf Name, Google Maps Location, Photos, GSTIN, Timings, Hourly Price, and UPI ID).
2. **Developer Review & Approval:** Developers receive WhatsApp and Telegram notifications containing details and command buttons to `/approve` or `/reject` registrations.
3. **Owner Subscription & Auto-Pay:** Approved owners receive a ₹699 monthly subscription link. Once paid, the system configures monthly recurring auto-pay via Razorpay, sets the owner to active, and generates a permanent **Booking QR Code** (`Book [TurfName]`).
4. **Player Booking (Centralized):** 
   - **Smart Re-engagement:** If a returning player texts "hi", they are prompted to book their last visited turf.
   - **Location-Based Search:** Players can share their native WhatsApp location. The bot calculates nearby verified turfs within a **10km radius** using the **Haversine formula** and lists them.
   - **Slot Booking:** Players select a date, time slot (Morning/Evening), input team details, and receive a Razorpay link (Turf Rate + ₹50 platform fee).
5. **Split Payouts:** On successful payment, the booking is confirmed, and the turf owner receives their share automatically via **RazorpayX Payouts** based on their registered UPI ID.
6. **Single Player Match Joining:** Individual players can join booked slots by paying a ₹9 platform fee, notifying the team captain who can accept them and input a joining fee.
7. **Owner Management Dashboard:** Active owners can message the main bot to view active bookings, earnings stats, block/unblock slots interactively, edit settings, or download PDF transaction reports (**Current Month, Previous Month, All-Time**).
8. **Expired Subscriptions:** If an owner's subscription expires, player bookings remain active (platform still collects ₹50 booking fee), but the owner is blocked from dashboard/reports and gets a benefits checklist with a renewal link.
9. **Schedulers:** 
   - Monthly PDF earnings reports are auto-generated and sent to active owners' WhatsApp.
   - Renewal alerts are sent to owners 3 days prior to expiration.

---

## 📂 File Architecture Map

```text
strikitbot/
├── prisma/
│   └── schema.prisma         # Database models (Prisma/PostgreSQL)
├── src/
│   ├── routes/
│   │   ├── admin.js          # REST endpoints for Android Admin app
│   │   ├── telegramBot.js    # Telegram webhook handler for dev approvals & reports
│   │   ├── whatsappBot.js    # WhatsApp webhook router & conversational state machine
│   │   └── razorpay.js       # Webhook callback endpoints for Razorpay & RazorpayX
│   ├── services/
│   │   ├── pdfGenerator.js   # PDF generation service for owner & platform reports
│   │   ├── paymentService.js # Razorpay link generator (subscriptions, bookings, join fees)
│   │   ├── payoutService.js  # RazorpayX automated split payout executor
│   │   ├── telegramService.js# Telegram alert sender (HTML format parsing)
│   │   └── whatsappService.js# Meta Cloud API wrapper (text, buttons, lists, images, files)
│   ├── middleware/
│   │   └── security.js       # Input sanitization and API key checks
│   ├── server.js             # Express app entry, location parser, schedulers
│   └── verifyFlow.js         # End-to-End integration test suite (offline mock mode)
├── strikit-admin-app/        # Android Gradle project for Owner/Turf Admin App
└── app-debug.apk             # Compiled Android admin APK with updated app icon
```

---

## 💾 Database Schema (`prisma/schema.prisma`)

The system uses PostgreSQL. The WhatsApp bot models are prefixed with `Bot` to distinguish from web database tables:

```prisma
model BotOwner {
  id                    Int           @id @default(autoincrement())
  name                  String
  mobile                String        @unique
  turfName              String
  location              String
  photoUrls             String
  gst                   String?
  msme                  String?
  upiId                 String?
  razorpayContactId     String?       // Cache for split payouts
  razorpayFundAccountId String?       // Cache for split payouts
  verified              Boolean       @default(false)
  businessPhone         String?       @unique
  subscriptionActive    Boolean       @default(false)
  subscriptionExpiry    DateTime?
  createdAt             DateTime      @default(now())
  openingTime           String        @default("06:00 AM")
  closingTime           String        @default("10:00 PM")
  pricePerHour          Float         @default(1000.0)
  latitude              Float?        // Geocoding coordinates
  longitude             Float?        // Geocoding coordinates
  slots                 BotTurfSlot[]
}

model BotTurfSlot {
  id             Int          @id @default(autoincrement())
  ownerId        Int
  owner          BotOwner     @relation(fields: [ownerId], references: [id])
  date           String       // YYYY-MM-DD
  timeSlot       String       // e.g. "06:00 PM"
  status         String       // "AVAILABLE", "BOOKED", "BLOCKED"
  blockedByOwner Boolean      @default(false)
  createdAt      DateTime     @default(now())
  bookings       BotBooking[]

  @@unique([ownerId, date, timeSlot])
}

model BotBooking {
  id           Int              @id @default(autoincrement())
  slotId       Int
  slot         BotTurfSlot      @relation(fields: [slotId], references: [id])
  teamName     String
  captainName  String
  captainPhone String
  paymentId    String?          // Razorpay payment ID
  amountPaid   Float            // Gross minus ₹50 fee
  createdAt    DateTime         @default(now())
  joinRequests BotJoinRequest[]
}

model BotJoinRequest {
  id            Int        @id @default(autoincrement())
  bookingId     Int
  booking       BotBooking @relation(fields: [bookingId], references: [id])
  playerName    String
  playerPhone   String
  status        String     // "PENDING", "ACCEPTED", "REJECTED"
  joiningAmount Float?     // Direct payment to Captain
  createdAt     DateTime   @default(now())
}

model BotSession {
  id        Int      @id @default(autoincrement())
  phone     String   @unique
  role      String   // "CUSTOMER", "OWNER", "ONBOARDING"
  state     String   // Chat state tag (State Machine)
  context   String?  // JSON context payload
  updatedAt DateTime @updatedAt
}
```

---

## 🔄 Core Webhook & Message Routing Flows

### 1. Centralized Routing (`whatsappBot.js` -> `handleWhatsAppWebhook`)
When a message is received at the centralized WhatsApp number:
- Check if sender phone matches a registered `BotOwner`.
  - If **Yes**:
    - If session is in `ONBOARDING` role, continue registration state machine.
    - Check if subscription is expired. If so, intercept, block owner dashboard commands, and send renewal details.
    - If subscription is active, route to `handleOwnerCommands` (manual commands and interactive menus).
  - If **No**:
    - Check if sender has an active onboarding session (`role === 'ONBOARDING'`). If so, continue onboarding flow.
    - If sender texts `register` or `onboard`, wipe previous sessions and start registration onboarding flow.
    - If not onboarding, check if sender is a team captain responding to a join request (`handleCaptainApproval`).
    - Otherwise, treat sender as a player/customer and route to `handleCentralizedPlayerFlow`.

### 2. Player Booking Geolocation & Search
- If a player messages "hi" or "hello":
  - Query their last booking. If found, ask: *"Would you like to book a slot at [LastTurf] again?"* using WhatsApp interactive buttons.
  - If "No" or no history, prompt: *"Please share your current location using the WhatsApp Location button (📎 -> Location)"*.
  - Text search is blocked in this state to guarantee precise coordinates.
  - Upon receiving location data (formatted as `location:lat,lng` by `server.js` parser), extract latitude/longitude.
  - Fetch all verified, active owners. Use the Haversine formula to filter turfs within **10km** and present them sorted by distance.
  - Once chosen, start the standard booking slot selection.

### 3. Razorpay Subscription & Payout Webhooks (`razorpay.js`)
Handles webhook events from Razorpay:
- **`payment_link.paid` with `notes.type === 'subscription'`**:
  - Extend subscription by 30 days.
  - Set owner session directly to `OWNER_DASHBOARD` and role to `OWNER`.
  - Generate a permanent booking QR code (`Book [TurfName]`) via qrserver API and send it to the owner.
- **`payment_link.paid` with `notes.type === 'booking'`**:
  - Update `BotTurfSlot` status to `BOOKED` and create `BotBooking`.
  - Execute split payout: Send turf owner's rate directly to their registered UPI ID via RazorpayX.
  - Send booking confirmation WhatsApp to the captain (including coordinates/Google Maps directions link) and booking alert to the owner.
- **`payment_link.paid` with `notes.type === 'join_request'`**:
  - Update `BotJoinRequest` status to `PENDING` and notify the captain with buttons to accept or reject.

---

## 🛠️ How to Run and Test the Project

### Prerequisites
- Node.js v20.x installed.
- PostgreSQL database URL configured in `.env`.

### 1. Database Setup
Ensure schema is applied to the PostgreSQL database and the client is generated:
```bash
# Push schema updates directly to the database
npx prisma db push --accept-data-loss

# Generate Prisma Client types
npx prisma generate
```

### 2. Run Integration Tests
The project includes a robust integration test suite (`verifyFlow.js`) which runs in a completely offline mock mode (no real WhatsApp or Razorpay API calls are made):
```bash
# Run integration tests
node src/verifyFlow.js
```
*Expected Output:* `🎉 SUCCESS! ALL STRIKIT WORKFLOW CONVERSIONS VERIFIED! 🎉`

### 3. Start the Web Server Locally
```bash
# Start development server
npm run dev
```

### 4. Build the Android Admin App APK
```powershell
# In Windows PowerShell, build debug APK using Android Studio JBR
$env:JAVA_HOME="C:\Program Files\Android\Android Studio1\jbr"
$env:Path="C:\Program Files\Android\Android Studio1\jbr\bin;" + $env:Path
cd strikit-admin-app
.\gradlew.bat assembleDebug
```
The compiled APK will be output to `strikit-admin-app/app/build/outputs/apk/debug/app-debug.apk` and can be copied to the root folder.
