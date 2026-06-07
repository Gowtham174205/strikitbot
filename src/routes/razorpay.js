import * as whatsappService from '../services/whatsappService.js';
import * as telegramService from '../services/telegramService.js';
import express from 'express';
import crypto from 'crypto';
import { requireAdminKey } from '../middleware/security.js';

const router = express.Router();

/**
 * POST /razorpay/webhook
 * Real Razorpay payment webhook — verify HMAC-SHA256 signature before processing.
 */
router.post('/webhook', async (req, res) => {
  const razorpaySecret = process.env.RAZORPAY_WEBHOOK_SECRET;

  if (razorpaySecret) {
    const sigHeader = req.headers['x-razorpay-signature'];
    if (!sigHeader) {
      console.warn('[SECURITY] Razorpay webhook received without signature header — rejected.');
      return res.status(403).json({ error: 'Forbidden: Missing Razorpay webhook signature' });
    }

    const rawBody = req.rawBody; // captured by server.js rawBody middleware
    const expectedSig = crypto
      .createHmac('sha256', razorpaySecret)
      .update(rawBody)
      .digest('hex');

    let sigMatch = false;
    try {
      const a = Buffer.from(expectedSig, 'utf8');
      const b = Buffer.from(sigHeader, 'utf8');
      if (a.length === b.length) {
        sigMatch = crypto.timingSafeEqual(a, b);
      }
    } catch {
      sigMatch = false;
    }

    if (!sigMatch) {
      console.warn('[SECURITY] Razorpay webhook signature mismatch — rejected.');
      return res.status(403).json({ error: 'Forbidden: Invalid Razorpay webhook signature' });
    }
  } else {
    console.warn('[SECURITY WARNING] RAZORPAY_WEBHOOK_SECRET not set — skipping Razorpay signature check.');
  }

  const prisma = req.app.get('prisma');
  // TODO: process real Razorpay payment events here
  res.sendStatus(200);
});

// ---------------------------------------------------------------------------
// MOCK PAYMENT ENDPOINTS (dev/test only)
// Protected by admin API key. Completely disabled in production NODE_ENV.
// ---------------------------------------------------------------------------
function blockInProduction(req, res, next) {
  if (process.env.NODE_ENV === 'production') {
    return res
      .status(404)
      .json({ error: 'Not found' });
  }
  next();
}



/**
 * MOCK ENDPOINT: Simulates a successful Owner Onboarding Subscription Payment (₹699)
 */
