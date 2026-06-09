import * as whatsappService from '../services/whatsappService.js';
import * as telegramService from '../services/telegramService.js';
import * as payoutService from '../services/payoutService.js';
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
  const body = req.body;
  console.log('[Razorpay Webhook] Received webhook event:', body.event);

  if (body.event === 'payment_link.paid') {
    const paymentLink = body.payload?.payment_link?.entity;
    if (!paymentLink) {
      console.warn('[Razorpay Webhook] Webhook missing payment_link payload');
      return res.sendStatus(400);
    }

    const notes = paymentLink.notes || {};
    console.log('[Razorpay Webhook] Notes:', notes);

    try {
      if (notes.type === 'subscription') {
        const ownerId = parseInt(notes.ownerId, 10);
        const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
        if (!owner) {
          console.error(`[Razorpay Webhook] Owner not found for ID: ${ownerId}`);
          return res.sendStatus(404);
        }

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

          // Generate QR Code URL
          const botNum = (process.env.ONBOARDING_NUMBER || '919360756749').replace(/[^0-9]/g, '');
          const qrText = `Book ${owner.turfName}`;
          const qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(`https://wa.me/${botNum}?text=${encodeURIComponent(qrText)}`)}`;

          await whatsappService.sendImage(
            owner.mobile,
            qrCodeUrl,
            `🎉 *Welcome to STRIKIT, ${owner.name}!* 🎉\n\n` +
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
          );
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
        }
      } else if (notes.type === 'booking') {
        const { phone, ownerId, date, slotTime, captainName, teamName, amount } = notes;
        const owner = await prisma.botOwner.findUnique({ where: { id: parseInt(ownerId, 10) } });
        if (!owner) {
          console.error(`[Razorpay Webhook] Owner not found for ID: ${ownerId}`);
          return res.sendStatus(404);
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
            amountPaid: parseFloat(amount) - 50, // Deducting the updated ₹50 booking fee
            paymentId: paymentLink.id
          }
        });

        await prisma.botSession.deleteMany({ where: { phone } });

        // Execute automatic split payout to owner via RazorpayX
        let payoutStatusText = '';
        if (owner.upiId) {
          try {
            owner.prisma = prisma; // Attach prisma so payoutService can cache Contact/Fund IDs
            const payoutResult = await payoutService.executePayout({
              owner,
              amount: booking.amountPaid, // Turf rate (e.g., ₹1200)
              bookingId: booking.id
            });
            payoutStatusText = `\n• Payout Status: *${payoutResult.status.toUpperCase()}* (${payoutResult.simulated ? 'SIMULATED' : 'LIVE'})`;
          } catch (payoutErr) {
            console.error(`[Razorpay Webhook] Failed to execute split payout for booking ${booking.id}:`, payoutErr);
            payoutStatusText = `\n• Payout Status: *FAILED* (Manual transfer required)`;
            
            try {
              await telegramService.sendAlert(
                `⚠️ *Payout Failed Alert!* ⚠️\n` +
                `Turf: ${owner.turfName}\n` +
                `Owner: ${owner.name}\n` +
                `Amount: ₹${booking.amountPaid.toFixed(2)}\n` +
                `Error: ${payoutErr.message}`
              );
            } catch (teleErr) {
              console.error('Error sending Telegram payout failure alert:', teleErr);
            }
          }
        } else {
          console.warn(`[Razorpay Webhook] Skipping payout for owner ${owner.id} - no UPI ID configured.`);
          payoutStatusText = `\n• Payout Status: *SKIPPED* (No UPI ID set by Owner)`;
        }

        await whatsappService.sendText(
          phone,
          `🎉 *Booking Confirmed!* 🎉\n\n` +
          `Thank you ${captainName || 'Player'}, your booking at *${owner.turfName}* has been verified successfully!\n\n` +
          `📅 *Date:* ${date}\n` +
          `⏰ *Time Slot:* ${slotTime}\n` +
          `💰 *Amount Paid:* ₹${amount}\n` +
          `📍 *Directions:* ${owner.location}\n\n` +
          `Get ready for your match! ⚽🔥\n\n` +
          `_Powered by STRIKIT_`
        );

        await whatsappService.sendText(
          owner.mobile,
          `📅 *New Booking Alert for ${owner.turfName}!* 📅\n\n` +
          `Hello ${owner.name}, a new booking has been confirmed at your turf:\n\n` +
          `• Date: ${date}\n` +
          `• Time Slot: ${slotTime}\n` +
          `• Team Name: ${teamName}\n` +
          `• Captain Name: ${captainName} (${phone})\n` +
          `• Total Paid by Player: ₹${parseFloat(amount).toFixed(2)}\n` +
          `• Payout Sent to you: ₹${booking.amountPaid.toFixed(2)}${payoutStatusText}\n\n` +
          `The slot status has been updated to *BOOKED* in your inventory.\n\n` +
          `_Powered by STRIKIT_`
        );

        await telegramService.sendAlert(
          `New Booking Confirmed! ✅\n` +
          `Turf: ${owner.turfName}\n` +
          `Date: ${date}\n` +
          `Slot: ${slotTime}\n` +
          `Team: ${teamName}\n` +
          `Revenue: ₹${amount}\n` +
          `Turf Share: ₹${booking.amountPaid}${payoutStatusText}`
        );
      } else if (notes.type === 'join_request') {
        const { requestId, phone } = notes;
        const joinReq = await prisma.botJoinRequest.findUnique({
          where: { id: parseInt(requestId, 10) }
        });

        if (!joinReq) {
          console.error(`[Razorpay Webhook] Join Request not found for ID: ${requestId}`);
          return res.sendStatus(404);
        }

        const updatedReq = await prisma.botJoinRequest.update({
          where: { id: joinReq.id },
          data: { status: 'PENDING' }
        });

        await prisma.botSession.deleteMany({ where: { phone: joinReq.playerPhone } });

        const booking = await prisma.botBooking.findUnique({
          where: { id: joinReq.bookingId },
          include: { slot: { include: { owner: true } } }
        });

        if (booking) {
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

        await whatsappService.sendText(
          joinReq.playerPhone,
          `⏳ *STRIKIT Platform Fee Verified!* ⏳\n\n` +
          `Hello ${joinReq.playerName}, your platform fee of *₹9.00* has been successfully processed.\n\n` +
          `📬 *Status:* We have sent a request to the Team Captain of the *${booking ? booking.slot.timeSlot : 'selected'}* slot at *${booking ? booking.slot.owner.turfName : 'the turf'}*.\n` +
          `📲 We will notify you immediately via WhatsApp the moment the captain accepts or rejects your request. Stay tuned!\n\n` +
          `_Powered by STRIKIT_`
        );

        const turfName = booking ? booking.slot.owner.turfName : 'Unknown Turf';
        const captainName = booking ? booking.captainName : 'Captain';
        await telegramService.sendAlert(
          `Single Player Join Request (₹9 Platform Fee Paid): ${joinReq.playerName} requested to join ${captainName}'s team at ${turfName}.`
        );
      }
    } catch (dbErr) {
      console.error('[Razorpay Webhook] Database error processing webhook:', dbErr);
      return res.sendStatus(500);
    }
  }

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
        amountPaid: parseFloat(amount) - 50, // Deducting the updated ₹50 booking fee
        paymentId: `pay_mock_${Date.now()}`
      }
    });

    await prisma.botSession.deleteMany({ where: { phone } });

    // Execute automatic split payout to owner via RazorpayX (will simulate success if not fully configured)
    let payoutStatusText = '';
    if (owner.upiId) {
      try {
        owner.prisma = prisma; // Attach prisma so payoutService can cache Contact/Fund IDs
        const payoutResult = await payoutService.executePayout({
          owner,
          amount: booking.amountPaid, // Turf rate (e.g., ₹1200)
          bookingId: booking.id
        });
        payoutStatusText = `\n• Payout Status: *${payoutResult.status.toUpperCase()}* (${payoutResult.simulated ? 'SIMULATED' : 'LIVE'})`;
      } catch (payoutErr) {
        console.error(`[Razorpay Webhook Mock] Failed to execute split payout for booking ${booking.id}:`, payoutErr);
        payoutStatusText = `\n• Payout Status: *FAILED* (Manual transfer required)`;
      }
    } else {
      console.warn(`[Razorpay Webhook Mock] Skipping payout for owner ${owner.id} - no UPI ID configured.`);
      payoutStatusText = `\n• Payout Status: *SKIPPED* (No UPI ID set by Owner)`;
    }

    await whatsappService.sendText(
      phone,
      `⚽ *Booking Confirmed at ${owner.turfName}!* ⚽\n\n` +
      `Hello ${captainName}, thank you for booking with us! Your slot has been successfully reserved.\n\n` +
      `*Booking Details:*\n` +
      `• Turf: *${owner.turfName}*\n` +
      `• Date: ${date}\n` +
      `• Time Slot: ${slotTime}\n` +
      `• Team Name: ${teamName}\n` +
      `• Platform Fee Paid: ₹50.00\n` +
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
      `• Captain Name: ${captainName} (${phone})\n` +
      `• Total Paid by Player: ₹${parseFloat(amount).toFixed(2)}\n` +
      `• Payout Sent to you: ₹${booking.amountPaid.toFixed(2)}${payoutStatusText}\n\n` +
      `The slot status has been updated to *BOOKED* in your inventory.\n\n` +
      `_Powered by STRIKIT_`
    );

    await telegramService.sendAlert(
      `New Booking Confirmed! ✅\n` +
      `Turf: ${owner.turfName}\n` +
      `Date: ${date}\n` +
      `Slot: ${slotTime}\n` +
      `Team: ${teamName}\n` +
      `Revenue: ₹${amount}\n` +
      `Turf Share: ₹${booking.amountPaid}${payoutStatusText}`
    );

    res.json({ message: 'Mock booking payment processed successfully', booking, payoutStatusText });
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

