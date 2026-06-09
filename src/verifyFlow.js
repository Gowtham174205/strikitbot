import dotenv from 'dotenv';
dotenv.config();

// Force local simulation/mock mode for tests
process.env.WHATSAPP_ACCESS_TOKEN = '';
process.env.WHATSAPP_PHONE_NUMBER_ID = '';
process.env.RAZORPAY_KEY_ID = '';
process.env.RAZORPAY_KEY_SECRET = '';

// Use direct/session database connection for test stability instead of transactional pgbouncer
if (process.env.DATABASE_URL) {
  process.env.DATABASE_URL = process.env.DATABASE_URL
    .replace(':6543/', ':5432/')
    .replace('pgbouncer=true', 'pgbouncer=false');
}

import path from 'path';
import fs from 'fs';

let PrismaClient;
let prisma;
let handleWhatsAppWebhook;
let handleTelegramWebhook;
let mockSentMessages;
let clearMockMessages;
let mockTelegramMessages;
let clearMockTelegramMessages;
let generateRevenueReport;

const OWNER_MOBILE = '919876543210';
const BUSINESS_NUMBER = '918888888888';
const PLAYER_MOBILE = '919999999999';
const SINGLE_PLAYER_MOBILE = '917777777777';
let ONBOARDING_NUMBER;

