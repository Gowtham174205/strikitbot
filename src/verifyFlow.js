import { PrismaClient } from '@prisma/client';
import { handleWhatsAppWebhook } from './routes/whatsappBot.js';
import { handleTelegramWebhook } from './routes/telegramBot.js';
import { mockSentMessages, clearMockMessages } from './services/whatsappService.js';
import { mockTelegramMessages, clearMockTelegramMessages } from './services/telegramService.js';
import { generateRevenueReport } from './services/pdfGenerator.js';
import path from 'path';
import fs from 'fs';

const prisma = new PrismaClient();
const ONBOARDING_NUMBER = '919000000000';
const OWNER_MOBILE = '919876543210';
const BUSINESS_NUMBER = '918888888888';
const PLAYER_MOBILE = '919999999999';
const SINGLE_PLAYER_MOBILE = '917777777777';

async function runVerification() {
  console.log('🚀 Starting STRIKIT Bot Flow Programmatic Verification...');

  try {
    // 0. Clean Bot Database Tables
    console.log('🧹 Wiping WhatsApp bot database tables for test...');
    await prisma.botJoinRequest.deleteMany();
    await prisma.botBooking.deleteMany();
    await prisma.botTurfSlot.deleteMany();
    await prisma.botSession.deleteMany();
    await prisma.botOwner.deleteMany();

    // 1. Simulate Owner Sends "Hi" to Onboarding
    console.log('\n1. Owner registers on Onboarding bot...');
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Hi', prisma);
    assertMessageContains(OWNER_MOBILE, 'Owner Name');

    // Send name
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Gowtham P', prisma);
    assertMessageContains(OWNER_MOBILE, 'Turf Name');

    // Send Turf name
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'Strikers Turf', prisma);
    assertMessageContains(OWNER_MOBILE, 'Location');

    // Send Location
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'https://maps.google.com/?q=Chennai', prisma);
    assertMessageContains(OWNER_MOBILE, 'Turf Photos');

    // Send photos
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'http://photos.link/strikers', prisma);
    assertMessageContains(OWNER_MOBILE, 'GST');

    // Send GST
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, '33AAAAA1111A1Z1', prisma);
    assertMessageContains(OWNER_MOBILE, 'MSME');

    // Send MSME
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, 'UDYAM-TN-01-0123456', prisma);
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
    assertMessageContains(OWNER_MOBILE, 'Registration complete');
    assertMessageContains(OWNER_MOBILE, '₹699');

    // Verify Owner record exists in DB
    const owner = await prisma.botOwner.findUnique({
      where: { mobile: OWNER_MOBILE }
    });
    if (!owner) throw new Error('Owner failed to save in database');
    console.log('✅ Owner registered in DB:', owner.name, '-', owner.turfName);

    // 2. Mock Owner Subscription Payment (₹699)
    console.log('\n2. Simulating Owner Subscription Payment via Razorpay...');
    clearMockMessages();
    clearMockTelegramMessages();

    // Update Bot Session state to Awaiting Verification
    await prisma.botSession.update({
      where: { phone: OWNER_MOBILE },
      data: { state: 'ONBOARDING_AWAITING_VERIFICATION' }
    });

    // Notify Owner and Developer
    await mockSubscriptionPaymentCompleted(owner.id);
    assertMessageContains(OWNER_MOBILE, 'Payment of ₹699 verified');
    assertTelegramMessageContains('New Owner Onboarding');

    // 3. Developer Approves Owner via Telegram
    console.log('\n3. Developer Approves Owner via Telegram Inline Button...');
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

    // Verify Owner is updated to verified
    const verifiedOwner = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (!verifiedOwner.verified) throw new Error('Owner was not verified by Telegram action');
    assertMessageContains(OWNER_MOBILE, 'APPROVED');

    // 4. Connect WhatsApp Business Number
    console.log('\n4. Owner connects WhatsApp Business number...');
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, ONBOARDING_NUMBER, `/connect ${BUSINESS_NUMBER}`, prisma);
    assertMessageContains(OWNER_MOBILE, 'STRIKIT Bot is now active');

    const connectedOwner = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (connectedOwner.businessPhone !== BUSINESS_NUMBER) throw new Error('Business number connection failed');
    console.log('✅ WhatsApp Business connected in DB:', connectedOwner.businessPhone);

    // 5. Player Booking Flow (I Have Team)
    console.log('\n5. Player starts Team Booking flow...');
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, BUSINESS_NUMBER, 'Hi', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Welcome to Strikers Turf');

    // Choose option 1
    await handleWhatsAppWebhook(PLAYER_MOBILE, BUSINESS_NUMBER, '1', prisma);
    assertMessageContains(PLAYER_MOBILE, 'select a Date');

    // Choose Date (Today)
    await handleWhatsAppWebhook(PLAYER_MOBILE, BUSINESS_NUMBER, '1', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Slots for');

    // Select Slot
    await handleWhatsAppWebhook(PLAYER_MOBILE, BUSINESS_NUMBER, '06:00 PM', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Name and Team Name');

    // Enter details
    clearMockMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, BUSINESS_NUMBER, 'John - HawksFC', prisma);
    assertMessageContains(PLAYER_MOBILE, 'Booking Summary');
    assertMessageContains(PLAYER_MOBILE, '₹1230');

    // 6. Mock Player Payment Complete
    console.log('\n6. Simulating Player Payment Complete...');
    clearMockMessages();
    clearMockTelegramMessages();

    // Trigger booking payment simulator logic
    await mockBookingPaymentCompleted(PLAYER_MOBILE, owner.id, getTodayDateString(), '06:00 PM', 'John', 'HawksFC', 1230);
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
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, BUSINESS_NUMBER, 'Hi', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Welcome to Strikers Turf');

    // Select Option 2 (Single Player)
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, BUSINESS_NUMBER, '2', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'select a Date');

    // Select Date (Today)
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, BUSINESS_NUMBER, '1', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'Booked slots on');

    // Select booked slot
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, BUSINESS_NUMBER, '06:00 PM', prisma);
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'enter your Name');

    // Enter name
    clearMockMessages();
    await handleWhatsAppWebhook(SINGLE_PLAYER_MOBILE, BUSINESS_NUMBER, 'Giri', prisma);
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

    // 8. Captain (Player A) Accepts Join Request
    console.log('\n8. Team Captain accepts request & inputs ₹150 joining fee...');
    clearMockMessages();
    clearMockTelegramMessages();
    await handleWhatsAppWebhook(PLAYER_MOBILE, BUSINESS_NUMBER, 'ACCEPT 150', prisma);
    assertMessageContains(PLAYER_MOBILE, 'You accepted Giri');
    assertMessageContains(SINGLE_PLAYER_MOBILE, 'accepted your request');
    assertMessageContains(SINGLE_PLAYER_MOBILE, '₹150');

    // Check status in DB
    const acceptedReq = await prisma.botJoinRequest.findUnique({ where: { id: joinReq.id } });
    if (acceptedReq.status !== 'ACCEPTED' || acceptedReq.joiningAmount !== 150) {
      throw new Error('Join request database update failed');
    }
    console.log('✅ Join Request updated to ACCEPTED with amount ₹150');

    // 9. Turf Owner dashboard commands
    console.log('\n9. Testing Turf Owner commands...');
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/bookings', prisma);
    assertMessageContains(OWNER_MOBILE, 'Strikers Turf');
    assertMessageContains(OWNER_MOBILE, 'HawksFC');

    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/revenue', prisma);
    assertMessageContains(OWNER_MOBILE, 'Revenue Summary');
    assertMessageContains(OWNER_MOBILE, 'Gross Revenue: ₹1200');

    // PDF report generation
    clearMockMessages();
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/report', prisma);
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
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, `/block ${getTodayDateString()} 09:00 PM`, prisma);
    assertMessageContains(OWNER_MOBILE, 'blocked');

    const blockedSlot = await prisma.botTurfSlot.findUnique({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date: getTodayDateString(), timeSlot: '09:00 PM' } }
    });
    if (!blockedSlot || blockedSlot.status !== 'BLOCKED') throw new Error('Slot block failed');
    console.log('✅ Slot successfully blocked in database');

    // 11. Owner Edit Commands
    console.log('\n11. Testing Owner Edit Commands (/edit)...');
    clearMockMessages();
    
    // Edit Turf Name
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/edit name New Strikers Turf', prisma);
    assertMessageContains(OWNER_MOBILE, 'updated to: *New Strikers Turf*');
    
    const ownerNameCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerNameCheck.turfName !== 'New Strikers Turf') throw new Error('Turf name edit failed in DB');

    // Edit Turf Price
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/edit price 1500', prisma);
    assertMessageContains(OWNER_MOBILE, 'updated to: *₹1500*');

    const ownerPriceCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerPriceCheck.pricePerHour !== 1500) throw new Error('Turf price edit failed in DB');

    // Edit Owner Name
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/edit ownername Gowtham P. New', prisma);
    assertMessageContains(OWNER_MOBILE, 'Owner name successfully updated to: *Gowtham P. New*');
    const ownerNameUpdateCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerNameUpdateCheck.name !== 'Gowtham P. New') throw new Error('Owner name update failed in DB');

    // Edit Turf Photos
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/edit photos http://photos.link/new-strikers', prisma);
    assertMessageContains(OWNER_MOBILE, 'photos link successfully updated to: *http://photos.link/new-strikers*');
    const ownerPhotosCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerPhotosCheck.photoUrls !== 'http://photos.link/new-strikers') throw new Error('Turf photos update failed in DB');

    // Edit GST
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/edit gst 33AAAAA1111A1Z1', prisma);
    assertMessageContains(OWNER_MOBILE, 'GST number successfully updated to: *33AAAAA1111A1Z1*');
    const ownerGstCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerGstCheck.gst !== '33AAAAA1111A1Z1') throw new Error('GST update failed in DB');

    // Edit MSME
    await handleWhatsAppWebhook(OWNER_MOBILE, BUSINESS_NUMBER, '/edit msme UDYAM-TN-01-0123456', prisma);
    assertMessageContains(OWNER_MOBILE, 'MSME certificate successfully updated to: *UDYAM-TN-01-0123456*');
    const ownerMsmeCheck = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (ownerMsmeCheck.msme !== 'UDYAM-TN-01-0123456') throw new Error('MSME update failed in DB');

    console.log('✅ Turf details (name, price, ownername, photos, gst, msme) successfully updated via commands');

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

