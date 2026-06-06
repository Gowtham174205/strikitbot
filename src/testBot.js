import { PrismaClient } from '@prisma/client';
import { handleWhatsAppWebhook } from './routes/whatsappBot.js';
import { mockSentMessages, clearMockMessages } from './services/whatsappService.js';
import { mockTelegramMessages, clearMockTelegramMessages } from './services/telegramService.js';
import { handleTelegramWebhook } from './routes/telegramBot.js';
import readline from 'readline';

const prisma = new PrismaClient();
const ONBOARDING_NUMBER = '919000000000';

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function ask(query) {
  return new Promise((resolve) => rl.question(query, resolve));
}

// Global configurations for simulation
let currentOwnerMobile = '919876543210';
let currentBusinessNumber = '918888888888';
let currentPlayerMobile = '919999999999';
let currentSinglePlayerMobile = '917777777777';

async function main() {
  console.log('\n==================================================');
  console.log('       STRIKIT BOT WORKFLOW CLI SIMULATOR         ');
  console.log('==================================================');
  console.log('This utility simulates the full WhatsApp/Telegram bot');
  console.log('database states, payments, and notifications.');

  let exit = false;
  while (!exit) {
    console.log('\n--- SIMULATOR MENU ---');
    console.log('1. Onboard Owner (Register via STRIKIT Onboarding Number)');
    console.log('2. Mock Owner Subscription Payment (Razorpay ₹699)');
    console.log('3. Developer Approve/Reject Owner (Telegram Action)');
    console.log('4. Owner Connect WhatsApp Business Number');
    console.log('5. Player "I Have Team" Booking flow (WhatsApp to Business Bot)');
    console.log('6. Mock Player Payment (Razorpay Booking Pay)');
    console.log('7. Single Player "Join Team" flow (WhatsApp to Business Bot)');
    console.log('8. Team Captain Accept/Reject player (WhatsApp reply)');
    console.log('9. Owner Dashboard Commands (/bookings, /revenue, /report)');
    console.log('10. Database Status & Reset Bot Database');
    console.log('0. Exit');

    const choice = await ask('\nEnter choice number: ');

    switch (choice.trim()) {
      case '1':
        await simulateOwnerRegistration();
        break;
      case '2':
        await simulateOwnerPayment();
        break;
      case '3':
        await simulateDeveloperAction();
        break;
      case '4':
        await simulateBusinessConnect();
        break;
      case '5':
        await simulatePlayerTeamBooking();
        break;
      case '6':
        await simulatePlayerBookingPayment();
        break;
      case '7':
        await simulateSinglePlayerJoin();
        break;
      case '8':
        await simulateCaptainAction();
        break;
      case '9':
        await simulateOwnerCommands();
        break;
      case '10':
        await viewDatabaseStatus();
        break;
      case '0':
        exit = true;
        break;
      default:
        console.log('Invalid choice.');
    }
  }

  rl.close();
  await prisma.$disconnect();
}

/**
 * Step 1: Owner Registration Onboarding Flow
 */