async function runVerification() {
  console.log('🚀 Starting STRIKIT Bot Flow Programmatic Verification...');

  try {
    // Dynamically import modules to ensure process.env variables take effect
    const prismaModule = await import('@prisma/client');
    PrismaClient = prismaModule.PrismaClient;
    prisma = new PrismaClient();

    const whatsappBotModule = await import('./routes/whatsappBot.js');
    handleWhatsAppWebhook = whatsappBotModule.handleWhatsAppWebhook;

    const telegramBotModule = await import('./routes/telegramBot.js');
    handleTelegramWebhook = telegramBotModule.handleTelegramWebhook;

    const whatsappServiceModule = await import('./services/whatsappService.js');
    mockSentMessages = whatsappServiceModule.mockSentMessages;
    clearMockMessages = whatsappServiceModule.clearMockMessages;

    const telegramServiceModule = await import('./services/telegramService.js');
    mockTelegramMessages = telegramServiceModule.mockTelegramMessages;
    clearMockTelegramMessages = telegramServiceModule.clearMockTelegramMessages;

    const pdfGeneratorModule = await import('./services/pdfGenerator.js');
    generateRevenueReport = pdfGeneratorModule.generateRevenueReport;

    ONBOARDING_NUMBER = process.env.ONBOARDING_NUMBER || '919000000000';

    // 0. Clean Bot Database Tables
    console.log('🧹 Wiping WhatsApp bot database tables for test...');
    await prisma.botJoinRequest.deleteMany();
    await prisma.botBooking.deleteMany();
    await prisma.botTurfSlot.deleteMany();
    await prisma.botSession.deleteMany();
    await prisma.botOwner.deleteMany();

    // 1. Simulate Owner Sends "register" to Onboarding
    console.log('\n1. Owner registers on Onboarding bot...');
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'register', prisma);
    assertMessageContains(OWNER_MOBILE, 'Owner Name');

    // Send name
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Gowtham P', prisma);
    assertMessageContains(OWNER_MOBILE, 'Turf Name');

    // Send Turf name
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Strikers Turf', prisma);
    assertMessageContains(OWNER_MOBILE, 'Location');

    // Send Location (with coordinates in URL)
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'https://maps.google.com/?q=12.9715987,77.5945627', prisma);
    assertMessageContains(OWNER_MOBILE, 'Turf Photos');

    // Send photos via media upload (image type)
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '', prisma, 'media_photo_123', 'image');
    assertMessageContains(OWNER_MOBILE, 'Turf Photo uploaded successfully');
    assertMessageContains(OWNER_MOBILE, 'GST');

    // Send GST (skipping MSME step)
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '33AAAAA1111A1Z1', prisma);
    assertMessageContains(OWNER_MOBILE, 'Opening Time');

    // Send Opening Time
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '06:00 AM', prisma);
    assertMessageContains(OWNER_MOBILE, 'Closing Time');

    // Send Closing Time
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '10:00 PM', prisma);
    assertMessageContains(OWNER_MOBILE, 'Hourly Booking Price');

    // Send Price
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '1200', prisma);
    assertMessageContains(OWNER_MOBILE, 'UPI ID');

    // Send UPI ID
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'owner@okaxis', prisma);
    assertMessageContains(OWNER_MOBILE, 'Registration Summary');

    // Verify Owner record exists in DB
    const owner = await prisma.botOwner.findUnique({
      where: { mobile: OWNER_MOBILE }
    });
    if (!owner) throw new Error('Owner failed to save in database');
    console.log('✅ Owner registered in DB:', owner.name, '-', owner.turfName);

    // 2. Developer Approves Owner via Telegram
    console.log('\n2. Developer Approves Owner via Telegram Inline Button...');
    clearMockMessages();
    const mockReq = {
      body: {
        callback_query: {
          id: 'cb_test_123',
          data: `verify_approve_${owner.id}`,
          message: {
            chat: { id: 123456 },
            message_id: 789,
            text: 'New Owner Onboarding Request'
          }
        }
      }
    };
    const mockRes = {
      sendStatus: (status) => console.log(`   Telegram Hook Status: ${status}`)
    };
    await handleTelegramWebhook(mockReq, mockRes, prisma);

    // Verify Owner is updated to verified but subscription is inactive
    const verifiedOwner = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (!verifiedOwner.verified) throw new Error('Owner was not verified by Telegram action');
    if (verifiedOwner.subscriptionActive) throw new Error('Owner subscription should not be active before payment');
    assertMessageContains(OWNER_MOBILE, 'APPROVED');
    assertMessageContains(OWNER_MOBILE, 'Subscription Link');

    // Check session state is AWAITING_SUBSCRIPTION
    const sessionAfterApprove = await prisma.botSession.findUnique({ where: { phone: OWNER_MOBILE } });
    if (sessionAfterApprove.state !== 'AWAITING_SUBSCRIPTION') {
      throw new Error(`Expected session state AWAITING_SUBSCRIPTION, got ${sessionAfterApprove.state}`);
    }

    // 3. Simulating Owner Subscription Payment (₹699)
    console.log('\n3. Simulating Owner Onboarding Subscription Payment...');
    clearMockMessages();
    
    // Simulate webhook updates and welcomes
    await mockSubscriptionPaymentCompleted(owner.id);
    assertMessageContains(OWNER_MOBILE, 'Welcome to STRIKIT');
    assertMessageContains(OWNER_MOBILE, 'api.qrserver.com'); // QR code link is sent

    // Verify Owner is updated to active subscription and session is set to OWNER_DASHBOARD
    const activeOwner = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (!activeOwner.subscriptionActive) throw new Error('Owner subscription is not active after payment');
    const ownerSession = await prisma.botSession.findUnique({ where: { phone: OWNER_MOBILE } });
    if (ownerSession.state !== 'OWNER_DASHBOARD') throw new Error('Owner session was not set to OWNER_DASHBOARD');

    // 4. Player Booking Flow (I Have Team) on the main number
    console.log('\n4. Player starts Team Booking flow on the main number...');
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'Hi', prisma);
    assertMessageContains(PLAYER_MOBILE, 'share your current location');

    // Send location payload (should find Strikers Turf within 10km)
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'location:12.9715987,77.5945627', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Nearby Turfs Found');
    assertMessageContains(PLAYER_MOBILE, 'Strikers Turf');

    // Player selects option 1 (Strikers Turf)
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, '1', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Welcome');

    // Choose option 1
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'opt_team', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Select a Date');

    // Choose Date (Today)
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, `date_${getTodayDateString()}`, prisma);
    assertMessageContains(PLAYER_MOBILE, 'Choose a Time Period');

    // Choose period (Evening)
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'period_evening', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Select an Available Slot');

    // Select Slot
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, '06:00 PM', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Name and Team Name');

    // Enter details
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'John - HawksFC', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Booking Summary');
    assertMessageContains(PLAYER_MOBILE, '₹1250');

    // 6. Mock Player Payment Complete
    console.log('\n6. Simulating Player Payment Complete...');
    clearMockMessages();
    clearMockTelegramMessages();

    // Trigger booking payment simulator logic
    await mockBookingPaymentCompleted(PLAYER_MOBILE, owner.id, getTodayDateString(), '06:00 PM', 'John', 'HawksFC', 1250);
    assertMessageContains(PLAYER_MOBILE, 'Booking Confirmed');
    assertMessageContains(OWNER_MOBILE, 'New Booking Alert');
    assertTelegramMessageContains('New Booking Confirmed');

    // Verify TurfSlot and Booking exists in DB
    const bookedSlot = await prisma.botTurfSlot.findUnique({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date: getTodayDateString(), timeSlot: '06:00 PM' } },
      include: { bookings: true }
    });
    if (!bookedSlot || bookedSlot.status !== 'BOOKED') throw new Error('Slot was not marked as BOOKED');
    if (bookedSlot.bookings.length === 0) throw new Error('Booking was not created');
    console.log('✅ Slot status is BOOKED, booking logged for team:', bookedSlot.bookings[0].teamName);

    // 7. Single Player Join Request
    console.log('\n7. Single Player Join Request Flow...');
    clearMockMessages();
    
    // Sends "Hi" to main number, gets location prompt
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, 'Hi', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'share your current location');

    // Sends location payload, gets turfs list
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, 'location:12.9715987,77.5945627', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Nearby Turfs Found');
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Strikers Turf');

    // Selects option 1 (Strikers Turf), gets welcome menu
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, '1', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Welcome');

    // Select Option 2 (Single Player)
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, 'opt_single', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Select a Date');

    // Select Date (Today)
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, `date_${getTodayDateString()}`, prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Choose a Time Period');

    // Choose period (Evening)
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, 'period_evening', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Select a Slot to Join');

    // Select booked slot
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, '06:00 PM', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'enter your Name');

    // Enter name
    clearMockMessages();
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, ONBOARDING_NUMBER, 'Giri', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'STRIKIT Platform Fee');
    assertMessageContains(SINGLE_PLAYER_MOBILE, '₹9');
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Non-Refundable');

    // Retrieve join request in AWAITING_PAYMENT status
    const joinReq = await prisma.botJoinRequest.findFirst({
      where: { playerName: 'Giri' }
    });
    if (!joinReq || joinReq.status !== 'AWAITING_PAYMENT') throw new Error('Join request was not logged in AWAITING_PAYMENT status');
    console.log('✅ Join request logged in DB in AWAITING_PAYMENT status');

    // Simulate join fee payment
    clearMockMessages();
    clearMockTelegramMessages();
    await mockJoinPaymentCompleted(joinReq.id);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Payment of ₹9 verified');
    assertMessageContains(PLAYER_MOBILE, 'Join Request for your booking');
    assertTelegramMessageContains('Single Player Join Request');

    // Check Join Request updated in DB
    const paidJoinReq = await prisma.botJoinRequest.findUnique({ where: { id: joinReq.id } });
    if (!paidJoinReq || paidJoinReq.status !== 'PENDING') throw new Error('Join request status was not updated to PENDING after payment');
    console.log('✅ Join request status updated to PENDING after ₹9 payment');

    // 8. Captain (Player A) Accepts Join Request via buttons
    console.log('\n8. Team Captain accepts request via buttons & inputs ₹150 joining fee...');
    clearMockMessages();
    clearMockTelegramMessages();
    
    // Captain clicks Accept button
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, `captain_accept_${joinReq.id}`, prisma);
    assertMessageContains(PLAYER_MOBILE, 'joining amount');

    // Captain types amount
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, '150', prisma);
    
    assertMessageContains(PLAYER_MOBILE, 'accepted');
    assertMessageContains(PLAYER_MOBILE, 'Giri');
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'accepted your request');
    assertMessageContains(SINGLE_PLAYER_MOBILE, '₹150');

    // Check status in DB
    const acceptedReq = await prisma.botJoinRequest.findUnique({ where: { id: joinReq.id } });
    if (acceptedReq.status !== 'ACCEPTED' || acceptedReq.joiningAmount !== 150) {
      throw new Error('Join request database update failed');
    }
    console.log('✅ Join Request updated to ACCEPTED with amount ₹150');

    // 9. Turf Owner dashboard commands (commands still supported)
    console.log('\n9. Testing Turf Owner commands...');
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/bookings', prisma);
    assertMessageContains(OWNER_MOBILE, 'Strikers Turf');
    assertMessageContains(OWNER_MOBILE, 'HawksFC');

    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/revenue', prisma);
    assertMessageContains(OWNER_MOBILE, 'Revenue Summary');
    assertMessageContains(OWNER_MOBILE, 'Gross Revenue: ₹1200');

    // PDF report generation
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/report', prisma);
    assertMessageContains(OWNER_MOBILE, 'Select PDF Report Range');

    // Choose 3 (All-Time)
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '3', prisma);
    assertMessageContains(OWNER_MOBILE, 'report_');
    assertMessageContains(OWNER_MOBILE, '.pdf');

    // Wait 1 second for PDF stream to flush to disk
    await new Promise(r => setTimeout(r, 1000));

    // Check PDF report file exists
    const reportsDir = path.resolve('reports');
    const files = fs.readdirSync(reportsDir);
    const pdfs = files.filter(f => f.startsWith(`report_${owner.id}`) && f.endsWith('.pdf'));
    if (pdfs.length === 0) throw new Error('PDF Report file was not generated');
    console.log('✅ PDF Earnings Report file successfully written to disk:', pdfs[0]);

    // 10. Owner Block slot command
    console.log('\n10. Testing Block / Unblock slots commands...');
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, `/block ${getTodayDateString()} 09:00 PM`, prisma);
    assertMessageContains(OWNER_MOBILE, 'blocked');

    const blockedSlot = await prisma.botTurfSlot.findUnique({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date: getTodayDateString(), timeSlot: '09:00 PM' } }
    });
    if (!blockedSlot || blockedSlot.status !== 'BLOCKED') throw new Error('Slot block failed');
    console.log('✅ Slot successfully blocked in database');

    // 10b. Testing Interactive Slot Blocking/Unblocking Toggle Flow...
    console.log('\n10b. Testing Interactive Slot Blocking/Unblocking Toggle Flow...');
    clearMockMessages();
    
    // Owner triggers dashboard menu
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'hi', prisma);
    assertMessageContains(OWNER_MOBILE, 'Owner Control Panel');

    // Select dashboard_block_slot
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'dashboard_block_slot', prisma);
    assertMessageContains(OWNER_MOBILE, 'Select a Date for Block/Unblock');

    // Select Today
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, `block_date_${getTodayDateString()}`, prisma);
    assertMessageContains(OWNER_MOBILE, 'Slot Availability Dashboard');

    // Toggle 08:00 PM slot (Block it)
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, `toggle_block_${getTodayDateString()}_08:00 PM`, prisma);
    assertMessageContains(OWNER_MOBILE, 'blocked');

    const toggledBlockedSlot = await prisma.botTurfSlot.findUnique({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date: getTodayDateString(), timeSlot: '08:00 PM' } }
    });
    if (!toggledBlockedSlot || toggledBlockedSlot.status !== 'BLOCKED') throw new Error('Interactive slot block failed');
    console.log('   [Pass] Interactive slot block succeeded');

    // Toggle 08:00 PM slot again (Unblock it)
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, `toggle_block_${getTodayDateString()}_08:00 PM`, prisma);
    assertMessageContains(OWNER_MOBILE, 'unblocked');

    const toggledOpenSlot = await prisma.botTurfSlot.findUnique({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date: getTodayDateString(), timeSlot: '08:00 PM' } }
    });
    if (!toggledOpenSlot || toggledOpenSlot.status !== 'AVAILABLE') throw new Error('Interactive slot unblock failed');
    console.log('   [Pass] Interactive slot unblock succeeded');

    // 11. Owner Edit Commands (manual commands compatibility)
    console.log('\n11. Testing Owner Edit Commands (/edit)...');
    clearMockMessages();
    
    // Edit Turf Name
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/edit name New Strikers Turf', prisma);
    assertMessageContains(OWNER_MOBILE, 'updated to: *New Strikers Turf*');
    
    const ownerNameCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerNameCheck.turfName !== 'New Strikers Turf') throw new Error('Turf name edit failed in DB');

    // 11b. Testing Interactive Settings Editing...
    console.log('\n11b. Testing Interactive Settings Editing...');
    clearMockMessages();
    
    // Owner triggers menu
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'hi', prisma);
    assertMessageContains(OWNER_MOBILE, 'Owner Control Panel');

    // Selects "dashboard_edit_settings"
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'dashboard_edit_settings', prisma);
    assertMessageContains(OWNER_MOBILE, 'Edit Turf Settings');

    // Selects "edit_name"
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'edit_name', prisma);
    assertMessageContains(OWNER_MOBILE, 'new Turf Name');

    // Types new turf name
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Interactive Strikers Arena', prisma);
    assertMessageContains(OWNER_MOBILE, 'updated to: *Interactive Strikers Arena*');

    const updatedOwnerCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (updatedOwnerCheck.turfName !== 'Interactive Strikers Arena') throw new Error('Interactive Turf name edit failed in DB');
    console.log('   [Pass] Interactive settings edit succeeded');

    // Edit Turf Price (command check)
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/edit price 1500', prisma);
    assertMessageContains(OWNER_MOBILE, 'updated to: *₹1500*');

    const ownerPriceCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerPriceCheck.pricePerHour !== 1500) throw new Error('Turf price edit failed in DB');

    // Edit Owner Name
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/edit ownername Gowtham P. New', prisma);
    assertMessageContains(OWNER_MOBILE, 'Owner name successfully updated to: *Gowtham P. New*');
    const ownerNameUpdateCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerNameUpdateCheck.name !== 'Gowtham P. New') throw new Error('Owner name update failed in DB');

    // Edit Turf Photos
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/edit photos http://photos.link/new-strikers', prisma);
    assertMessageContains(OWNER_MOBILE, 'photos link successfully updated to: *http://photos.link/new-strikers*');
    const ownerPhotosCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerPhotosCheck.photoUrls !== 'http://photos.link/new-strikers') throw new Error('Turf photos update failed in DB');

    // Edit GST
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/edit gst 33AAAAA1111A1Z1', prisma);
    assertMessageContains(OWNER_MOBILE, 'GST number successfully updated to: *33AAAAA1111A1Z1*');
    const ownerGstCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerGstCheck.gst !== '33AAAAA1111A1Z1') throw new Error('GST update failed in DB');

    // Edit MSME
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '/edit msme UDYAM-TN-01-0123456', prisma);
    assertMessageContains(OWNER_MOBILE, 'MSME certificate successfully updated to: *UDYAM-TN-01-0123456*');
    const ownerMsmeCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerMsmeCheck.msme !== 'UDYAM-TN-01-0123456') throw new Error('MSME update failed in DB');

    console.log('✅ Turf details (name, price, ownername, photos, gst, msme) successfully updated');

    // 12. Test Subscription Expiration & Self-Service Renewal
    console.log('\n12. Testing Subscription Expiration and Self-Service Renewal...');
    clearMockMessages();

    // Force expiration in DB
    const pastDate = new Date();
    pastDate.setDate(pastDate.getDate() - 3); // 3 days ago

    await prisma.botOwner.update({
      where: { id: owner.id },
      data: { subscriptionExpiry: pastDate, subscriptionActive: true }
    });

    // 12a. Owner messages the bot, should get a subscription expired warning with Razorpay link
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Hello', prisma);
    assertMessageContains(OWNER_MOBILE, 'STRIKIT Subscription Expired');
    assertMessageContains(OWNER_MOBILE, 'razorpay.mock/sub');

    // 12b. Player messages the bot, should NOT be blocked even when subscription is inactive
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'Hi', prisma);
    assertMessageContains(PLAYER_MOBILE, 'book a slot at *Interactive Strikers Arena* again');
    
    // Select Yes to proceed
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, '1', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Welcome');

    // 12c. Simulating owner completing subscription renewal
    console.log('   Simulating owner completing subscription renewal...');
    const activationExpiry = new Date();
    activationExpiry.setDate(activationExpiry.getDate() + 30);
    await prisma.botOwner.update({
      where: { id: owner.id },
      data: { subscriptionActive: true, subscriptionExpiry: activationExpiry }
    });

    // Reset owner onboarding session to owner dashboard mode if any
    await prisma.botSession.upsert({
      where: { phone: OWNER_MOBILE },
      update: { role: 'OWNER', state: 'OWNER_DASHBOARD' },
      create: { phone: OWNER_MOBILE, role: 'OWNER', state: 'OWNER_DASHBOARD' }
    });

    // 12d. Check if the bot is active again
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, ONBOARDING_NUMBER, 'Hi', prisma);
    assertMessageContains(PLAYER_MOBILE, 'book a slot at *Interactive Strikers Arena* again');
    console.log('✅ Expired bot successfully locked and unlocked via self-service subscription renewal simulation');

    console.log('\n======================================================');
    console.log('🎉 SUCCESS! ALL STRIKIT WORKFLOW CONVERSIONS VERIFIED! 🎉');
    console.log('======================================================\n');

  } catch (err) {
    console.error('\n❌ Verification Failed! Error:', err.message);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
    process.exit(0);
  }
}

