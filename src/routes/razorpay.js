import * as whatsappService from '../services/whatsappService.js';
import * as telegramService from '../services/telegramService.js';
import express from 'express';

const router = express.Router();

router.post('/webhook', async (req, res) => {
  const prisma = req.app.get('prisma');
  res.sendStatus(200);
});

/**
 * MOCK ENDPOINT: Simulates a successful Owner Onboarding Subscription Payment (₹699)
 */
router.post('/mock-sub-pay', async (req, res) => {
  const prisma = req.app.get('prisma');
  const { ownerId } = req.body;

  try {
    const owner = await prisma.botOwner.findUnique({ where: { id: parseInt(ownerId, 10) } });
    if (!owner) {
      return res.status(404).json({ error: 'Owner not found' });
    }

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
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * MOCK ENDPOINT: Simulates a successful Player Booking Payment (₹1030)
 */
router.post('/mock-booking-pay', async (req, res) => {
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
    res.status(500).json({ error: err.message });
  }
});

/**
 * MOCK ENDPOINT: Simulates a successful Single Player Join Request Platform Fee Payment (₹9)
 */
router.post('/mock-join-pay', async (req, res) => {
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
      // Send Join Request notification to Team Captain
      await whatsappService.sendText(
        booking.captainPhone,
        `🔔 *Join Request for your booking at ${booking.slot.owner.turfName}!* 🔔\n\n` +
        `Hello ${booking.captainName}, an individual player wants to join your time slot:\n\n` +
        `• Player Name: *${joinReq.playerName}*\n` +
        `• Booking Slot: ${booking.slot.date} @ ${booking.slot.timeSlot}\n\n` +
        `Reply to this message with:\n` +
        `👉 *ACCEPT [Amount]* to accept them and specify what they should pay you directly (e.g. "ACCEPT 150")\n` +
        `👉 *REJECT* to deny their request.\n\n` +
        `_Powered by STRIKIT_`
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
    res.status(500).json({ error: err.message });
  }
});

export default router;
