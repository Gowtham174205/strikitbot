import express from 'express';
import axios from 'axios';
import { requireAdminKey } from '../middleware/security.js';

const router = express.Router();

// Apply timing-safe admin API key verification to all routes in this router
router.use(requireAdminKey);


/**
 * GET /api/admin/owners
 * Retrieve all turf owners, with optional search query filtering by owner name, phone, or turf name.
 */
router.get('/owners', async (req, res) => {
  const prisma = req.app.get('prisma');
  const { search } = req.query;

  try {
    let where = {};
    if (search) {
      const queryStr = String(search).trim();
      where = {
        OR: [
          { name: { contains: queryStr, mode: 'insensitive' } },
          { mobile: { contains: queryStr, mode: 'insensitive' } },
          { turfName: { contains: queryStr, mode: 'insensitive' } }
        ]
      };
    }

    const owners = await prisma.botOwner.findMany({
      where,
      orderBy: { createdAt: 'desc' }
    });

    res.json(owners);
  } catch (err) {
    console.error('Error fetching owners:', err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

/**
 * POST /api/admin/owners/:id/approve
 * Verify a turf owner, activate their 2-day free trial, and transition onboarding session.
 */
router.post('/owners/:id/approve', async (req, res) => {
  const prisma = req.app.get('prisma');
  const ownerId = parseInt(req.params.id, 10);

  if (isNaN(ownerId)) {
    return res.status(400).json({ error: 'Invalid owner ID' });
  }

  try {
    const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
    if (!owner) {
      return res.status(404).json({ error: 'Owner not found' });
    }

    const trialExpiry = new Date();
    trialExpiry.setDate(trialExpiry.getDate() + 2); // 2 days free trial

    await prisma.botOwner.update({
      where: { id: ownerId },
      data: { verified: true, subscriptionActive: true, subscriptionExpiry: trialExpiry }
    });

    // Update onboarding session to connect business number
    await prisma.botSession.upsert({
      where: { phone: owner.mobile },
      update: { role: 'ONBOARDING', state: 'AWAITING_BUSINESS_CONNECT' },
      create: { phone: owner.mobile, role: 'ONBOARDING', state: 'AWAITING_BUSINESS_CONNECT' }
    });

    res.json({ message: `Owner ${owner.name} approved successfully with a 2-day free trial.` });
  } catch (err) {
    console.error('Error approving owner:', err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

/**
 * POST /api/admin/owners/:id/reject
 * Reject/deactivate a turf owner and remove their subscription/verification.
 */
router.post('/owners/:id/reject', async (req, res) => {
  const prisma = req.app.get('prisma');
  const ownerId = parseInt(req.params.id, 10);

  if (isNaN(ownerId)) {
    return res.status(400).json({ error: 'Invalid owner ID' });
  }

  try {
    const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
    if (!owner) {
      return res.status(404).json({ error: 'Owner not found' });
    }

    await prisma.botOwner.update({
      where: { id: ownerId },
      data: { verified: false, subscriptionActive: false, subscriptionExpiry: null }
    });

    // Reset session
    await prisma.botSession.deleteMany({ where: { phone: owner.mobile } });

    res.json({ message: `Owner ${owner.name} has been rejected/deactivated.` });
  } catch (err) {
    console.error('Error rejecting owner:', err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

/**
 * DELETE /api/admin/owners/:id
 * Completely purge owner registration details, bookings, slots, join requests, active sessions,
 * and deactivate their bot responses.
 */
router.delete('/owners/:id', async (req, res) => {
  const prisma = req.app.get('prisma');
  const ownerId = parseInt(req.params.id, 10);

  if (isNaN(ownerId)) {
    return res.status(400).json({ error: 'Invalid owner ID' });
  }

  try {
    const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
    if (!owner) {
      return res.status(404).json({ error: 'Owner not found' });
    }

    // 1. Get slot IDs of this owner
    const slots = await prisma.botTurfSlot.findMany({ where: { ownerId } });
    const slotIds = slots.map(s => s.id);

    // 2. Get booking IDs of those slots
    const bookings = await prisma.botBooking.findMany({ where: { slotId: { in: slotIds } } });
    const bookingIds = bookings.map(b => b.id);

    // 3. Delete all associated join requests
    if (bookingIds.length > 0) {
      await prisma.botJoinRequest.deleteMany({ where: { bookingId: { in: bookingIds } } });
    }

    // 4. Delete all bookings
    if (slotIds.length > 0) {
      await prisma.botBooking.deleteMany({ where: { slotId: { in: slotIds } } });
    }

    // 5. Delete all slots
    await prisma.botTurfSlot.deleteMany({ where: { ownerId } });

    // 6. Delete all sessions for the owner (mobile & businessPhone if any)
    const phones = [owner.mobile, owner.businessPhone].filter(Boolean);
    if (phones.length > 0) {
      await prisma.botSession.deleteMany({ where: { phone: { in: phones } } });
    }

    // 7. Delete the Owner record itself
    await prisma.botOwner.delete({ where: { id: ownerId } });

    res.json({ message: `Owner ${owner.name} (${owner.turfName}) and all related data have been completely deleted.` });
  } catch (err) {
    console.error('Error deleting owner:', err);
    res.status(500).json({ error: 'An internal error occurred' });
  }
});

/**
 * POST /api/admin/telegram/setup-webhook
 * Triggers automatic Telegram webhook registration using server environment variables.
 * Enforces timing-safe requireAdminKey auth (applied at router level).
 */
router.post('/telegram/setup-webhook', async (req, res) => {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const secretToken = process.env.TELEGRAM_WEBHOOK_SECRET;

  if (!token) {
    return res.status(400).json({ error: 'TELEGRAM_BOT_TOKEN is not set in the server environment.' });
  }
  if (!secretToken) {
    return res.status(400).json({ error: 'TELEGRAM_WEBHOOK_SECRET is not set in the server environment.' });
  }

  try {
    // Dynamically detect server protocol and host
    const host = req.get('host');
    const protocol = req.protocol === 'http' && host.includes('localhost') ? 'http' : 'https';
    const webhookUrl = `${protocol}://${host}/webhook/telegram`;

    console.log(`[Telegram Setup] Registering webhook: ${webhookUrl}`);
    const response = await axios.post(`https://api.telegram.org/bot${token}/setWebhook`, {
      url: webhookUrl,
      secret_token: secretToken
    });

    res.json({
      message: 'Telegram webhook registration request sent successfully.',
      telegramResponse: response.data,
      registeredUrl: webhookUrl
    });
  } catch (err) {
    const errorData = err.response?.data || err.message;
    console.error('Error setting Telegram webhook:', errorData);
    res.status(500).json({
      error: 'Failed to configure Telegram webhook with Telegram servers.',
      details: typeof errorData === 'object' ? errorData : { message: errorData }
    });
  }
});

export default router;