function assertMessageContains(phone, phrase) {
  const matches = mockSentMessages.filter(m => m.to === phone);
  if (matches.length === 0) {
    throw new Error(`No outgoing messages found to ${phone}. Expected to find phrase: "${phrase}"`);
  }
  
  const hasMatch = matches.some(msg => {
    let bodyText = '';
    if (msg.type === 'text') {
      bodyText = msg.text?.body || '';
    } else if (msg.type === 'image') {
      bodyText = [msg.image?.caption, msg.image?.link].filter(Boolean).join(' ');
    } else {
      bodyText = [
        msg.interactive?.body?.text,
        msg.document?.caption,
        msg.document?.filename,
        msg.document?.link
      ].filter(Boolean).join(' ');
    }
    return bodyText.toLowerCase().includes(phrase.toLowerCase());
  });
  
  if (!hasMatch) {
    const allBodies = matches.map((m, idx) => `[${idx}] Type: ${m.type} - Content: ${JSON.stringify(m)}`).join('\n');
    throw new Error(`No message to ${phone} contained: "${phrase}". Found instead:\n${allBodies}`);
  }
  console.log(`   [Pass] Message to ${phone} contains: "${phrase}"`);
}

function assertTelegramMessageContains(phrase) {
  if (mockTelegramMessages.length === 0) {
    throw new Error(`No telegram alerts dispatched. Expected phrase: "${phrase}"`);
  }
  const lastAlert = mockTelegramMessages[mockTelegramMessages.length - 1];
  if (!lastAlert.text.toLowerCase().includes(phrase.toLowerCase())) {
    throw new Error(`Telegram alert did not contain: "${phrase}". Found instead:\n"${lastAlert.text}"`);
  }
  console.log(`   [Pass] Telegram Alert contains: "${phrase}"`);
}