async function simulateOwnerRegistration() {
  console.log('\n=== OWNER REGISTRATION ONBOARDING ===');
  currentOwnerMobile = await ask(`Enter Owner Mobile Number [default: ${currentOwnerMobile}]: `) || currentOwnerMobile;
  
  // Clean onboarding session for this number
  await prisma.botSession.deleteMany({ where: { phone: currentOwnerMobile } });

  console.log('\n--- Simulating WhatsApp conversation on Onboarding Number ---');
  
  // Send "Hi"
  console.log(`[Owner ${currentOwnerMobile}]: "Hi"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, "Hi", prisma);

  // Read Name
  const name = await ask('Enter your Name: ');
  console.log(`[Owner ${currentOwnerMobile}]: "${name}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, name, prisma);

  // Read Turf Name
  const turf = await ask('Enter your Turf Name: ');
  console.log(`[Owner ${currentOwnerMobile}]: "${turf}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, turf, prisma);

  // Read Location
  const location = await ask('Enter Turf Location: ');
  console.log(`[Owner ${currentOwnerMobile}]: "${location}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, location, prisma);

  // Read Photos
  const photos = await ask('Provide photo links/description: ');
  console.log(`[Owner ${currentOwnerMobile}]: "${photos}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, photos, prisma);

  // GST
  const gst = await ask('Enter GST (or type SKIP): ');
  console.log(`[Owner ${currentOwnerMobile}]: "${gst}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, gst, prisma);

  // MSME
  const msme = await ask('Enter MSME (or type SKIP): ');
  console.log(`[Owner ${currentOwnerMobile}]: "${msme}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, msme, prisma);

  // Opening Time
  const openTime = await ask('Enter Turf Opening Time (e.g. 06:00 AM): ');
  console.log(`[Owner ${currentOwnerMobile}]: "${openTime}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, openTime, prisma);

  // Closing Time
  const closeTime = await ask('Enter Turf Closing Time (e.g. 10:00 PM): ');
  console.log(`[Owner ${currentOwnerMobile}]: "${closeTime}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, closeTime, prisma);
}

/**
 * Step 2: Simulate Razorpay Subscription Payment for Owner
 */
async function simulateOwnerPayment() {
  console.log('\n=== MOCK OWNER SUBSCRIPTION PAYMENT (Razorpay ₹699) ===');
  const owner = await prisma.botOwner.findFirst({
    where: { mobile: currentOwnerMobile }
  });

  if (!owner) {
    console.log('No owner registration found in DB for this phone. Run Step 1 first.');
    return;
  }

  console.log(`Owner Found: ${owner.name} (${owner.turfName})`);
  const confirm = await ask('Simulate Payment Succeeded callback? (y/n): ');

  if (confirm.toLowerCase() === 'y') {
    clearMockMessages();
    clearMockTelegramMessages();

    // Perform DB update and webhook simulation
    await prisma.botSession.upsert({
      where: { phone: owner.mobile },
      update: { state: 'ONBOARDING_AWAITING_VERIFICATION' },
      create: { phone: owner.mobile, role: 'ONBOARDING', state: 'ONBOARDING_AWAITING_VERIFICATION' }
    });

    console.log('\nProcessing Payment...');
    await whatsappService_sendText(
      owner.mobile,
      `💳 Payment of ₹699 verified successfully! Your details have been sent to the developer for verification.`
    );

    await telegramService_sendVerificationAlert(owner);
    console.log('Done. Check Telegram notifications log output above.');
  }
}

/**
 * Step 3: Developer Action (Approve/Reject) on Telegram
 */
async function simulateDeveloperAction() {
  console.log('\n=== DEVELOPER APPROVE/REJECT (Telegram Bot Webhook) ===');
  const owner = await prisma.botOwner.findFirst({
    where: { mobile: currentOwnerMobile }
  });

  if (!owner) {
    console.log('No owner found in DB. Run Step 1 & 2 first.');
    return;
  }

  console.log(`Reviewing Registration: ${owner.name} - ${owner.turfName}`);
  console.log('1. Approve Owner');
  console.log('2. Reject Owner');
  const action = await ask('Select action (1/2): ');

  const mockReq = {
    body: {
      callback_query: {
        id: `cb_${Date.now()}`,
        data: action === '1' ? `verify_approve_${owner.id}` : `verify_reject_${owner.id}`,
        message: {
          chat: { id: 123456 },
          message_id: 789,
          text: `Owner Verification Request`
        }
      }
    }
  };

  const mockRes = {
    sendStatus: (status) => console.log(`Telegram webhook response: Status ${status}`)
  };

  clearMockMessages();
  await handleTelegramWebhook(mockReq, mockRes, prisma);
}

/**
 * Step 4: Owner Connect WhatsApp Business Number
 */
async function simulateBusinessConnect() {
  console.log('\n=== OWNER WHATSAPP BUSINESS CONNECT ===');
  const owner = await prisma.botOwner.findFirst({
    where: { mobile: currentOwnerMobile }
  });

  if (!owner || !owner.verified) {
    console.log('Owner is not registered or not verified yet. Perform Step 1, 2, and 3 first.');
    return;
  }

  currentBusinessNumber = await ask(`Enter Owner Business Number [default: ${currentBusinessNumber}]: `) || currentBusinessNumber;

  console.log(`[Owner ${currentOwnerMobile}]: "/connect ${currentBusinessNumber}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentOwnerMobile, ONBOARDING_NUMBER, `/connect ${currentBusinessNumber}`, prisma);
}

/**
 * Step 5: Player Booking Flow (I Have Team)
 */
async function simulatePlayerTeamBooking() {
  console.log('\n=== PLAYER "I HAVE TEAM" BOOKING FLOW ===');
  const owner = await prisma.botOwner.findFirst({
    where: { mobile: currentOwnerMobile, verified: true }
  });

  if (!owner || !owner.businessPhone) {
    console.log('Active Turf Owner is required. Complete Owner Onboarding first.');
    return;
  }

  currentPlayerMobile = await ask(`Enter Player Mobile [default: ${currentPlayerMobile}]: `) || currentPlayerMobile;

  // Clean player sessions
  await prisma.botSession.deleteMany({ where: { phone: currentPlayerMobile } });

  console.log(`\n--- Simulating Chat to Turf Business Bot (${owner.businessPhone}) ---`);
  
  // 1. Send "Hi"
  console.log(`[Player ${currentPlayerMobile}]: "Hi"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentPlayerMobile, owner.businessPhone, "Hi", prisma);

  // 2. Select Option 1 (I Have Team)
  console.log(`[Player ${currentPlayerMobile}]: "1" (I Have Team)`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentPlayerMobile, owner.businessPhone, "1", prisma);

  // 3. Select Date
  console.log(`[Player ${currentPlayerMobile}]: "1" (Today)`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentPlayerMobile, owner.businessPhone, "1", prisma);

  // 4. Select Slot Time
  const time = await ask('Type Available Time Slot (e.g. "06:00 PM", "07:00 PM"): ');
  console.log(`[Player ${currentPlayerMobile}]: "${time}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentPlayerMobile, owner.businessPhone, time, prisma);

  // 5. Enter details Name - TeamName
  const details = await ask('Enter details (Format: Name - TeamName): ');
  console.log(`[Player ${currentPlayerMobile}]: "${details}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentPlayerMobile, owner.businessPhone, details, prisma);
}

/**
 * Step 6: Mock Player Booking Payment (Razorpay ₹1030)
 */
async function simulatePlayerBookingPayment() {
  console.log('\n=== MOCK PLAYER BOOKING PAYMENT ===');
  
  const session = await prisma.botSession.findUnique({
    where: { phone: currentPlayerMobile }
  });

  if (!session || session.state !== 'AWAITING_PAYMENT_CONFIRMATION') {
    console.log('No booking session awaiting payment. Run Step 5 first.');
    return;
  }

  const context = JSON.parse(session.context || '{}');
  console.log(`Awaiting payment for: ${context.captainName} - Team ${context.teamName}`);
  console.log(`Slot: ${context.selectedDate} @ ${context.selectedSlot}`);

  const confirm = await ask('Complete mock Razorpay payment? (y/n): ');
  if (confirm.toLowerCase() === 'y') {
    clearMockMessages();
    clearMockTelegramMessages();

    // Perform database operations
    const slot = await prisma.botTurfSlot.upsert({
      where: { ownerId_date_timeSlot: { ownerId: context.turfId, date: context.selectedDate, timeSlot: context.selectedSlot } },
      update: { status: 'BOOKED' },
      create: { ownerId: context.turfId, date: context.selectedDate, timeSlot: context.selectedSlot, status: 'BOOKED' }
    });

    await prisma.botBooking.create({
      data: {
        slotId: slot.id,
        teamName: context.teamName,
        captainName: context.captainName,
        captainPhone: currentPlayerMobile,
        amountPaid: 1000, // INR 1000 turf rate
        paymentId: `pay_mock_${Date.now()}`
      }
    });

    await prisma.botSession.deleteMany({ where: { phone: currentPlayerMobile } });

    const owner = await prisma.botOwner.findUnique({ where: { id: context.turfId } });

    console.log('\nProcessing Booking Payment Confirmation...');
    // Notifications
    await whatsappService_sendText(currentPlayerMobile, `🎉 *Booking Confirmed!* 🎉\nYour slot at ${owner.turfName} is locked.`);
    await whatsappService_sendText(owner.mobile, `📅 *New Booking Alert!* Turf slot booked for ${context.selectedDate} @ ${context.selectedSlot}.`);
    await telegramService_sendAlert(`New Booking Confirmed! Turf: ${owner.turfName} | Slot: ${context.selectedDate} @ ${context.selectedSlot}`);

    console.log('Booking completed successfully.');
  }
}

/**
 * Step 7: Single Player Join Request Flow
 */
async function simulateSinglePlayerJoin() {
  console.log('\n=== SINGLE PLAYER JOIN FLOW ===');
  const owner = await prisma.botOwner.findFirst({
    where: { mobile: currentOwnerMobile, verified: true }
  });

  if (!owner || !owner.businessPhone) {
    console.log('Active Turf Owner is required.');
    return;
  }

  currentSinglePlayerMobile = await ask(`Enter Single Player Mobile [default: ${currentSinglePlayerMobile}]: `) || currentSinglePlayerMobile;
  await prisma.botSession.deleteMany({ where: { phone: currentSinglePlayerMobile } });

  console.log(`\n--- Simulating Single Player Chat to Bot (${owner.businessPhone}) ---`);
  
  // 1. Send "Hi"
  console.log(`[Player ${currentSinglePlayerMobile}]: "Hi"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentSinglePlayerMobile, owner.businessPhone, "Hi", prisma);

  // 2. Select Option 2 (Single Player)
  console.log(`[Player ${currentSinglePlayerMobile}]: "2" (Single Player)`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentSinglePlayerMobile, owner.businessPhone, "2", prisma);

  // 3. Select Date
  console.log(`[Player ${currentSinglePlayerMobile}]: "1" (Today)`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentSinglePlayerMobile, owner.businessPhone, "1", prisma);

  // 4. Select Booked slot time slot to join
  const time = await ask('Type Booked Time Slot to Join (e.g. "06:00 PM", "07:00 PM"): ');
  console.log(`[Player ${currentSinglePlayerMobile}]: "${time}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentSinglePlayerMobile, owner.businessPhone, time, prisma);

  // 5. Enter player Name
  const name = await ask('Enter Single Player Name: ');
  console.log(`[Player ${currentSinglePlayerMobile}]: "${name}"`);
  clearMockMessages();
  await handleWhatsAppWebhook(currentSinglePlayerMobile, owner.businessPhone, name, prisma);
}

/**
 * Step 8: Captain Action (Accept / Reject) Join Request
 */
async function simulateCaptainAction() {
  console.log('\n=== TEAM CAPTAIN ACTION (Accept / Reject player Join request) ===');
  
  // Search for pending join request
  const request = await prisma.botJoinRequest.findFirst({
    where: { status: 'PENDING' },
    include: { booking: { include: { slot: { include: { owner: true } } } } },
    orderBy: { createdAt: 'desc' }
  });

  if (!request) {
    console.log('No pending single player join requests found in DB.');
    return;
  }

  console.log(`Pending Request Found:`);
  console.log(`• Single Player: ${request.playerName} (${request.playerPhone})`);
  console.log(`• Captain: ${request.booking.captainName} (${request.booking.captainPhone})`);
  console.log(`• Slot: ${request.booking.slot.date} @ ${request.booking.slot.timeSlot}`);

  console.log('\nOptions:');
  console.log('1. Captain Accepts Request (specify amount)');
  console.log('2. Captain Rejects Request');
  const action = await ask('Select action (1/2): ');

  if (action === '1') {
    const amount = await ask('Enter Joining Fee Captain charges (e.g. 150): ');
    console.log(`[Captain ${request.booking.captainPhone}]: "ACCEPT ${amount}"`);
    clearMockMessages();
    await handleWhatsAppWebhook(request.booking.captainPhone, request.booking.slot.owner.businessPhone, `ACCEPT ${amount}`, prisma);
  } else if (action === '2') {
    console.log(`[Captain ${request.booking.captainPhone}]: "REJECT"`);
    clearMockMessages();
    await handleWhatsAppWebhook(request.booking.captainPhone, request.booking.slot.owner.businessPhone, `REJECT`, prisma);
  }
}

/**
 * Step 9: Owner Commands Test
 */
async function simulateOwnerCommands() {
  console.log('\n=== OWNER DASHBOARD COMMANDS ===');
  const owner = await prisma.botOwner.findFirst({
    where: { mobile: currentOwnerMobile, verified: true }
  });

  if (!owner || !owner.businessPhone) {
    console.log('Verified Owner with connected Business number is required.');
    return;
  }

  console.log(`Messaging Turf Business Number (${owner.businessPhone}) from Owner Number (${owner.mobile})`);
  console.log('Commands:');
  console.log('1. Show Bookings Summary (/bookings)');
  console.log('2. Show Revenue Metrics (/revenue)');
  console.log('3. Generate Earnings Report PDF (/report)');
  console.log('4. Block Slot (/block YYYY-MM-DD HH:MM)');
  const opt = await ask('Select Command Number (1-4): ');

  clearMockMessages();
  if (opt === '1') {
    await handleWhatsAppWebhook(owner.mobile, owner.businessPhone, '/bookings', prisma);
  } else if (opt === '2') {
    await handleWhatsAppWebhook(owner.mobile, owner.businessPhone, '/revenue', prisma);
  } else if (opt === '3') {
    await handleWhatsAppWebhook(owner.mobile, owner.businessPhone, '/report', prisma);
  } else if (opt === '4') {
    const date = await ask('Enter Date to Block (YYYY-MM-DD): ');
    const slot = await ask('Enter Time to Block (e.g. "08:00 PM"): ');
    await handleWhatsAppWebhook(owner.mobile, owner.businessPhone, `/block ${date} ${slot}`, prisma);
  }
}

/**
 * Helper to view database metrics or wipe database
 */
async function viewDatabaseStatus() {
  console.log('\n=== BOT DATABASE STATUS SUMMARY ===');
  const ownersCount = await prisma.botOwner.count();
  const bookingsCount = await prisma.botBooking.count();
  const slotsCount = await prisma.botTurfSlot.count();
  const joinsCount = await prisma.botJoinRequest.count();
  const sessionsCount = await prisma.botSession.count();

  console.log(`• WhatsApp Owners: ${ownersCount}`);
  console.log(`• WhatsApp Turf Slots: ${slotsCount}`);
  console.log(`• WhatsApp Bookings: ${bookingsCount}`);
  console.log(`• WhatsApp Single Join Requests: ${joinsCount}`);
  console.log(`• Active Bot Conversations: ${sessionsCount}`);

  const wipe = await ask('\nDo you want to RESET/WIPE only the WhatsApp Bot tables? (y/n): ');
  if (wipe.toLowerCase() === 'y') {
    await prisma.botJoinRequest.deleteMany();
    await prisma.botBooking.deleteMany();
    await prisma.botTurfSlot.deleteMany();
    await prisma.botSession.deleteMany();
    await prisma.botOwner.deleteMany();
    console.log('WhatsApp Bot tables cleared. Main application tables were left untouched.');
  }
}

// Low-level helpers
async function whatsappService_sendText(to, text) {
  console.log(`\n--- [MOCK WHATSAPP OUTGOING to ${to}] ---`);
  console.log(text);
  console.log('-------------------------------------------------\n');
}

async function telegramService_sendVerificationAlert(owner) {
  console.log(`\n=== [MOCK TELEGRAM ALERT to Admin] ===`);
  console.log(`🆕 New Owner Onboarding:\nOwner: ${owner.name}\nTurf: ${owner.turfName}\nMobile: ${owner.mobile}`);
  console.log(`Buttons: [✅ Approve Owner] (verify_approve_${owner.id})  [❌ Reject Owner] (verify_reject_${owner.id})`);
  console.log('==============================================\n');
}

async function telegramService_sendAlert(text) {
  console.log(`\n=== [MOCK TELEGRAM ALERT to Admin] ===`);
  console.log(text);
  console.log('==============================================\n');
}

// Start CLI
main().catch(err => {
  console.error('Simulator Execution Failed:', err);
  rl.close();
});