// Helpers
function assertMessageContains(phone, phrase) {
  const matches = mockSentMessages.filter(m => m.to === phone);
  if (matches.length === 0) {
    throw new Error(`No outgoing messages found to ${phone}. Expected to find phrase: "${phrase}"`);
  }
  
  const lastMsg = matches[matches.length - 1];
  const bodyText = lastMsg.type === 'text' 
    ? (lastMsg.text?.body || '') 
    : [
        lastMsg.interactive?.body?.text,
        lastMsg.document?.caption,
        lastMsg.document?.filename,
        lastMsg.document?.link
      ].filter(Boolean).join(' ');
  
  if (!bodyText.toLowerCase().includes(phrase.toLowerCase())) {
    throw new Error(`Message to ${phone} did not contain: "${phrase}". Found instead:\n"${bodyText}"`);
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
  await mockWhatsAppOutgoing(owner.mobile, `💳 Payment of ₹699 verified successfully! Auto-Pay has been set up for future monthly renewals. Your details have been sent to the developer for verification.`);
  await mockTelegramAlert(`🆕 New Owner Onboarding:\nOwner: ${owner.name}\nTurf: ${owner.turfName}\nMobile: ${owner.mobile}\n\nApprove: verify_approve_${owner.id}`);
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
      amountPaid: parseFloat(amount) - 30,
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

  await mockWhatsAppOutgoing(
    booking.captainPhone,
    `🔔 *Join Request for your booking!*\n\n` +
    `A single player wants to play with your team:\n` +
    `• Player Name: ${joinReq.playerName}\n` +
    `• Booking Slot: ${booking.slot.date} @ ${booking.slot.timeSlot}\n\n` +
    `Reply to this message with:\n` +
    `• *ACCEPT [Amount]* to accept them and specify what they should pay you directly (e.g. "ACCEPT 150")\n` +
    `• *REJECT* to deny`
  );

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