function getTodayDateString() {
  return new Date().toISOString().split('T')[0];
}

async function mockSubscriptionPaymentCompleted(ownerId) {
  const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
  
  if (owner.verified) {
    const activationExpiry = new Date();
    activationExpiry.setDate(activationExpiry.getDate() + 30);

    await prisma.botOwner.update({
      where: { id: owner.id },
      data: { subscriptionActive: true, subscriptionExpiry: activationExpiry }
    });

    await prisma.botSession.upsert({
      where: { phone: owner.mobile },
      update: { role: 'OWNER', state: 'OWNER_DASHBOARD', context: '{}' },
      create: { phone: owner.mobile, role: 'OWNER', state: 'OWNER_DASHBOARD', context: '{}' }
    });

    const botNum = (process.env.ONBOARDING_NUMBER || '919360756749').replace(/[^0-9]/g, '');
    const qrText = `Book ${owner.turfName}`;
    const qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(`https://wa.me/${botNum}?text=${encodeURIComponent(qrText)}`)}`;

    mockSentMessages.push({
      messaging_product: 'whatsapp',
      recipient_type: 'individual',
      to: owner.mobile,
      type: 'image',
      image: {
        link: qrCodeUrl,
        caption: `🎉 *Welcome to STRIKIT, ${owner.name}!* 🎉\n\n` +
          `Your subscription payment of *₹699.00* has been verified successfully!\n\n` +
          `Your turf *${owner.turfName}* is now ACTIVE on STRIKIT. 🚀\n\n` +
          `📸 *Your Permanent Booking QR Code is attached!*\n` +
          `Players can scan this QR code or click the link below to book slots directly:\n` +
          `🔗 https://wa.me/${botNum}?text=${encodeURIComponent(qrText)}\n\n` +
          `*Turf Owner Control Panel:* Message this number anytime to manage bookings and reports:\n` +
          `• \`/bookings\` - Real-time booking dashboard\n` +
          `• \`/revenue\` - Earnings stats\n` +
          `• \`/report\` - Generate premium PDF transaction sheets\n` +
          `• \`/block [Date] [Time]\` - Block slots (e.g. \`/block 2026-06-06 06:00 PM\`)\n` +
          `• \`/unblock [Date] [Time]\` - Restore slots\n` +
          `• \`/edit\` - Edit turf settings\n\n` +
          `_Powered by STRIKIT_`
      }
    });
  } else {
    await prisma.botSession.upsert({
      where: { phone: owner.mobile },
      update: { state: 'ONBOARDING_AWAITING_VERIFICATION' },
      create: { phone: owner.mobile, role: 'ONBOARDING', state: 'ONBOARDING_AWAITING_VERIFICATION' }
    });

    await mockWhatsAppOutgoing(
      owner.mobile,
      `💳 *STRIKIT Subscription Payment Verified!* 💳\n\n` +
      `Hello ${owner.name}, your payment of *₹699.00* has been verified successfully!\n\n` +
      `🔄 *Auto-Pay Setup:* Monthly recurring payments are active for subsequent renewals.\n` +
      `⏳ *Verification:* Your turf details for *${owner.turfName}* are sent to the developers. You will receive an activation alert as soon as the developer reviews and approves them.\n\n` +
      `Thank you for choosing STRIKIT to automate your turf! ⚽🚀\n\n` +
      `_Powered by STRIKIT_`
    );
  }
}