router.post('/mock-sub-pay', blockInProduction, requireAdminKey, async (req, res) => {
  const prisma = req.app.get('prisma');
  const { ownerId } = req.body;

  try {
    const owner = await prisma.botOwner.findUnique({ where: { id: parseInt(ownerId, 10) } });
    if (!owner) {
      return res.status(404).json({ error: 'Owner not found' });
    }

    if (owner.verified) {
      const activationExpiry = new Date();
      activationExpiry.setDate(activationExpiry.getDate() + 30); // Extend by 30 days

      await prisma.botOwner.update({
        where: { id: owner.id },
        data: { subscriptionActive: true, subscriptionExpiry: activationExpiry }
      });

      // Reset owner onboarding session to owner dashboard mode if any
      await prisma.botSession.upsert({
        where: { phone: owner.mobile },
        update: { role: 'OWNER', state: 'OWNER_DASHBOARD' },
        create: { phone: owner.mobile, role: 'OWNER', state: 'OWNER_DASHBOARD' }
      });

      await whatsappService.sendText(
        owner.mobile,
        `🎉 *STRIKIT Subscription Renewed!* 🎉\n\n` +
        `Hello ${owner.name}, your renewal payment of *₹699.00* has been verified successfully!\n\n` +
        `Your turf *${owner.turfName}* bot has been reactivated for the next 30 days! 🚀\n\n` +
        `_Powered by STRIKIT_`
      );

      return res.json({ message: 'Subscription renewed successfully.' });
    } else {
      await prisma.botSession.upsert({
        where: { phone: owner.mobile },
        update: { state: 'ONBOARDING_AWAITING_VERIFICATION' },
        create: { phone: owner.mobile, role: 'ONBOARDING', state: 'ONBOARDING_AWAITING_VERIFICATION' }
      });

      await whatsappService.sendText(
        owner.mobile,
        `💳 *STRIKIT Subscription Payment Verified!* 💳\n\n` +
        `Hello ${owner.name}, your payment of *₹699.00* has been verified successfully!\n\n` +
        `🔄 *Auto-Pay Setup:* Monthly recurring payments are active for subsequent renewals.\n` +
        `⏳ *Verification:* Your turf details for *${owner.turfName}* are sent to the developers. You will receive an activation alert as soon as the developer reviews and approves them.\n\n` +
        `Thank you for choosing STRIKIT to automate your turf! ⚽🚀\n\n` +
        `_Powered by STRIKIT_`
      );

      await telegramService.sendVerificationAlert(owner);
      await whatsappService.sendDeveloperVerificationAlert(owner);

      res.json({ message: 'Mock subscription payment completed and processed.' });
    }
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

/**
 * MOCK ENDPOINT: Simulates a successful Player Booking Payment (₹1030)
 */
router.post('/mock-booking-pay', blockInProduction, requireAdminKey, async (req, res) => {
  const prisma = req.app.get('prisma');
  const { phone, ownerId, date, slotTime, captainName, teamName, amount } = req.body;

  try {
    const owner = await prisma.botOwner.findUnique({ where: { id: parseInt(ownerId, 10) } });
    if (!owner) {
      return res.status(404).json({ error: 'Owner not found' });
    }

    const slot = await prisma.botTurfSlot.upsert({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date, timeSlot: slotTime } },
      update: { status: 'BOOKED' },
      create: { ownerId: owner.id, date, timeSlot: slotTime, status: 'BOOKED' }
    });

    const booking = await prisma.botBooking.create({
      data: {
        slotId: slot.id,
        teamName,
        captainName,
        captainPhone: phone,
        amountPaid: parseFloat(amount) - 30, // Deducting the booking fee
        paymentId: `pay_mock_${Date.now()}`
      }
    });

    await prisma.botSession.deleteMany({ where: { phone } });

    await whatsappService.sendText(
      phone,
      `⚽ *Booking Confirmed at ${owner.turfName}!* ⚽\n\n` +
      `Hello ${captainName}, thank you for booking with us! Your slot has been successfully reserved.\n\n` +
      `*Booking Details:*\n` +
      `• Turf: *${owner.turfName}*\n` +
      `• Date: ${date}\n` +
      `• Time Slot: ${slotTime}\n` +
      `• Team Name: ${teamName}\n` +
      `• Platform Fee Paid: ₹30.00\n` +
      `• Turf Amount Paid: ₹${booking.amountPaid.toFixed(2)}\n\n` +
      `Present this booking confirmation at the turf entrance. Have an amazing game! 🏃‍♂️🔥\n\n` +
      `_Powered by STRIKIT_`
    );

    await whatsappService.sendText(
      owner.mobile,
      `📅 *New Booking Alert for ${owner.turfName}!* 📅\n\n` +
      `Hello ${owner.name}, a new booking has been confirmed at your turf:\n\n` +
      `• Date: ${date}\n` +
      `• Time Slot: ${slotTime}\n` +
      `• Team Name: ${teamName}\n` +
      `• Captain Name: ${captainName} (${phone})\n\n` +
      `The slot status has been updated to *BOOKED* in your inventory.\n\n` +
      `_Powered by STRIKIT_`
    );

    await telegramService.sendAlert(
      `New Booking Confirmed! ✅\n` +
      `Turf: ${owner.turfName}\n` +
      `Date: ${date}\n` +
      `Slot: ${slotTime}\n` +
      `Team: ${teamName}\n` +
      `Revenue: ₹${amount}`
    );

    res.json({ message: 'Mock booking payment processed successfully', booking });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

/**
 * MOCK ENDPOINT: Simulates a successful Single Player Join Request Platform Fee Payment (₹9)
 */
router.post('/mock-join-pay', blockInProduction, requireAdminKey, async (req, res) => {
  const prisma = req.app.get('prisma');
  const { requestId, phone } = req.body;

  try {
    const joinReq = await prisma.botJoinRequest.findUnique({
      where: { id: parseInt(requestId, 10) }
    });

    if (!joinReq) {
      return res.status(404).json({ error: 'Join Request not found' });
    }

    // Update status to PENDING
    const updatedReq = await prisma.botJoinRequest.update({
      where: { id: joinReq.id },
      data: { status: 'PENDING' }
    });

    // Delete the player's session
    await prisma.botSession.deleteMany({ where: { phone: joinReq.playerPhone } });

    // Fetch booking to find the Team Captain
    const booking = await prisma.botBooking.findUnique({
      where: { id: joinReq.bookingId },
      include: { slot: { include: { owner: true } } }
    });

    if (booking) {
      // Send Join Request notification to Team Captain using interactive buttons
      await whatsappService.sendButtons(
        booking.captainPhone,
        `🔔 *Join Request for your booking at ${booking.slot.owner.turfName}!* 🔔\n\n` +
        `Hello ${booking.captainName}, an individual player wants to join your time slot:\n\n` +
        `• Player Name: *${joinReq.playerName}*\n` +
        `• Booking Slot: ${booking.slot.date} @ ${booking.slot.timeSlot}\n\n` +
        `Please select an action:`,
        [
          { id: `captain_accept_${joinReq.id}`, title: '✅ Accept' },
          { id: `captain_reject_${joinReq.id}`, title: '❌ Reject' }
        ]
      );
    }

    // Confirm to Single Player
    await whatsappService.sendText(
      joinReq.playerPhone,
      `⏳ *STRIKIT Platform Fee Verified!* ⏳\n\n` +
      `Hello ${joinReq.playerName}, your platform fee of *₹9.00* has been successfully processed.\n\n` +
      `📬 *Status:* We have sent a request to the Team Captain of the *${booking.slot.timeSlot}* slot at *${booking.slot.owner.turfName}*.\n` +
      `📲 We will notify you immediately via WhatsApp the moment the captain accepts or rejects your request. Stay tuned!\n\n` +
      `_Powered by STRIKIT_`
    );

    // Alert Telegram Log
    const turfName = booking ? booking.slot.owner.turfName : 'Unknown Turf';
    const captainName = booking ? booking.captainName : 'Captain';
    await telegramService.sendAlert(
      `Single Player Join Request (₹9 Platform Fee Paid): ${joinReq.playerName} requested to join ${captainName}'s team at ${turfName}.`
    );

    res.json({ message: 'Mock join request payment processed successfully', joinRequest: updatedReq });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

export default router;