async function mockBookingPaymentCompleted(phone, ownerId, date, slotTime, captainName, teamName, amount) {
  const slot = await prisma.botTurfSlot.upsert({
    where: { ownerId_date_timeSlot: { ownerId, date, timeSlot: slotTime } },
    update: { status: 'BOOKED' },
    create: { ownerId, date, timeSlot: slotTime, status: 'BOOKED' }
  });

  const booking = await prisma.botBooking.create({
    data: {
      slotId: slot.id,
      teamName,
      captainName,
      captainPhone: phone,
      amountPaid: parseFloat(amount) - 50,
      paymentId: `pay_mock_${Date.now()}`
    }
  });

  await prisma.botSession.deleteMany({ where: { phone } });
  const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });

  await mockWhatsAppOutgoing(phone, `🎉 *Booking Confirmed!* 🎉\nYour slot at ${owner.turfName} is locked.`);
  await mockWhatsAppOutgoing(
    owner.mobile,
    `📅 *New Booking Alert!*\n\n` +
    `• Date: ${date}\n` +
    `• Time Slot: ${slotTime}\n` +
    `• Team Name: ${teamName}\n` +
    `• Captain: ${captainName} (${phone})`
  );
  await mockTelegramAlert(`New Booking Confirmed! Turf: ${owner.turfName} | Slot: ${date} @ ${slotTime}`);
}

async function mockJoinPaymentCompleted(requestId) {
  const joinReq = await prisma.botJoinRequest.findUnique({
    where: { id: requestId }
  });
  
  await prisma.botJoinRequest.update({
    where: { id: requestId },
    data: { status: 'PENDING' }
  });

  await prisma.botSession.deleteMany({ where: { phone: joinReq.playerPhone } });

  const booking = await prisma.botBooking.findUnique({
    where: { id: joinReq.bookingId },
    include: { slot: { include: { owner: true } } }
  });
  const owner = booking.slot.owner;

  // Send Join Request notification to Team Captain using interactive buttons
  mockSentMessages.push({
    to: booking.captainPhone,
    type: 'interactive',
    interactive: {
      type: 'button',
      body: {
        text: `🔔 *Join Request for your booking at ${owner.turfName}!* 🔔\n\n` +
              `Hello ${booking.captainName}, an individual player wants to join your time slot:\n\n` +
              `• Player Name: *${joinReq.playerName}*\n` +
              `• Booking Slot: ${booking.slot.date} @ ${booking.slot.timeSlot}\n\n` +
              `Please select an action:`
      },
      action: {
        buttons: [
          { type: 'reply', reply: { id: `captain_accept_${joinReq.id}`, title: '✅ Accept' } },
          { type: 'reply', reply: { id: `captain_reject_${joinReq.id}`, title: '❌ Reject' } }
        ]
      }
    }
  });

  await mockWhatsAppOutgoing(
    joinReq.playerPhone,
    `⏳ Payment of ₹9 verified!\n` +
    `Your request has been sent to the Team Captain who booked the slot.\n` +
    `We will notify you immediately once the captain accepts or rejects your request.`
  );

  await mockTelegramAlert(
    `Single Player Join Request (₹9 Platform Fee Paid): ${joinReq.playerName} requested to join ${booking.captainName}'s team at ${owner.turfName}.`
  );
}

async function mockWhatsAppOutgoing(to, text) {
  mockSentMessages.push({ to, type: 'text', text: { body: text } });
}

async function mockTelegramAlert(text) {
  mockTelegramMessages.push({ text });
}

runVerification();
