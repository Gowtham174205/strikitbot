import * as whatsappService from '../services/whatsappService.js';
import * as telegramService from '../services/telegramService.js';
import { generateRevenueReport } from '../services/pdfGenerator.js';
import path from 'path';
import fs from 'fs';
import { sanitizeInput } from '../middleware/security.js';
import * as paymentService from '../services/paymentService.js';
import axios from 'axios';

const ONBOARDING_NUMBER = process.env.ONBOARDING_NUMBER || '919000000000';

export async function handleWhatsAppWebhook(from, to, messageText, prisma, mediaId = '', mediaType = '') {
  const text = (messageText || '').trim();
  const phone = from;

  // 0. Developer Commands: check if the sender is an authorized developer/admin
  const devNumbersStr = process.env.DEVELOPER_NUMBERS || '';
  const developerNumbers = devNumbersStr.split(',').map(n => n.trim()).filter(Boolean);

  if (developerNumbers.includes(phone)) {
    if (
      text.startsWith('/approve') ||
      text.startsWith('/reject') ||
      text.startsWith('/deactivate') ||
      text.startsWith('/activate')
    ) {
      await handleDeveloperWhatsAppCommand(phone, text, prisma);
      return;
    }
  }

  // 1. ROUTING: Centralized WhatsApp Bot Routing
  // If the destination is the STRIKIT Bot number, handle everything on this one number.
  if (to === ONBOARDING_NUMBER || to === process.env.WHATSAPP_PHONE_NUMBER_ID) {
    const lowerText = text.toLowerCase().trim();

    // Check if sender is a registered Owner
    const owner = await prisma.botOwner.findUnique({
      where: { mobile: phone }
    });

    if (owner) {
      // If owner is still in onboarding state (has session with role ONBOARDING)
      const session = await prisma.botSession.findUnique({ where: { phone } });
      if (session && session.role === 'ONBOARDING') {
        return handleOnboardingFlow(phone, text, prisma, mediaId, mediaType);
      }

      // Check subscription expiration
      if (owner.subscriptionActive && owner.subscriptionExpiry) {
        const now = new Date();
        if (now > new Date(owner.subscriptionExpiry)) {
          await prisma.botOwner.update({
            where: { id: owner.id },
            data: { subscriptionActive: false }
          });
          owner.subscriptionActive = false;
        }
      }

      // If not verified yet
      if (!owner.verified) {
        return whatsappService.sendText(phone, "⏳ Your turf verification is pending developer approval. We will notify you once approved!");
      }

      // If subscription is expired, block owner commands and show warning with benefits checklist
      if (!owner.subscriptionActive) {
        const subLink = await paymentService.createSubscriptionLink(owner.id);
        return whatsappService.sendText(
          phone,
          `⚠️ *STRIKIT Subscription Expired* ⚠️\n\n` +
          `Dear ${owner.name}, your subscription for *${owner.turfName}* has expired.\n\n` +
          `To restore access to your owner commands, reports, and settings, please renew your ₹699.00 monthly subscription:\n` +
          `🔗 *Payment Link:* ${subLink}\n\n` +
          `*Subscriber Benefits Include:*\n` +
          `• 📊 Real-Time booking dashboard\n` +
          `• 📈 Automated WhatsApp Monthly PDF reports\n` +
          `• 🚫 Slot blocking and management commands\n` +
          `• ⚙️ Pricing and timings customization\n\n` +
          `_Powered by STRIKIT_`
        );
      }

      // Active Owner commands
      return handleOwnerCommands(phone, text, owner, prisma, mediaId, mediaType);
    }

    // Not a registered owner - check if they have onboarding session in progress
    const session = await prisma.botSession.findUnique({ where: { phone } });
    if (session && session.role === 'ONBOARDING') {
      return handleOnboardingFlow(phone, text, prisma, mediaId, mediaType);
    }

    // Check if new owner wants to register/onboard
    if (lowerText === '/onboard' || lowerText === 'onboard' || lowerText === '/register' || lowerText === 'register') {
      await prisma.botSession.deleteMany({ where: { phone } });
      return handleOnboardingFlow(phone, 'Hi', prisma, mediaId, mediaType);
    }

    // Players: check if the captain is responding to a join request (since captain is also on the main number)
    if (await handleCaptainApproval(phone, text, null, prisma)) {
      return;
    }

    // Otherwise handle player flow
    return handleCentralizedPlayerFlow(phone, text, prisma, mediaId, mediaType);
  }

  // Fallback / legacy support for decentralized numbers
  const turfOwner = await prisma.botOwner.findUnique({
    where: { businessPhone: to }
  });

  if (!turfOwner) {
    return whatsappService.sendText(phone, "Hello! This WhatsApp number is not configured on STRIKIT. Please onboard at the STRIKIT number.");
  }

  // Check trial/subscription expiration
  if (turfOwner.subscriptionActive && turfOwner.subscriptionExpiry) {
    const now = new Date();
    if (now > new Date(turfOwner.subscriptionExpiry)) {
      await prisma.botOwner.update({
        where: { id: turfOwner.id },
        data: { subscriptionActive: false }
      });
      turfOwner.subscriptionActive = false;
    }
  }

  if (!turfOwner.verified) {
    if (phone === turfOwner.mobile) {
      return whatsappService.sendText(phone, "⏳ Your turf verification is pending developer approval. We will notify you once approved!");
    } else {
      return whatsappService.sendText(phone, "⚠️ This booking bot is temporarily inactive. Please contact turf management directly.");
    }
  }

  if (!turfOwner.subscriptionActive) {
    if (phone === turfOwner.mobile) {
      const subLink = await paymentService.createSubscriptionLink(turfOwner.id);
      return whatsappService.sendText(
        phone,
        `⚠️ *STRIKIT Subscription Expired* ⚠️\n\n` +
        `Dear ${turfOwner.name}, your subscription or 2-day free trial for *${turfOwner.turfName}* has expired.\n\n` +
        `To keep your booking bot active for players, please pay ₹699.00 to renew your monthly subscription:\n\n` +
        `🔗 *Payment Link:* Click below to pay via Razorpay:\n` +
        `${subLink}\n\n` +
        `_Powered by STRIKIT_`
      );
    }
  }

  if (phone === turfOwner.mobile) {
    return handleOwnerCommands(phone, text, turfOwner, prisma, mediaId, mediaType);
  }

  if (await handleCaptainApproval(phone, text, turfOwner, prisma)) {
    return;
  }

  return handlePlayerFlow(phone, text, turfOwner, prisma);
}

/**
 * =========================================================================
 * ONBOARDING STATE MACHINE
 * =========================================================================
 */
async function handleOnboardingFlow(phone, text, prisma, mediaId = '', mediaType = '') {
  let session = await prisma.botSession.findUnique({
    where: { phone }
  });

  if (!session || session.role !== 'ONBOARDING') {
    // Initialize Onboarding Session
    session = await prisma.botSession.upsert({
      where: { phone },
      update: { role: 'ONBOARDING', state: 'ONBOARDING_START', context: '{}' },
      create: { phone, role: 'ONBOARDING', state: 'ONBOARDING_START', context: '{}' }
    });
  }

  const context = JSON.parse(session.context || '{}');

  switch (session.state) {
    case 'ONBOARDING_START':
      await whatsappService.sendText(phone, "Welcome to STRIKIT Onboarding! Let's get your turf set up. Please enter the Owner Name:");
      await updateSession(phone, 'AWAITING_OWNER_NAME', context, prisma);
      break;

    case 'AWAITING_OWNER_NAME':
      context.ownerName = sanitizeInput(text, 100);
      await whatsappService.sendText(phone, `Thank you, ${context.ownerName}. Now, please enter your Turf Name:`);
      await updateSession(phone, 'AWAITING_TURF_NAME', context, prisma);
      break;

    case 'AWAITING_TURF_NAME':
      context.turfName = sanitizeInput(text, 100);
      await whatsappService.sendText(phone, `Got it: "${text}". Please enter the Location of your turf as a Google Maps link (e.g., https://maps.app.goo.gl/...):`);
      await updateSession(phone, 'AWAITING_LOCATION', context, prisma);
      break;

    case 'AWAITING_LOCATION':
      if (!isGoogleMapsLink(text)) {
        await whatsappService.sendText(phone, `❌ Invalid location format. Please provide a valid Google Maps location link (e.g., https://maps.app.goo.gl/xxxx or maps.google.com):`);
        return;
      }
      context.location = text;
      const coords = await extractCoordinatesFromGoogleMapsLink(text);
      if (coords) {
        context.latitude = coords.latitude;
        context.longitude = coords.longitude;
      }
      await whatsappService.sendText(phone, `Location set. Please upload or provide a link for your Turf Photos (e.g. Google Drive link or upload photos directly):`);
      await updateSession(phone, 'AWAITING_PHOTOS', context, prisma);
      break;

    case 'AWAITING_PHOTOS':
      if (mediaType === 'image' || mediaType === 'document') {
        const mediaUrl = await whatsappService.getMediaUrl(mediaId);
        context.photoUrls = sanitizeInput(mediaUrl, 2000);
        await whatsappService.sendText(phone, `✅ Turf Photo uploaded successfully!\n\nPlease enter your 15-character GST Number (GSTIN):`);
        await updateSession(phone, 'AWAITING_GST', context, prisma);
      } else {
        context.photoUrls = sanitizeInput(text, 2000);
        await whatsappService.sendText(phone, `Photos set. Please enter your 15-character GST Number (GSTIN):`);
        await updateSession(phone, 'AWAITING_GST', context, prisma);
      }
      break;

    case 'AWAITING_GST':
      const cleanGst = text.toUpperCase().replace(/\s+/g, '');
      const gstRegex = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
      if (!gstRegex.test(cleanGst)) {
        await whatsappService.sendText(phone, `❌ Invalid GST format. Please enter a valid 15-character GSTIN (e.g., 22AAAAA0000A1Z5):`);
        return;
      }
      context.gst = cleanGst;
      await whatsappService.sendText(phone, `GST registered. Please enter your Turf Opening Time (Format: HH:MM AM/PM, e.g. 06:00 AM):`);
      await updateSession(phone, 'AWAITING_OPENING_TIME', context, prisma);
      break;

    case 'AWAITING_MSME':
      if (mediaType === 'image' || mediaType === 'document') {
        const mediaUrl = await whatsappService.getMediaUrl(mediaId);
        context.msme = mediaUrl;
        await whatsappService.sendText(phone, `✅ MSME Certificate uploaded successfully!\n\nPlease enter your Turf Opening Time (Format: HH:MM AM/PM, e.g. 06:00 AM):`);
        await updateSession(phone, 'AWAITING_OPENING_TIME', context, prisma);
      } else {
        const cleanMsme = text.toUpperCase().replace(/\s+/g, '');
        const msmeRegex = /^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$/;
        if (!msmeRegex.test(cleanMsme)) {
          await whatsappService.sendText(phone, `❌ Invalid MSME Udyam Registration. Please enter a valid registration number (e.g., UDYAM-TN-01-0123456) OR upload your MSME Certificate file/image here:`);
          return;
        }
        context.msme = cleanMsme;
        await whatsappService.sendText(phone, `MSME registered. Please enter your Turf Opening Time (Format: HH:MM AM/PM, e.g. 06:00 AM):`);
        await updateSession(phone, 'AWAITING_OPENING_TIME', context, prisma);
      }
      break;

    case 'AWAITING_OPENING_TIME':
      context.openingTime = sanitizeInput(text, 20);
      await whatsappService.sendText(phone, `Please enter your Turf Closing Time (Format: HH:MM AM/PM, e.g. 10:00 PM):`);
      await updateSession(phone, 'AWAITING_CLOSING_TIME', context, prisma);
      break;

    case 'AWAITING_CLOSING_TIME':
      context.closingTime = sanitizeInput(text, 20);
      await whatsappService.sendText(phone, `Please enter your Turf Hourly Booking Price (in ₹, e.g. 1000):`);
      await updateSession(phone, 'AWAITING_PRICE', context, prisma);
      break;

    case 'AWAITING_PRICE':
      const priceVal = parseFloat(text);
      context.pricePerHour = isNaN(priceVal) || priceVal <= 0 ? 1000.0 : priceVal;
      
      await whatsappService.sendText(
        phone,
        `Great! Hourly rate is set to *₹${context.pricePerHour.toFixed(2)}*.\n\n` +
        `👉 *Final Registration Detail:* Please enter your UPI ID (VPA) where players' booking payments will be transferred automatically (e.g. owner@upi or name@ybl):`
      );
      await updateSession(phone, 'AWAITING_UPI', context, prisma);
      break;

    case 'AWAITING_UPI':
      const cleanUpiId = text.trim().toLowerCase().replace(/\s+/g, '');
      const upiRegexStr = /^[\w\.\-_]{2,256}@[a-zA-Z]{2,64}$/;
      if (!upiRegexStr.test(cleanUpiId)) {
        await whatsappService.sendText(phone, "❌ Invalid UPI ID format. Please reply with a valid UPI ID (e.g. owner@upi or name@ybl):");
        return;
      }
      context.upiId = cleanUpiId;
      
      // Save owner data to database (verified: false)
      const existingOwner = await prisma.botOwner.findUnique({ where: { mobile: phone } });
      let owner;
      if (existingOwner) {
        owner = await prisma.botOwner.update({
          where: { mobile: phone },
          data: {
            name: context.ownerName,
            turfName: context.turfName,
            location: context.location,
            photoUrls: context.photoUrls,
            gst: context.gst,
            msme: context.msme,
            upiId: context.upiId,
            openingTime: context.openingTime,
            closingTime: context.closingTime,
            pricePerHour: context.pricePerHour,
            latitude: context.latitude ? parseFloat(context.latitude) : null,
            longitude: context.longitude ? parseFloat(context.longitude) : null
          }
        });
      } else {
        owner = await prisma.botOwner.create({
          data: {
            name: context.ownerName,
            mobile: phone,
            turfName: context.turfName,
            location: context.location,
            photoUrls: context.photoUrls,
            gst: context.gst,
            msme: context.msme,
            upiId: context.upiId,
            openingTime: context.openingTime,
            closingTime: context.closingTime,
            pricePerHour: context.pricePerHour,
            latitude: context.latitude ? parseFloat(context.latitude) : null,
            longitude: context.longitude ? parseFloat(context.longitude) : null
          }
        });
      }

      await whatsappService.sendText(
        phone,
        `🎉 *Registration Summary for ${context.turfName}!* 🎉\n\n` +
        `Hello ${context.ownerName}, your registration details have been saved successfully!\n\n` +
        `⏳ *Verification:* Your details have been sent to the developers for review. Once approved, you will receive a link to pay the ₹699 subscription fee to activate your bot and generate your QR Code.\n\n` +
        `We will notify you immediately via WhatsApp once verified. Thank you for partnering with STRIKIT!\n\n` +
        `_Powered by STRIKIT_`
      );

      await updateSession(phone, 'ONBOARDING_AWAITING_VERIFICATION', { ...context, ownerId: owner.id }, prisma);

      // Trigger verification alerts immediately
      try {
        await telegramService.sendVerificationAlert(owner);
        await whatsappService.sendDeveloperVerificationAlert(owner);
      } catch (alertErr) {
        console.error('Error sending developer verification alerts:', alertErr);
      }
      break;

    case 'AWAITING_SUBSCRIPTION':
      const awaitingSubLink = await paymentService.createSubscriptionLink(context.ownerId);
      await whatsappService.sendText(phone, `Your subscription has expired. Please pay ₹699.00 to reactivate: ${awaitingSubLink}`);
      break;

    case 'AWAITING_VERIFICATION':
    case 'ONBOARDING_AWAITING_VERIFICATION':
      await whatsappService.sendText(phone, `⏳ *Awaiting Verification:* Your details are being reviewed by the developers. Once approved, you will receive a payment link to pay the ₹699 subscription fee and activate your bot. Please wait.`);
      break;

    case 'AWAITING_BUSINESS_CONNECT':
      let bNumber = '';
      if (text.startsWith('/connect')) {
        const parts = text.split(' ');
        if (parts.length < 2) {
          await whatsappService.sendText(phone, "Format error. Please send: /connect [WhatsAppBusinessNumber] (e.g. /connect 919876543210)");
          return;
        }
        bNumber = parts[1].replace(/[^0-9]/g, ''); // strip formatting
      } else {
        bNumber = text.replace(/[^0-9]/g, '');
      }
      
      if (bNumber.length >= 10 && bNumber.length <= 15) {
        await prisma.botOwner.update({
          where: { id: context.ownerId },
          data: { businessPhone: bNumber }
        });

        await whatsappService.sendText(
          phone,
          `🌟 *Welcome to STRIKIT!* 🌟\n\n` +
          `Hello ${context.ownerName || 'Owner'}, your registration is complete and your STRIKIT Bot is now active for *${context.turfName}*! 🚀\n\n` +
          `📲 Players can book slots directly by texting your business bot at:\n` +
          `👉 *wa.me/${bNumber}*\n\n` +
          `*Turf Owner Management Commands:*\n` +
          `You can message this bot anytime to manage your turf bookings and view analytics:\n` +
          `• \`/bookings\` - Get real-time booking summary\n` +
          `• \`/revenue\` - Get earnings statistics\n` +
          `• \`/report\` - Generate a premium PDF transaction sheet\n` +
          `• \`/block [Date] [Time]\` - Temporarily block a slot (e.g. \`/block 2026-06-06 06:00 PM\`)\n` +
          `• \`/unblock [Date] [Time]\` - Restore a blocked slot\n` +
          `• \`/edit\` - Update turf details (name, price, timings, location, ownername, photos, gst, msme)\n\n` +
          `We are excited to help you automate bookings and elevate your business! ⚽🔥\n\n` +
          `_Powered by STRIKIT_`
        );

        // Delete onboarding session
        await prisma.botSession.delete({ where: { phone } });
      } else {
        await whatsappService.sendText(phone, "Please connect your WhatsApp Business Number by replying with your number directly (e.g. 919876543210) or typing:\n/connect [WhatsAppNumber]");
      }
      break;

    default:
      await whatsappService.sendText(phone, "You are in onboarding. Please follow the instructions.");
  }
}

/**
 * =========================================================================
 * OWNER COMMANDS FLOW
 * =========================================================================
 */
async function handleOwnerCommands(phone, text, owner, prisma, mediaId = '', mediaType = '') {
  let session = await prisma.botSession.findUnique({ where: { phone } });
  if (!session || session.role !== 'OWNER') {
    session = await prisma.botSession.upsert({
      where: { phone },
      update: { role: 'OWNER', state: 'OWNER_DASHBOARD', context: '{}' },
      create: { phone, role: 'OWNER', state: 'OWNER_DASHBOARD', context: '{}' }
    });
  }

  const context = JSON.parse(session.context || '{}');

  // Support manual commands for backwards compatibility in tests
  if (text.startsWith('/bookings')) {
    await executeBookings(phone, owner, prisma);
    return;
  }
  if (text.startsWith('/revenue')) {
    await executeRevenue(phone, owner, prisma);
    return;
  }
  if (text.startsWith('/report')) {
    await startReportFlow(phone, prisma);
    return;
  }
  if (text.startsWith('/block')) {
    const parts = text.split(' ');
    if (parts.length < 3) {
      await whatsappService.sendText(phone, "Format error. Use: /block [YYYY-MM-DD] [HH:MM] (e.g. /block 2026-06-05 18:00)");
      return;
    }
    const date = parts[1];
    const timeSlot = parts.slice(2).join(' ');

    await prisma.botTurfSlot.upsert({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date, timeSlot } },
      update: { status: 'BLOCKED', blockedByOwner: true },
      create: { ownerId: owner.id, date, timeSlot, status: 'BLOCKED', blockedByOwner: true }
    });

    await whatsappService.sendText(phone, `🚫 Slot on ${date} @ ${timeSlot} has been blocked.`);
    await telegramService.sendAlert(`Owner blocked slot: ${owner.turfName} - ${date} @ ${timeSlot}`);
    return;
  }
  if (text.startsWith('/unblock')) {
    const parts = text.split(' ');
    if (parts.length < 3) {
      await whatsappService.sendText(phone, "Format error. Use: /unblock [YYYY-MM-DD] [HH:MM] (e.g. /unblock 2026-06-05 18:00)");
      return;
    }
    const date = parts[1];
    const timeSlot = parts.slice(2).join(' ');

    const existing = await prisma.botTurfSlot.findUnique({
      where: { ownerId_date_timeSlot: { ownerId: owner.id, date, timeSlot } }
    });

    if (existing && existing.status === 'BLOCKED') {
      await prisma.botTurfSlot.update({
        where: { id: existing.id },
        data: { status: 'AVAILABLE', blockedByOwner: false }
      });
      await whatsappService.sendText(phone, `✅ Slot on ${date} @ ${timeSlot} has been unblocked.`);
    } else {
      await whatsappService.sendText(phone, `Slot on ${date} @ ${timeSlot} is not blocked.`);
    }
    return;
  }
  if (text.startsWith('/edit')) {
    const parts = text.split(' ');
    if (parts.length < 3) {
      await whatsappService.sendText(
        phone,
        `⚙️ *STRIKIT Edit Commands Menu*\n\n` +
        `To update your turf details, text one of the following commands:\n` +
        `• \`/edit name [New Turf Name]\` (e.g. \`/edit name Red Devils Turf\`)\n` +
        `• \`/edit price [New Price]\` (e.g. \`/edit price 1200\`)\n` +
        `• \`/edit open [Opening Time]\` (e.g. \`/edit open 07:00 AM\`)\n` +
        `• \`/edit close [Closing Time]\` (e.g. \`/edit close 11:00 PM\`)\n` +
        `• \`/edit location [New Location]\` (e.g. \`/edit location High Road, Chennai\`)\n` +
        `• \`/edit ownername [New Owner Name]\` (e.g. \`/edit ownername Gowtham P\`)\n` +
        `• \`/edit photos [New Photos Link]\` (e.g. \`/edit photos http://photos.link/new\`)\n` +
        `• \`/edit gst [New GST or SKIP]\` (e.g. \`/edit gst 33AAAAA1111A1Z1\`)\n` +
        `• \`/edit msme [New MSME or SKIP]\` (e.g. \`/edit msme UDYAM-TN-01-0123456\`)`
      );
      return;
    }

    const field = parts[1].toLowerCase();
    const value = parts.slice(2).join(' ');

    try {
      if (field === 'name') {
        await prisma.botOwner.update({ where: { id: owner.id }, data: { turfName: value } });
        await whatsappService.sendText(phone, `✅ Turf name successfully updated to: *${value}*`);
      } else if (field === 'price') {
        const price = parseFloat(value);
        if (isNaN(price) || price <= 0) {
          await whatsappService.sendText(phone, `❌ Invalid price amount. Please enter a valid number.`);
          return;
        }
        await prisma.botOwner.update({ where: { id: owner.id }, data: { pricePerHour: price } });
        await whatsappService.sendText(phone, `✅ Turf hourly price successfully updated to: *₹${price}*`);
      } else if (field === 'open') {
        await prisma.botOwner.update({ where: { id: owner.id }, data: { openingTime: value } });
        await whatsappService.sendText(phone, `✅ Turf opening time successfully updated to: *${value}*`);
      } else if (field === 'close') {
        await prisma.botOwner.update({ where: { id: owner.id }, data: { closingTime: value } });
        await whatsappService.sendText(phone, `✅ Turf closing time successfully updated to: *${value}*`);
      } else if (field === 'location') {
        if (!isGoogleMapsLink(value)) {
          await whatsappService.sendText(phone, `❌ Invalid location format. Please provide a valid Google Maps location link (e.g., https://maps.app.goo.gl/...):`);
          return;
        }
        await prisma.botOwner.update({ where: { id: owner.id }, data: { location: value } });
        await whatsappService.sendText(phone, `✅ Turf location successfully updated to: *${value}*`);
      } else if (field === 'ownername') {
        await prisma.botOwner.update({ where: { id: owner.id }, data: { name: value } });
        await whatsappService.sendText(phone, `✅ Owner name successfully updated to: *${value}*`);
      } else if (field === 'photos') {
        await prisma.botOwner.update({ where: { id: owner.id }, data: { photoUrls: value } });
        await whatsappService.sendText(phone, `✅ Turf photos link successfully updated to: *${value}*`);
      } else if (field === 'gst') {
        const cleanGst = value.toUpperCase().replace(/\s+/g, '');
        const gstRegex = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
        if (!gstRegex.test(cleanGst)) {
          await whatsappService.sendText(phone, `❌ Invalid GST format. Please enter a valid 15-character GSTIN (e.g., 22AAAAA0000A1Z5):`);
          return;
        }
        await prisma.botOwner.update({ where: { id: owner.id }, data: { gst: cleanGst } });
        await whatsappService.sendText(phone, `✅ GST number successfully updated to: *${cleanGst}*`);
      } else if (field === 'msme') {
        const cleanMsme = value.toUpperCase().replace(/\s+/g, '');
        const msmeRegex = /^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$/;
        if (!msmeRegex.test(cleanMsme)) {
          await whatsappService.sendText(phone, `❌ Invalid MSME Udyam Registration format. Format must be UDYAM-XX-00-0000000 (e.g., UDYAM-TN-01-0123456):`);
          return;
        }
        await prisma.botOwner.update({ where: { id: owner.id }, data: { msme: cleanMsme } });
        await whatsappService.sendText(phone, `✅ MSME certificate successfully updated to: *${cleanMsme}*`);
      } else {
        await whatsappService.sendText(phone, `❌ Unknown edit field. Send \`/edit\` to see options.`);
      }
    } catch (err) {
      console.error(err);
      await whatsappService.sendText(phone, `❌ Failed to update turf details. Check syntax and try again.`);
    }
    return;
  }

  // Interactive Flow Logic based on state
  switch (session.state) {
    case 'OWNER_DASHBOARD':
      await sendOwnerDashboard(phone, prisma);
      await prisma.botSession.update({
        where: { phone },
        data: { state: 'AWAITING_OWNER_DASHBOARD_CHOICE' }
      });
      break;

    case 'AWAITING_OWNER_DASHBOARD_CHOICE':
      if (text === 'dashboard_bookings') {
        await executeBookings(phone, owner, prisma);
        await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      } else if (text === 'dashboard_revenue') {
        await executeRevenue(phone, owner, prisma);
        await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      } else if (text === 'dashboard_report') {
        await startReportFlow(phone, prisma);
      } else if (text === 'dashboard_edit_settings') {
        await sendSettingsEditMenu(phone, prisma);
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_FIELD_CHOICE' } });
      } else if (text === 'dashboard_block_slot') {
        await sendBlockDateSelection(phone, prisma);
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_BLOCK_DATE_CHOICE' } });
      } else {
        await sendOwnerDashboard(phone, prisma);
      }
      break;

    case 'AWAITING_REPORT_RANGE_CHOICE':
      let range = '';
      if (text === '1' || text === 'report_current_month' || text.toLowerCase().includes('current')) {
        range = 'CURRENT_MONTH';
      } else if (text === '2' || text === 'report_prev_month' || text.toLowerCase().includes('prev') || text.toLowerCase().includes('previous')) {
        range = 'PREVIOUS_MONTH';
      } else if (text === '3' || text === 'report_all_time' || text.toLowerCase().includes('all')) {
        range = 'ALL_TIME';
      } else {
        await whatsappService.sendText(phone, "❌ Invalid selection. Please reply: 1 (Current Month), 2 (Previous Month), or 3 (All-Time):");
        return;
      }

      await executeReportWithRange(phone, owner, range, prisma);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_FIELD_CHOICE':
      if (text === 'edit_name') {
        await whatsappService.sendText(phone, "Please reply with the new Turf Name:");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_TURF_NAME' } });
      } else if (text === 'edit_price') {
        await whatsappService.sendText(phone, "Please reply with the new price per hour (in ₹):");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_PRICE' } });
      } else if (text === 'edit_location') {
        await whatsappService.sendText(phone, "Please reply with the new Location Link (Google Maps link):");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_LOCATION' } });
      } else if (text === 'edit_ownername') {
        await whatsappService.sendText(phone, "Please reply with the new Owner Name:");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_OWNER_NAME' } });
      } else if (text === 'edit_photos') {
        await whatsappService.sendText(phone, "Please reply with the new Photos Link or upload a photo directly:");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_PHOTOS' } });
      } else if (text === 'edit_gst') {
        await whatsappService.sendText(phone, "Please reply with the new GST Number:");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_GST' } });
      } else if (text === 'edit_msme') {
        await whatsappService.sendText(phone, "Please reply with the new MSME Certificate Number or upload a file directly:");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_MSME' } });
      } else if (text === 'edit_upi') {
        await whatsappService.sendText(phone, "Please reply with your new UPI ID (VPA) for receiving payments (e.g. owner@upi):");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_UPI' } });
      } else if (text === 'edit_opening') {
        await whatsappService.sendText(phone, "Please reply with the new Opening Time (e.g. 06:00 AM):");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_OPENING' } });
      } else if (text === 'edit_closing') {
        await whatsappService.sendText(phone, "Please reply with the new Closing Time (e.g. 10:00 PM):");
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_EDIT_CLOSING' } });
      } else {
        await sendSettingsEditMenu(phone, prisma);
      }
      break;

    case 'AWAITING_EDIT_TURF_NAME':
      await prisma.botOwner.update({ where: { id: owner.id }, data: { turfName: text } });
      await whatsappService.sendText(phone, `✅ Turf name successfully updated to: *${text}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_PRICE':
      const price = parseFloat(text);
      if (isNaN(price) || price <= 0) {
        await whatsappService.sendText(phone, "❌ Invalid price. Please reply with a valid number:");
        return;
      }
      await prisma.botOwner.update({ where: { id: owner.id }, data: { pricePerHour: price } });
      await whatsappService.sendText(phone, `✅ Turf hourly price successfully updated to: *₹${price}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_LOCATION':
      if (!isGoogleMapsLink(text)) {
        await whatsappService.sendText(phone, "❌ Invalid location format. Please provide a valid Google Maps location link (e.g., https://maps.app.goo.gl/...):");
        return;
      }
      await prisma.botOwner.update({ where: { id: owner.id }, data: { location: text } });
      await whatsappService.sendText(phone, `✅ Turf location successfully updated to: *${text}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_OWNER_NAME':
      await prisma.botOwner.update({ where: { id: owner.id }, data: { name: text } });
      await whatsappService.sendText(phone, `✅ Owner name successfully updated to: *${text}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_PHOTOS':
      let photoLink = text;
      if (mediaType === 'image' || mediaType === 'document') {
        photoLink = await whatsappService.getMediaUrl(mediaId);
      }
      await prisma.botOwner.update({ where: { id: owner.id }, data: { photoUrls: photoLink } });
      await whatsappService.sendText(phone, `✅ Turf photos link successfully updated to: *${photoLink}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_GST':
      const cleanGst = text.toUpperCase().replace(/\s+/g, '');
      const gstRegex = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
      if (!gstRegex.test(cleanGst)) {
        await whatsappService.sendText(phone, "❌ Invalid GST format. Please enter a valid 15-character GSTIN (e.g., 22AAAAA0000A1Z5):");
        return;
      }
      await prisma.botOwner.update({ where: { id: owner.id }, data: { gst: cleanGst } });
      await whatsappService.sendText(phone, `✅ GST number successfully updated to: *${cleanGst}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_MSME':
      let msmeVal = text;
      if (mediaType === 'image' || mediaType === 'document') {
        msmeVal = await whatsappService.getMediaUrl(mediaId);
      } else {
        const cleanMsme = text.toUpperCase().replace(/\s+/g, '');
        const msmeRegex = /^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$/;
        if (!msmeRegex.test(cleanMsme)) {
          await whatsappService.sendText(phone, "❌ Invalid MSME Udyam Registration format. Format must be UDYAM-XX-00-0000000 (e.g., UDYAM-TN-01-0123456) OR upload your MSME Certificate file directly:");
          return;
        }
        msmeVal = cleanMsme;
      }
      await prisma.botOwner.update({ where: { id: owner.id }, data: { msme: msmeVal } });
      await whatsappService.sendText(phone, `✅ MSME certificate successfully updated to: *${msmeVal}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_UPI':
      const cleanUpiStr = text.trim().toLowerCase().replace(/\s+/g, '');
      const upiRegexObj = /^[\w\.\-_]{2,256}@[a-zA-Z]{2,64}$/;
      if (!upiRegexObj.test(cleanUpiStr)) {
        await whatsappService.sendText(phone, "❌ Invalid UPI ID format. Please reply with a valid UPI ID (e.g. owner@upi or name@ybl):");
        return;
      }
      await prisma.botOwner.update({
        where: { id: owner.id },
        data: {
          upiId: cleanUpiStr,
          razorpayContactId: null,
          razorpayFundAccountId: null
        }
      });
      await whatsappService.sendText(phone, `✅ UPI ID successfully updated to: *${cleanUpiStr}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_OPENING':
      await prisma.botOwner.update({ where: { id: owner.id }, data: { openingTime: text } });
      await whatsappService.sendText(phone, `✅ Turf opening time successfully updated to: *${text}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_EDIT_CLOSING':
      await prisma.botOwner.update({ where: { id: owner.id }, data: { closingTime: text } });
      await whatsappService.sendText(phone, `✅ Turf closing time successfully updated to: *${text}*\n\n_Powered by STRIKIT_`);
      await prisma.botSession.update({ where: { phone }, data: { state: 'OWNER_DASHBOARD' } });
      break;

    case 'AWAITING_BLOCK_DATE_CHOICE':
      let blockDate = '';
      if (text.startsWith('block_date_')) {
        blockDate = text.replace('block_date_', '');
      } else if (text.trim() === '1') {
        blockDate = new Date().toISOString().split('T')[0];
      } else if (text.trim() === '2') {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        blockDate = tomorrow.toISOString().split('T')[0];
      } else if (text.trim() === '3') {
        const dayAfter = new Date();
        dayAfter.setDate(dayAfter.getDate() + 2);
        blockDate = dayAfter.toISOString().split('T')[0];
      } else {
        blockDate = text.trim();
      }

      if (!/^\d{4}-\d{2}-\d{2}$/.test(blockDate)) {
        await whatsappService.sendText(phone, "Invalid date format. Please reply with YYYY-MM-DD or select a date:");
        return;
      }

      context.selectedBlockDate = blockDate;
      await sendBlockSlotToggleList(phone, owner.id, blockDate, prisma);
      await prisma.botSession.update({
        where: { phone },
        data: { state: 'AWAITING_BLOCK_SLOT_CHOICE', context: JSON.stringify(context) }
      });
      break;

    case 'AWAITING_BLOCK_SLOT_CHOICE':
      if (text.startsWith('toggle_block_')) {
        const rowPart = text.replace('toggle_block_', '');
        const date = rowPart.substring(0, 10);
        const timeSlot = rowPart.substring(11);

        const slot = await prisma.botTurfSlot.findUnique({
          where: { ownerId_date_timeSlot: { ownerId: owner.id, date, timeSlot } }
        });

        if (!slot) {
          await whatsappService.sendText(phone, `Slot ${timeSlot} on ${date} not found.`);
          return;
        }

        if (slot.status === 'BOOKED') {
          await whatsappService.sendText(phone, `⚠️ Slot ${timeSlot} is already booked by a team and cannot be blocked.`);
          return;
        }

        const newStatus = slot.status === 'BLOCKED' ? 'AVAILABLE' : 'BLOCKED';
        const blockedByOwner = newStatus === 'BLOCKED';

        await prisma.botTurfSlot.update({
          where: { id: slot.id },
          data: { status: newStatus, blockedByOwner }
        });

        if (newStatus === 'BLOCKED') {
          await whatsappService.sendText(phone, `🚫 Slot on ${date} @ ${timeSlot} has been blocked.`);
          await telegramService.sendAlert(`Owner blocked slot: ${owner.turfName} - ${date} @ ${timeSlot}`);
        } else {
          await whatsappService.sendText(phone, `✅ Slot on ${date} @ ${timeSlot} has been unblocked.`);
        }

        // Re-send the updated list so the owner can easily toggle multiple slots
        await sendBlockSlotToggleList(phone, owner.id, date, prisma);
      } else {
        await prisma.botSession.update({ where: { phone }, data: { state: 'AWAITING_OWNER_DASHBOARD_CHOICE' } });
        await sendOwnerDashboard(phone, prisma);
      }
      break;

    default:
      await sendOwnerDashboard(phone, prisma);
      await prisma.botSession.update({
        where: { phone },
        data: { state: 'AWAITING_OWNER_DASHBOARD_CHOICE' }
      });
  }
}

/**
 * =========================================================================
 * TEAM CAPTAIN JOIN APPROVAL ACTION
 * =========================================================================
 */
async function handleCaptainApproval(phone, text, owner, prisma) {
  const upperText = text.toUpperCase();

  // 1. Handle Accept Button Click (id: captain_accept_123)
  if (text.startsWith('captain_accept_')) {
    const joinReqId = parseInt(text.replace('captain_accept_', ''), 10);
    const pendingRequest = await prisma.botJoinRequest.findUnique({
      where: { id: joinReqId },
      include: { booking: { include: { slot: true } } }
    });

    if (!pendingRequest || pendingRequest.status !== 'PENDING') {
      await whatsappService.sendText(phone, "This join request is no longer pending or is invalid.");
      return true;
    }

    // Update Captain's session to await joining fee
    const context = { joinRequestId: joinReqId };
    await prisma.botSession.upsert({
      where: { phone },
      update: { role: 'CUSTOMER', state: 'AWAITING_JOIN_AMOUNT', context: JSON.stringify(context) },
      create: { phone, role: 'CUSTOMER', state: 'AWAITING_JOIN_AMOUNT', context: JSON.stringify(context) }
    });

    await whatsappService.sendText(phone, "Please reply with the joining amount (in ₹) that this player should pay you directly (e.g. 150):");
    return true;
  }

  // 2. Handle Reject Button Click (id: captain_reject_123)
  if (text.startsWith('captain_reject_')) {
    const joinReqId = parseInt(text.replace('captain_reject_', ''), 10);
    const pendingRequest = await prisma.botJoinRequest.findUnique({
      where: { id: joinReqId },
      include: { booking: { include: { slot: true } } }
    });

    if (!pendingRequest || pendingRequest.status !== 'PENDING') {
      await whatsappService.sendText(phone, "This join request is no longer pending or is invalid.");
      return true;
    }

    await prisma.botJoinRequest.update({
      where: { id: joinReqId },
      data: { status: 'REJECTED' }
    });

    await whatsappService.sendText(
      phone,
      `❌ *Request Rejected* ❌\n\n` +
      `You have declined the join request from *${pendingRequest.playerName}*.\n\n` +
      `_Powered by STRIKIT_`
    );

    // Notify Single Player
    await whatsappService.sendText(
      pendingRequest.playerPhone,
      `❌ *Join Request Status* ❌\n\n` +
      `Hello ${pendingRequest.playerName}, we regret to inform you that your request to join team *${pendingRequest.booking.teamName}* on *${pendingRequest.booking.slot.date}* was declined by the team captain.\n\n` +
      `Feel free to search for other slots to join! ⚽\n\n` +
      `_Powered by STRIKIT_`
    );
    return true;
  }

  // 3. Handle Captain Typing Joining Amount (in session state AWAITING_JOIN_AMOUNT)
  const session = await prisma.botSession.findUnique({ where: { phone } });
  if (session && session.state === 'AWAITING_JOIN_AMOUNT') {
    const context = JSON.parse(session.context || '{}');
    const amount = parseFloat(text.trim());
    if (isNaN(amount) || amount <= 0) {
      await whatsappService.sendText(phone, "Please enter a valid numeric amount (e.g. 150):");
      return true;
    }

    const pendingRequest = await prisma.botJoinRequest.findUnique({
      where: { id: context.joinRequestId },
      include: { booking: { include: { slot: { include: { owner: true } } } } }
    });

    if (!pendingRequest || pendingRequest.status !== 'PENDING') {
      await whatsappService.sendText(phone, "This join request is no longer pending or is invalid.");
      await prisma.botSession.delete({ where: { phone } });
      return true;
    }

    await prisma.botJoinRequest.update({
      where: { id: pendingRequest.id },
      data: { status: 'ACCEPTED', joiningAmount: amount }
    });

    await whatsappService.sendText(
      phone,
      `✅ *Player Accepted!* ✅\n\n` +
      `You have successfully accepted *${pendingRequest.playerName}* to join your slot.\n` +
      `We have notified them to pay you *₹${amount}.00* directly. Have a great session! ⚽\n\n` +
      `_Powered by STRIKIT_`
    );

    const turfOwner = owner || pendingRequest.booking.slot.owner;

    // Notify Single Player
    await whatsappService.sendText(
      pendingRequest.playerPhone,
      `🎉 *Join Request Accepted for ${turfOwner.turfName}!* 🎉\n\n` +
      `Hello ${pendingRequest.playerName}, captain *${pendingRequest.booking.captainName}* has accepted your request to play with them!\n\n` +
      `*Details:*\n` +
      `• Turf: *${turfOwner.turfName}*\n` +
      `• Date: ${pendingRequest.booking.slot.date}\n` +
      `• Time Slot: ${pendingRequest.booking.slot.timeSlot}\n` +
      `• Captain Contact: ${pendingRequest.booking.captainPhone}\n` +
      `• *Amount to Pay:* *₹${amount}.00*\n\n` +
      `Please pay the amount of ₹${amount}.00 directly to the captain (via Cash/UPI/etc.) when you join them at the turf. Have a great game! ⚽🔥\n\n` +
      `_Powered by STRIKIT_`
    );

    // Trigger Telegram log update
    await telegramService.sendAlert(
      `Player Joined: ${pendingRequest.playerName} joined ${pendingRequest.booking.captainName}'s team at ${turfOwner.turfName}.`
    );

    await prisma.botSession.delete({ where: { phone } });
    return true;
  }

  // 4. Backward Compatibility for Legacy Text Commands "ACCEPT [Amount]" or "REJECT"
  if (upperText.startsWith('ACCEPT') || upperText === 'REJECT') {
    const bookings = await prisma.botBooking.findMany({
      where: { captainPhone: phone, slot: owner ? { ownerId: owner.id } : undefined },
      orderBy: { createdAt: 'desc' }
    });

    if (bookings.length === 0) return false;

    const bookingIds = bookings.map(b => b.id);
    const pendingRequest = await prisma.botJoinRequest.findFirst({
      where: { bookingId: { in: bookingIds }, status: 'PENDING' },
      include: { booking: { include: { slot: { include: { owner: true } } } } },
      orderBy: { createdAt: 'desc' }
    });

    if (!pendingRequest) return false;

    const turfOwner = owner || pendingRequest.booking.slot.owner;

    if (upperText.startsWith('ACCEPT')) {
      const parts = text.split(' ');
      const amount = parts.length > 1 ? parseFloat(parts[1]) : 0;
      if (isNaN(amount) || amount <= 0) {
        await whatsappService.sendText(phone, "Please specify a valid joining amount. Format: ACCEPT [Amount] (e.g. ACCEPT 150)");
        return true;
      }

      await prisma.botJoinRequest.update({
        where: { id: pendingRequest.id },
        data: { status: 'ACCEPTED', joiningAmount: amount }
      });

      await whatsappService.sendText(
        phone,
        `✅ *Player Accepted!* ✅\n\n` +
        `You have successfully accepted *${pendingRequest.playerName}* to join your slot.\n` +
        `We have notified them to pay you *₹${amount}.00* directly. Have a great session! ⚽\n\n` +
        `_Powered by STRIKIT_`
      );

      await whatsappService.sendText(
        pendingRequest.playerPhone,
        `🎉 *Join Request Accepted for ${turfOwner.turfName}!* 🎉\n\n` +
        `Hello ${pendingRequest.playerName}, captain *${pendingRequest.booking.captainName}* has accepted your request to play with them!\n\n` +
        `*Details:*\n` +
        `• Turf: *${turfOwner.turfName}*\n` +
        `• Date: ${pendingRequest.booking.slot.date}\n` +
        `• Time Slot: ${pendingRequest.booking.slot.timeSlot}\n` +
        `• Captain Contact: ${pendingRequest.booking.captainPhone}\n` +
        `• *Amount to Pay:* *₹${amount}.00*\n\n` +
        `Please pay the amount of ₹${amount}.00 directly to the captain (via Cash/UPI/etc.) when you join them at the turf. Have a great game! ⚽🔥\n\n` +
        `_Powered by STRIKIT_`
      );

      await telegramService.sendAlert(
        `Player Joined: ${pendingRequest.playerName} joined ${pendingRequest.booking.captainName}'s team at ${turfOwner.turfName}.`
      );
    } else {
      await prisma.botJoinRequest.update({
        where: { id: pendingRequest.id },
        data: { status: 'REJECTED' }
      });

      await whatsappService.sendText(
        phone,
        `❌ *Request Rejected* ❌\n\n` +
        `You have declined the join request from *${pendingRequest.playerName}*.\n\n` +
        `_Powered by STRIKIT_`
      );

      await whatsappService.sendText(
        pendingRequest.playerPhone,
        `❌ *Join Request Status* ❌\n\n` +
        `Hello ${pendingRequest.playerName}, we regret to inform you that your request to join team *${pendingRequest.booking.teamName}* on *${pendingRequest.booking.slot.date}* was declined by the team captain.\n\n` +
        `Feel free to search for other slots to join! ⚽\n\n` +
        `_Powered by STRIKIT_`
      );
    }
    return true;
  }

  return false;
}

/**
 * =========================================================================
 * PLAYER BOOKING FLOW STATE MACHINE
 * =========================================================================
 */
async function handlePlayerFlow(phone, text, owner, prisma) {
  const lowerText = text.toLowerCase().trim();
  let session;

  if (lowerText === 'hi' || lowerText === 'hello' || lowerText === 'menu') {
    session = await prisma.botSession.upsert({
      where: { phone },
      update: { role: 'CUSTOMER', state: 'PLAYER_START', context: '{}' },
      create: { phone, role: 'CUSTOMER', state: 'PLAYER_START', context: '{}' }
    });
  } else {
    session = await prisma.botSession.findUnique({
      where: { phone }
    });

    if (!session || session.role !== 'CUSTOMER') {
      session = await prisma.botSession.upsert({
        where: { phone },
        update: { role: 'CUSTOMER', state: 'PLAYER_START', context: '{}' },
        create: { phone, role: 'CUSTOMER', state: 'PLAYER_START', context: '{}' }
      });
    }
  }

  const context = JSON.parse(session.context || '{}');
  context.turfId = owner.id;

  switch (session.state) {
    case 'PLAYER_START':
      // 1. Show Turf Name, Image, and Location
      const photoUrl = owner.photoUrls;
      const caption = `🏟️ *${owner.turfName}*\n📍 *Location:* ${owner.location}\n\n_Powered by STRIKIT_`;
      
      try {
        if (photoUrl && (photoUrl.startsWith('http://') || photoUrl.startsWith('https://'))) {
          await whatsappService.sendImage(phone, photoUrl, caption);
        } else {
          await whatsappService.sendText(phone, caption);
        }
      } catch (err) {
        console.error('Error sending turf info image:', err.message);
        await whatsappService.sendText(phone, caption);
      }

      // 2. Show the options buttons
      await whatsappService.sendButtons(
        phone,
        `👋 *Welcome!* ⚽\n\n` +
        `We are delighted to have you here! Book your turf slots or join existing games instantly.\n\n` +
        `Please select an option below to get started:`,
        [
          { id: 'opt_team', title: '1. I Have Team' },
          { id: 'opt_single', title: '2. Single Player' }
        ]
      );
      await updateSession(phone, 'AWAITING_OPTION_CHOICE', context, prisma);
      break;

    case 'AWAITING_OPTION_CHOICE':
      if (text.includes('1') || text.toLowerCase().includes('team') || text === 'opt_team') {
        context.bookingType = 'TEAM';
        await sendDateSelection(phone, prisma);
        await updateSession(phone, 'AWAITING_DATE_SELECTION', context, prisma);
      } else if (text.includes('2') || text.toLowerCase().includes('single') || text === 'opt_single') {
        context.bookingType = 'SINGLE';
        await sendDateSelection(phone, prisma);
        await updateSession(phone, 'AWAITING_DATE_SELECTION', context, prisma);
      } else {
        await whatsappService.sendText(phone, "Please select an option:\n1. I Have Team\n2. Single Player");
      }
      break;

    case 'AWAITING_DATE_SELECTION':
      const dateOption = text.trim();
      let selectedDate = '';
      const today = new Date();

      if (dateOption === '1') {
        selectedDate = today.toISOString().split('T')[0];
      } else if (dateOption === '2') {
        const tomorrow = new Date(today);
        tomorrow.setDate(today.getDate() + 1);
        selectedDate = tomorrow.toISOString().split('T')[0];
      } else if (dateOption === '3') {
        const dayAfter = new Date(today);
        dayAfter.setDate(today.getDate() + 2);
        selectedDate = dayAfter.toISOString().split('T')[0];
      } else if (dateOption.startsWith('date_')) {
        selectedDate = dateOption.replace('date_', '');
      } else {
        if (/^\d{4}-\d{2}-\d{2}$/.test(dateOption)) {
          selectedDate = dateOption;
        } else {
          await whatsappService.sendText(phone, "Invalid selection. Please choose a date using the buttons or type a date as YYYY-MM-DD.");
          return;
        }
      }

      context.selectedDate = selectedDate;
      await ensureSlotsGenerated(owner.id, selectedDate, prisma);

      await whatsappService.sendButtons(
        phone,
        `🌅 *Choose a Time Period* 🌅\n\n` +
        `Please select a period for *${selectedDate}*:`,
        [
          { id: 'period_morning', title: '🌅 Morning Slots' },
          { id: 'period_evening', title: '🌙 Evening/Night' }
        ]
      );
      await updateSession(phone, 'AWAITING_SLOT_PERIOD_CHOICE', context, prisma);
      break;

    case 'AWAITING_SLOT_PERIOD_CHOICE':
      const periodChoice = text.toLowerCase().trim();
      if (periodChoice === 'period_morning' || periodChoice.includes('morning')) {
        context.selectedPeriod = 'MORNING';
      } else if (periodChoice === 'period_evening' || periodChoice.includes('evening') || periodChoice.includes('night')) {
        context.selectedPeriod = 'EVENING';
      } else {
        await whatsappService.sendButtons(
          phone,
          `🌅 *Choose a Time Period* 🌅\n\n` +
          `Please select a period for *${context.selectedDate}*:`,
          [
            { id: 'period_morning', title: '🌅 Morning Slots' },
            { id: 'period_evening', title: '🌙 Evening/Night' }
          ]
        );
        return;
      }

      if (context.bookingType === 'TEAM') {
        const savedSlots = await prisma.botTurfSlot.findMany({
          where: { ownerId: owner.id, date: context.selectedDate, status: 'AVAILABLE' }
        });
        savedSlots.sort((a, b) => parseTimeTo24h(a.timeSlot) - parseTimeTo24h(b.timeSlot));

        const filteredSlots = savedSlots.filter(s => {
          const hour = parseTimeTo24h(s.timeSlot);
          return context.selectedPeriod === 'MORNING' ? hour < 14 : hour >= 14;
        });

        if (filteredSlots.length === 0) {
          await whatsappService.sendText(phone, `No available slots in the ${context.selectedPeriod.toLowerCase()} period for ${context.selectedDate}.`);
          await whatsappService.sendButtons(
            phone,
            `🌅 *Choose a Time Period* 🌅\n\n` +
            `Please select a period for *${context.selectedDate}*:`,
            [
              { id: 'period_morning', title: '🌅 Morning Slots' },
              { id: 'period_evening', title: '🌙 Evening/Night' }
            ]
          );
          return;
        }

        const rows = filteredSlots.map(s => ({
          id: s.timeSlot,
          title: s.timeSlot,
          description: `🟢 Available - ₹${owner.pricePerHour || 1000}/hr`
        }));

        const sections = [{
          title: `Available Slots (${context.selectedPeriod})`,
          rows
        }];

        await whatsappService.sendList(
          phone,
          `⚽ *Select an Available Slot* ⚽\n\n` +
          `Please select your preferred slot for *${context.selectedDate}* (${context.selectedPeriod.toLowerCase()}):`,
          "Select Time Slot",
          sections
        );
        await updateSession(phone, 'AWAITING_TEAM_SLOT_SELECTION', context, prisma);
      } else {
        // SINGLE booking type
        const bookedSlots = await prisma.botTurfSlot.findMany({
          where: { ownerId: owner.id, date: context.selectedDate, status: 'BOOKED' },
          include: { bookings: true }
        });
        bookedSlots.sort((a, b) => parseTimeTo24h(a.timeSlot) - parseTimeTo24h(b.timeSlot));

        const filteredSlots = bookedSlots.filter(s => {
          const hour = parseTimeTo24h(s.timeSlot);
          return context.selectedPeriod === 'MORNING' ? hour < 14 : hour >= 14;
        });

        if (filteredSlots.length === 0) {
          await whatsappService.sendText(phone, `No booked slots in the ${context.selectedPeriod.toLowerCase()} period to join for ${context.selectedDate}.`);
          await whatsappService.sendButtons(
            phone,
            `🌅 *Choose a Time Period* 🌅\n\n` +
            `Please select a period for *${context.selectedDate}*:`,
            [
              { id: 'period_morning', title: '🌅 Morning Slots' },
              { id: 'period_evening', title: '🌙 Evening/Night' }
            ]
          );
          return;
        }

        const rows = filteredSlots.map(s => {
          const booking = s.bookings[0];
          return {
            id: s.timeSlot,
            title: s.timeSlot,
            description: `Team: ${booking ? booking.teamName : 'Unknown'}`
          };
        });

        const sections = [{
          title: `Booked Slots (${context.selectedPeriod})`,
          rows
        }];

        await whatsappService.sendList(
          phone,
          `⚽ *Select a Slot to Join* ⚽\n\n` +
          `Select the booked slot you want to request to join on *${context.selectedDate}* (${context.selectedPeriod.toLowerCase()}):`,
          "Select Game Slot",
          sections
        );
        await updateSession(phone, 'AWAITING_SINGLE_SLOT_SELECTION', context, prisma);
      }
      break;

    case 'AWAITING_TEAM_SLOT_SELECTION':
      const timeSlot = text.trim();
      const slot = await prisma.botTurfSlot.findUnique({
        where: { ownerId_date_timeSlot: { ownerId: owner.id, date: context.selectedDate, timeSlot } }
      });

      if (slot && slot.status !== 'AVAILABLE') {
        await whatsappService.sendText(phone, `Sorry, ${timeSlot} is already ${slot.status.toLowerCase()}. Please select another slot:`);
        return;
      }

      context.selectedSlot = timeSlot;
      await whatsappService.sendText(phone, "Please enter your Name and Team Name (Format: Name - TeamName, e.g. John - HawksFC):");
      await updateSession(phone, 'AWAITING_TEAM_DETAILS', context, prisma);
      break;

    case 'AWAITING_TEAM_DETAILS':
      const details = text.split('-');
      if (details.length < 2) {
        await whatsappService.sendText(phone, "Format incorrect. Please enter in this format: Name - TeamName");
        return;
      }
      context.captainName = details[0].trim();
      context.teamName = details[1].trim();

      const bookingAmount = owner.pricePerHour || 1000;
      const totalAmount = bookingAmount + 50;
      const payLink = await paymentService.createBookingLink({
        phone,
        ownerId: owner.id,
        date: context.selectedDate,
        slotTime: context.selectedSlot,
        captainName: context.captainName,
        teamName: context.teamName,
        amount: totalAmount
      });

      await whatsappService.sendText(
        phone,
        `📋 *Booking Summary - ${owner.turfName}* 📋\n\n` +
        `Hello ${context.captainName}, here is your booking summary:\n\n` +
        `• Turf: *${owner.turfName}*\n` +
        `• Date: ${context.selectedDate}\n` +
        `• Time Slot: ${context.selectedSlot}\n` +
        `• Captain Name: ${context.captainName}\n` +
        `• Team Name: ${context.teamName}\n\n` +
        `*Payment Breakdown:*\n` +
        `• Turf Rate: ₹${bookingAmount}.00\n` +
        `• STRIKIT Booking Fee: ₹50.00\n` +
        `• *Total Amount:* *₹${totalAmount}.00*\n\n` +
        `🔗 *Payment Link:* Please click the link below to securely pay and confirm your booking:\n` +
        `${payLink}\n\n` +
        `_Powered by STRIKIT_`
      );

      await updateSession(phone, 'AWAITING_PAYMENT_CONFIRMATION', context, prisma);
      break;

    case 'AWAITING_PAYMENT_CONFIRMATION':
      const bookingAmt = owner.pricePerHour || 1000;
      const totalAmt = bookingAmt + 50;
      const awaitingPayLink = await paymentService.createBookingLink({
        phone,
        ownerId: owner.id,
        date: context.selectedDate,
        slotTime: context.selectedSlot,
        captainName: context.captainName,
        teamName: context.teamName,
        amount: totalAmt
      });
      await whatsappService.sendText(
        phone,
        `⏳ *Awaiting Payment Confirmation* ⏳\n\n` +
        `Your slot is temporarily held. Please click here to complete your payment:\n` +
        `👉 ${awaitingPayLink}\n\n` +
        `_Powered by STRIKIT_`
      );
      break;

    case 'AWAITING_SINGLE_SLOT_SELECTION':
      const joinSlotTime = text.trim();
      
      const targetSlot = await prisma.botTurfSlot.findFirst({
        where: { ownerId: owner.id, date: context.selectedDate, timeSlot: joinSlotTime, status: 'BOOKED' },
        include: { bookings: true }
      });

      if (!targetSlot || targetSlot.bookings.length === 0) {
        await whatsappService.sendText(phone, "Invalid slot selection or slot is not booked by a team. Please select a valid Booked slot:");
        return;
      }

      context.bookingIdToJoin = targetSlot.bookings[0].id;
      context.selectedSlot = joinSlotTime;
      
      await whatsappService.sendText(phone, "Please enter your Name:");
      await updateSession(phone, 'AWAITING_SINGLE_PLAYER_NAME', context, prisma);
      break;

    case 'AWAITING_SINGLE_PLAYER_NAME':
      context.playerName = text;
      
      const targetBooking = await prisma.botBooking.findUnique({
        where: { id: context.bookingIdToJoin }
      });

      // Create Join Request awaiting payment (status: 'AWAITING_PAYMENT')
      const joinReq = await prisma.botJoinRequest.create({
        data: {
          bookingId: context.bookingIdToJoin,
          playerName: context.playerName,
          playerPhone: phone,
          status: 'AWAITING_PAYMENT'
        }
      });

      // Ask player to pay ₹9 platform fee (non-refundable)
      const joinPayLink = await paymentService.createJoinRequestLink(joinReq.id, phone);
      await whatsappService.sendText(
        phone,
        `💳 *STRIKIT Platform Fee Payment* 💳\n\n` +
        `Hello ${context.playerName}, to submit your request to join the game at *${owner.turfName}*, please pay the platform fee:\n\n` +
        `• *Amount:* *₹9.00* (Non-Refundable)\n\n` +
        `🔗 *Payment Link:* Click below to pay via Razorpay:\n` +
        `${joinPayLink}\n\n` +
        `_Powered by STRIKIT_`
      );

      context.joinRequestId = joinReq.id;
      await updateSession(phone, 'AWAITING_SINGLE_PLAYER_PAYMENT', context, prisma);
      break;

    case 'AWAITING_SINGLE_PLAYER_PAYMENT':
      const awaitingJoinPayLink = await paymentService.createJoinRequestLink(context.joinRequestId, phone);
      await whatsappService.sendText(
        phone,
        `⏳ *Awaiting Platform Fee Payment* ⏳\n\n` +
        `Please complete the ₹9.00 non-refundable platform fee payment to notify the captain:\n` +
        `👉 ${awaitingJoinPayLink}\n\n` +
        `_Powered by STRIKIT_`
      );
      break;

    default:
      await whatsappService.sendText(phone, "Session reset. Type 'Hi' to book slots.");
      await prisma.botSession.delete({ where: { phone } });
  }
}

/**
 * =========================================================================
 * HELPER FUNCTIONS
 * =========================================================================
 */
async function updateSession(phone, state, context, prisma) {
  await prisma.botSession.update({
    where: { phone },
    data: { state, context: JSON.stringify(context) }
  });
}

async function sendDateSelection(phone, prisma) {
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const dayAfter = new Date(today);
  dayAfter.setDate(today.getDate() + 2);

  const format = (d) => d.toISOString().split('T')[0];

  await whatsappService.sendButtons(
    phone,
    `📅 *Please Select a Date* 📅\n\n` +
    `Choose one of the dates below to view available slots:`,
    [
      { id: `date_${format(today)}`, title: `Today (${format(today)})` },
      { id: `date_${format(tomorrow)}`, title: `Tomorrow (${format(tomorrow)})` },
      { id: `date_${format(dayAfter)}`, title: `Day After (${format(dayAfter)})` }
    ]
  );
}

async function sendOwnerDashboard(phone, prisma) {
  const sections = [
    {
      title: "Owner Operations",
      rows: [
        { id: "dashboard_bookings", title: "📅 Booking List", description: "View your bookings summary" },
        { id: "dashboard_revenue", title: "💰 Revenue Stats", description: "View earnings statistics" },
        { id: "dashboard_report", title: "📄 PDF Report", description: "Download transaction sheet PDF" },
        { id: "dashboard_edit_settings", title: "⚙️ Edit Settings", description: "Update turf details and options" },
        { id: "dashboard_block_slot", title: "🚫 Block/Unblock Slot", description: "Temporarily block or open slots" }
      ]
    }
  ];

  await whatsappService.sendList(
    phone,
    `🛡️ *STRIKIT Owner Control Panel* 🛡️\n\n` +
    `Hello! Welcome to your turf management dashboard. Choose an action from the menu below to manage your turf:\n\n` +
    `_Powered by STRIKIT_`,
    "Open Menu",
    sections
  );
}

async function sendSettingsEditMenu(phone, prisma) {
  const sections = [
    {
      title: "Turf Details",
      rows: [
        { id: "edit_name", title: "Turf Name", description: "Change turf display name" },
        { id: "edit_price", title: "Hourly Rate", description: "Update booking price per hour" },
        { id: "edit_location", title: "Location Link", description: "Update Google Maps location link" },
        { id: "edit_ownername", title: "Owner Name", description: "Change owner's name" },
        { id: "edit_photos", title: "Photos Link", description: "Update turf photos URL" }
      ]
    },
    {
      title: "Verification Details",
      rows: [
        { id: "edit_gst", title: "GST Number", description: "Update GST registration number" },
        { id: "edit_msme", title: "MSME Certificate", description: "Update MSME registration number/file" },
        { id: "edit_upi", title: "UPI ID", description: "Update UPI ID for receiving payments" }
      ]
    },
    {
      title: "Operational Hours",
      rows: [
        { id: "edit_opening", title: "Opening Time", description: "Update opening time (e.g. 06:00 AM)" },
        { id: "edit_closing", title: "Closing Time", description: "Update closing time (e.g. 10:00 PM)" }
      ]
    }
  ];

  await whatsappService.sendList(
    phone,
    `⚙️ *Edit Turf Settings* ⚙️\n\n` +
    `Select the field you want to update from the list below:\n\n` +
    `_Powered by STRIKIT_`,
    "Select Field",
    sections
  );
}

async function sendBlockDateSelection(phone, prisma) {
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const dayAfter = new Date(today);
  dayAfter.setDate(today.getDate() + 2);

  const format = (d) => d.toISOString().split('T')[0];

  await whatsappService.sendButtons(
    phone,
    `🚫 *Select a Date for Block/Unblock* 🚫\n\n` +
    `Please select the date for which you want to manage slot availability:\n\n` +
    `_Powered by STRIKIT_`,
    [
      { id: `block_date_${format(today)}`, title: `Today (${format(today)})` },
      { id: `block_date_${format(tomorrow)}`, title: `Tomorrow (${format(tomorrow)})` },
      { id: `block_date_${format(dayAfter)}`, title: `Day After (${format(dayAfter)})` }
    ]
  );
}

async function sendBlockSlotToggleList(phone, ownerId, date, prisma) {
  await ensureSlotsGenerated(ownerId, date, prisma);

  const slots = await prisma.botTurfSlot.findMany({
    where: { ownerId, date }
  });
  slots.sort((a, b) => parseTimeTo24h(a.timeSlot) - parseTimeTo24h(b.timeSlot));

  const rows = slots.map(s => {
    const isBlocked = s.status === 'BLOCKED';
    const statusText = isBlocked ? '🚫 Blocked (Click to Open)' : (s.status === 'BOOKED' ? '🔴 Booked (Cannot Toggle)' : '🟢 Open (Click to Block)');
    return {
      id: `toggle_block_${date}_${s.timeSlot}`,
      title: s.timeSlot,
      description: statusText
    };
  });

  const sections = [
    {
      title: `Slots on ${date}`,
      rows
    }
  ];

  await whatsappService.sendList(
    phone,
    `🚫 *Slot Availability Dashboard* 🚫\n\n` +
    `Click a slot to toggle its availability (Block/Unblock) for *${date}*:\n` +
    `• 🟢 Open slots will be blocked.\n` +
    `• 🚫 Blocked slots will be reopened.\n\n` +
    `_Powered by STRIKIT_`,
    "Toggle Slots",
    sections
  );
}

async function executeBookings(phone, owner, prisma) {
  const slots = await prisma.botTurfSlot.findMany({
    where: { ownerId: owner.id, status: { in: ['BOOKED', 'BLOCKED'] } },
    include: { bookings: true },
    orderBy: [{ date: 'asc' }, { timeSlot: 'asc' }]
  });

  if (slots.length === 0) {
    await whatsappService.sendText(phone, "You have no bookings or blocked slots currently.\n\n_Powered by STRIKIT_");
    return;
  }

  let summary = `📅 *STRIKIT Booking Dashboard for ${owner.turfName}*\n\n`;
  slots.forEach(s => {
    const isBlocked = s.status === 'BLOCKED';
    const booking = s.bookings[0];
    if (isBlocked) {
      summary += `🚫 Slot: ${s.date} @ ${s.timeSlot} - BLOCKED\n`;
    } else if (booking) {
      summary += `⚽ Slot: ${s.date} @ ${s.timeSlot}\n   Team: ${booking.teamName}\n   Captain: ${booking.captainName} (${booking.captainPhone})\n   Paid: ₹${booking.amountPaid}\n\n`;
    }
  });
  summary += `_Powered by STRIKIT_`;
  await whatsappService.sendText(phone, summary);
}

async function executeRevenue(phone, owner, prisma) {
  const bookings = await prisma.botBooking.findMany({
    where: { slot: { ownerId: owner.id } },
    include: { slot: true }
  });

  const total = bookings.reduce((sum, b) => sum + b.amountPaid, 0);
  const count = bookings.length;
  const feeCollected = count * 30; // ₹30/booking booking fee
  const net = total - feeCollected;

  const reportText = `💰 *STRIKIT Revenue Summary*\n` +
                     `Turf: ${owner.turfName}\n\n` +
                     `• Total Bookings: ${count}\n` +
                     `• Gross Revenue: ₹${total.toFixed(2)}\n` +
                     `• STRIKIT Platform Fees: ₹${feeCollected.toFixed(2)}\n` +
                     `• Net Earnings: ₹${net.toFixed(2)}\n\n` +
                     `_Powered by STRIKIT_`;

  await whatsappService.sendText(phone, reportText);
}

async function executeReport(phone, owner, prisma) {
  await executeReportWithRange(phone, owner, 'ALL_TIME', prisma);
}

async function startReportFlow(phone, prisma) {
  await whatsappService.sendButtons(
    phone,
    `📊 *Select PDF Report Range* 📊\n\n` +
    `Please select the period for your earnings report:\n` +
    `1️⃣ *Current Month*\n` +
    `2️⃣ *Previous Month*\n` +
    `3️⃣ *All-Time*`,
    [
      { id: 'report_current_month', title: '1. Current Month' },
      { id: 'report_prev_month', title: '2. Previous Month' },
      { id: 'report_all_time', title: '3. All-Time' }
    ]
  );
  await prisma.botSession.update({
    where: { phone },
    data: { state: 'AWAITING_REPORT_RANGE_CHOICE' }
  });
}

async function executeReportWithRange(phone, owner, range, prisma) {
  const bookings = await prisma.botBooking.findMany({
    where: { slot: { ownerId: owner.id } },
    include: { slot: true }
  });

  let filteredBookings = bookings;
  const now = new Date();

  if (range === 'CURRENT_MONTH') {
    const currentYearMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    filteredBookings = bookings.filter(b => b.slot.date.startsWith(currentYearMonth));
  } else if (range === 'PREVIOUS_MONTH') {
    let prevYear = now.getFullYear();
    let prevMonthVal = now.getMonth();
    if (prevMonthVal === 0) {
      prevMonthVal = 12;
      prevYear -= 1;
    }
    const prevYearMonth = `${prevYear}-${String(prevMonthVal).padStart(2, '0')}`;
    filteredBookings = bookings.filter(b => b.slot.date.startsWith(prevYearMonth));
  }

  await whatsappService.sendText(phone, "Generating report... Please wait.");
  try {
    const reportsDir = path.resolve('reports');
    if (!fs.existsSync(reportsDir)) {
      fs.mkdirSync(reportsDir, { recursive: true });
    }
    const pdfPath = generateRevenueReport(owner, filteredBookings, reportsDir);
    const url = `http://localhost:5000/reports/${path.basename(pdfPath)}`;
    await whatsappService.sendDocument(phone, url, `report_${owner.id}.pdf`, `Here is your revenue report PDF, ${owner.name}!`);
  } catch (err) {
    console.error(err);
    await whatsappService.sendText(phone, "Failed to generate report PDF.");
  }
}

async function getSlotsListText(ownerId, date, prisma) {
  const savedSlots = await prisma.botTurfSlot.findMany({
    where: { ownerId, date }
  });
  
  // Sort slots chronologically
  savedSlots.sort((a, b) => parseTimeTo24h(a.timeSlot) - parseTimeTo24h(b.timeSlot));

  let output = '';
  savedSlots.forEach(s => {
    const statusIndicator = s.status === 'AVAILABLE' ? '🟢 Available' : (s.status === 'BOOKED' ? '🔴 Booked' : '🚫 Blocked');
    output += `• ${s.timeSlot}: ${statusIndicator}\n`;
  });
  return output;
}

async function getBookedSlotsText(ownerId, date, prisma) {
  const bookedSlots = await prisma.botTurfSlot.findMany({
    where: { ownerId, date, status: 'BOOKED' },
    include: { bookings: true }
  });

  if (bookedSlots.length === 0) return null;

  let output = '';
  bookedSlots.forEach(s => {
    const booking = s.bookings[0];
    output += `• ${s.timeSlot} (Team: ${booking.teamName} - Captain: ${booking.captainName})\n`;
  });
  return output;
}

async function ensureSlotsGenerated(ownerId, date, prisma) {
  const count = await prisma.botTurfSlot.count({
    where: { ownerId, date }
  });

  if (count > 0) return;

  const owner = await prisma.botOwner.findUnique({
    where: { id: ownerId }
  });

  if (!owner) return;

  const startHour = parseTimeTo24h(owner.openingTime);
  const endHour = parseTimeTo24h(owner.closingTime);

  const newSlots = [];
  for (let h = startHour; h < endHour; h++) {
    newSlots.push({
      ownerId,
      date,
      timeSlot: formatHourTo12h(h),
      status: 'AVAILABLE'
    });
  }

  if (newSlots.length > 0) {
    await prisma.botTurfSlot.createMany({
      data: newSlots,
      skipDuplicates: true
    });
  }
}

function parseTimeTo24h(timeStr) {
  try {
    const cleaned = timeStr.trim().toUpperCase();
    const parts = cleaned.split(/\s+/);
    
    let timePart = parts[0];
    let ampm = parts[1] || '';

    if (!ampm) {
      if (cleaned.endsWith('PM')) {
        ampm = 'PM';
        timePart = cleaned.replace('PM', '');
      } else if (cleaned.endsWith('AM')) {
        ampm = 'AM';
        timePart = cleaned.replace('AM', '');
      }
    }

    const timeParts = timePart.split(':');
    let hours = parseInt(timeParts[0], 10);
    
    if (ampm === 'PM' && hours < 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;
    
    return isNaN(hours) ? 6 : hours;
  } catch (err) {
    return 6;
  }
}

function formatHourTo12h(hour) {
  const ampm = hour >= 12 ? 'PM' : 'AM';
  let displayHour = hour % 12;
  if (displayHour === 0) displayHour = 12;
  const pad = displayHour < 10 ? '0' : '';
  return `${pad}${displayHour}:00 ${ampm}`;
}

export function isGoogleMapsLink(text) {
  const urlPattern = /(maps\.google\.com|goo\.gl\/maps|maps\.app\.goo\.gl)/i;
  return urlPattern.test(text);
}

export async function extractCoordinatesFromGoogleMapsLink(url) {
  // First attempt: try to parse coordinates directly from the given URL
  const atRegex = /@(-?\d+\.\d+),(-?\d+\.\d+)/;
  let match = url.match(atRegex);
  if (match) {
    return { latitude: parseFloat(match[1]), longitude: parseFloat(match[2]) };
  }

  const qRegex = /[?&](q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)/;
  match = url.match(qRegex);
  if (match) {
    return { latitude: parseFloat(match[2]), longitude: parseFloat(match[3]) };
  }

  // Second attempt: if it's a short/redirect URL, resolve it first
  if (url.includes('goo.gl') || url.includes('maps.app.goo.gl') || url.includes('maps.google.com') || url.includes('google.com/maps')) {
    try {
      const response = await axios.get(url, {
        maxRedirects: 5,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36'
        },
        timeout: 5000,
        validateStatus: (status) => status >= 200 && status < 400
      });
      const targetUrl = response.request?.res?.responseUrl || response.headers?.location || url;
      
      let match = targetUrl.match(atRegex);
      if (match) {
        return { latitude: parseFloat(match[1]), longitude: parseFloat(match[2]) };
      }

      match = targetUrl.match(qRegex);
      if (match) {
        return { latitude: parseFloat(match[2]), longitude: parseFloat(match[3]) };
      }
    } catch (error) {
      console.error('Error resolving Google Maps URL:', error.message);
    }
  }

  return null;
}

async function handleDeveloperWhatsAppCommand(phone, text, prisma) {
  const parts = text.split(/\s+/);
  const command = parts[0].toLowerCase();
  
  if (parts.length < 2) {
    await whatsappService.sendText(phone, "❌ Format error. Please send: /approve [OwnerId], /reject [OwnerId], /deactivate [OwnerId] or /activate [OwnerId]");
    return;
  }
  
  const ownerId = parseInt(parts[1], 10);
  if (isNaN(ownerId)) {
    await whatsappService.sendText(phone, "❌ Invalid Owner ID. Please specify a numeric ID.");
    return;
  }
  
  const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
  if (!owner) {
    await whatsappService.sendText(phone, `❌ Owner with ID ${ownerId} not found.`);
    return;
  }
  
  if (command === '/approve') {
    await prisma.botOwner.update({
      where: { id: ownerId },
      data: { verified: true, subscriptionActive: false, subscriptionExpiry: null }
    });

    const subLink = await paymentService.createSubscriptionLink(ownerId);

    // Fetch existing context or build new one
    const existingSession = await prisma.botSession.findUnique({ where: { phone: owner.mobile } });
    const existingContext = JSON.parse(existingSession?.context || '{}');
    const newContext = { ...existingContext, ownerId: ownerId };

    await prisma.botSession.upsert({
      where: { phone: owner.mobile },
      update: { role: 'ONBOARDING', state: 'AWAITING_SUBSCRIPTION', context: JSON.stringify(newContext) },
      create: { phone: owner.mobile, role: 'ONBOARDING', state: 'AWAITING_SUBSCRIPTION', context: JSON.stringify(newContext) }
    });

    // Send confirmation to Developer who approved
    await whatsappService.sendText(phone, `✅ Owner *${owner.name}* (Turf: *${owner.turfName}*) has been approved successfully! Awaiting subscription payment.`);

    // Notify Owner on their onboarding number
    await whatsappService.sendText(
      owner.mobile,
      `🎉 *Congratulations ${owner.name}! Your STRIKIT Registration has been APPROVED!* 🎉\n\n` +
      `Your turf *${owner.turfName}* has been verified by the developer.\n\n` +
      `💳 *Subscription Link:* Please pay ₹699.00 to activate your bot and generate your booking QR Code:\n` +
      `${subLink}\n\n` +
      `_Powered by STRIKIT_`
    );
  } else if (command === '/reject') {
    await prisma.botOwner.update({
      where: { id: ownerId },
      data: { verified: false, subscriptionActive: false, subscriptionExpiry: null }
    });

    // Send confirmation to Developer who rejected
    await whatsappService.sendText(phone, `❌ Owner *${owner.name}* (Turf: *${owner.turfName}*) has been rejected.`);

    // Notify Owner on their onboarding number
    await whatsappService.sendText(
      owner.mobile,
      `❌ Hello ${owner.name}, your STRIKIT registration for *${owner.turfName}* was rejected. Please contact support to check details.\n\n` +
      `_Powered by STRIKIT_`
    );
  } else if (command === '/deactivate') {
    await prisma.botOwner.update({
      where: { id: ownerId },
      data: { subscriptionActive: false, subscriptionExpiry: new Date() }
    });

    await whatsappService.sendText(phone, `⚠️ Owner *${owner.name}* (Turf: *${owner.turfName}*) has been deactivated.`);

    // Notify Owner
    await whatsappService.sendText(
      owner.mobile,
      `⚠️ *STRIKIT Notification:* Your bot subscription for *${owner.turfName}* has been deactivated by the admin. Please contact support to reactivate.\n\n` +
      `_Powered by STRIKIT_`
    );
  } else if (command === '/activate') {
    const activationExpiry = new Date();
    activationExpiry.setDate(activationExpiry.getDate() + 30); // 30 days activation

    await prisma.botOwner.update({
      where: { id: ownerId },
      data: { subscriptionActive: true, subscriptionExpiry: activationExpiry }
    });

    await whatsappService.sendText(phone, `✅ Owner *${owner.name}* (Turf: *${owner.turfName}*) has been reactivated successfully for 30 days!`);

    // Notify Owner
    await whatsappService.sendText(
      owner.mobile,
      `🎉 *STRIKIT Notification:* Your bot subscription for *${owner.turfName}* has been reactivated successfully for 30 days! 🚀\n\n` +
      `_Powered by STRIKIT_`
    );
  }
}

export async function handleCentralizedPlayerFlow(phone, text, prisma, mediaId = '', mediaType = '') {
  const lowerText = text.toLowerCase().trim();
  let session = await prisma.botSession.findUnique({ where: { phone } });

  // Handle Book [TurfName] QR Code scans
  if (lowerText.startsWith('book ')) {
    const turfNameQuery = text.substring(5).trim();
    // Soft match turf name (case insensitive)
    const owners = await prisma.botOwner.findMany({
      where: { verified: true, subscriptionActive: true }
    });
    const matchedOwner = owners.find(o => o.turfName.toLowerCase() === turfNameQuery.toLowerCase());
    if (matchedOwner) {
      session = await prisma.botSession.upsert({
        where: { phone },
        update: { role: 'CUSTOMER', state: 'PLAYER_START', context: JSON.stringify({ turfId: matchedOwner.id }) },
        create: { phone, role: 'CUSTOMER', state: 'PLAYER_START', context: JSON.stringify({ turfId: matchedOwner.id }) }
      });
      return handlePlayerFlow(phone, 'Hi', matchedOwner, prisma);
    } else {
      await whatsappService.sendText(phone, `❌ Turf "${turfNameQuery}" not found or inactive. Please scan a valid QR code or send 'hi' to search nearby.`);
      return;
    }
  }

  // Initialize player flow if no session exists or they send "hi" / "hello"
  if (!session || session.role !== 'CUSTOMER' || lowerText === 'hi' || lowerText === 'hello' || lowerText === 'menu') {
    // Check previous booking history
    const lastBooking = await prisma.botBooking.findFirst({
      where: { captainPhone: phone },
      orderBy: { createdAt: 'desc' },
      include: { slot: { include: { owner: true } } }
    });

    if (lastBooking && lastBooking.slot?.owner) {
      const prevTurf = lastBooking.slot.owner;
      session = await prisma.botSession.upsert({
        where: { phone },
        update: {
          role: 'CUSTOMER',
          state: 'AWAITING_PREVIOUS_TURF_CONFIRMATION',
          context: JSON.stringify({ previousTurfId: prevTurf.id })
        },
        create: {
          phone,
          role: 'CUSTOMER',
          state: 'AWAITING_PREVIOUS_TURF_CONFIRMATION',
          context: JSON.stringify({ previousTurfId: prevTurf.id })
        }
      });

      await whatsappService.sendButtons(
        phone,
        `👋 *Welcome Back!* ⚽\n\n` +
        `Would you like to book a slot at *${prevTurf.turfName}* again?`,
        [
          { id: 'confirm_prev_yes', title: 'Yes' },
          { id: 'confirm_prev_no', title: 'No' }
        ]
      );
      return;
    } else {
      // New user or no bookings
      session = await prisma.botSession.upsert({
        where: { phone },
        update: { role: 'CUSTOMER', state: 'AWAITING_LOCATION_OR_SEARCH', context: '{}' },
        create: { phone, role: 'CUSTOMER', state: 'AWAITING_LOCATION_OR_SEARCH', context: '{}' }
      });

      await whatsappService.sendText(
        phone,
        `👋 *Welcome to STRIKIT!* ⚽\n\n` +
        `To help you find the best turfs nearby, please share your current location using the WhatsApp Location button (📎 -> Location).`
      );
      return;
    }
  }

  const context = JSON.parse(session.context || '{}');

  // Handle centralized search states
  if (session.state === 'AWAITING_PREVIOUS_TURF_CONFIRMATION') {
    if (text === '1' || lowerText === 'yes' || text === 'confirm_prev_yes') {
      const owner = await prisma.botOwner.findUnique({ where: { id: context.previousTurfId } });
      if (owner && owner.verified && owner.subscriptionActive) {
        session = await prisma.botSession.update({
          where: { phone },
          data: { state: 'PLAYER_START', context: JSON.stringify({ turfId: owner.id }) }
        });
        return handlePlayerFlow(phone, 'Hi', owner, prisma);
      } else {
        await whatsappService.sendText(phone, "⚠️ That turf is currently unavailable. Let's find other turfs nearby.");
        session = await prisma.botSession.update({
          where: { phone },
          data: { state: 'AWAITING_LOCATION_OR_SEARCH', context: '{}' }
        });
        await whatsappService.sendText(
          phone,
          `Please share your current location using the WhatsApp Location button (📎 -> Location):`
        );
        return;
      }
    } else if (text === '2' || lowerText === 'no' || text === 'confirm_prev_no') {
      session = await prisma.botSession.update({
        where: { phone },
        data: { state: 'AWAITING_LOCATION_OR_SEARCH', context: '{}' }
      });
      await whatsappService.sendText(
        phone,
        `Please share your current location using the WhatsApp Location button (📎 -> Location) to search for turfs within 10km:`
      );
      return;
    } else {
      await whatsappService.sendText(phone, "Please reply with 1 for Yes, or 2 for No.");
      return;
    }
  }

  if (session.state === 'AWAITING_LOCATION_OR_SEARCH') {
    if (text.startsWith('location:')) {
      const parts = text.substring(9).split(',');
      const playerLat = parseFloat(parts[0]);
      const playerLng = parseFloat(parts[1]);

      if (isNaN(playerLat) || isNaN(playerLng)) {
        await whatsappService.sendText(phone, "❌ Error parsing location. Please try sharing your location again:");
        return;
      }

      const verifiedTurfs = await prisma.botOwner.findMany({
        where: { verified: true, subscriptionActive: true }
      });

      const nearbyTurfs = verifiedTurfs.map(turf => {
        const distance = (turf.latitude && turf.longitude) ? calculateDistance(playerLat, playerLng, turf.latitude, turf.longitude) : 999999;
        return { ...turf, distance };
      }).filter(t => t.distance <= 10).sort((a, b) => a.distance - b.distance);

      if (nearbyTurfs.length === 0) {
        await whatsappService.sendText(phone, "❌ No verified turfs found within 10km of your location. Please share a different location:");
        return;
      }

      context.nearbyTurfs = nearbyTurfs.map(t => t.id);
      const listMessage = `🏟️ *Nearby Turfs Found (within 10km):*\n\n` +
        nearbyTurfs.map((t, idx) => `*${idx + 1}* - *${t.turfName}* (${t.distance.toFixed(1)} km)\n📍 ${t.location}`).join('\n\n') +
        `\n\nReply with the number (e.g. 1) to select and book your turf!`;
      
      await whatsappService.sendText(phone, listMessage);
      await updateSession(phone, 'AWAITING_SEARCH_RESULT_SELECTION', context, prisma);
      return;
    } else {
      // Block text input, only allow native location
      await whatsappService.sendText(phone, "⚠️ Please share your precise coordinates using the native WhatsApp Location sharing button (the paperclip icon 📎 -> Location) so we can find turfs within a 10km radius of your location.");
      return;
    }
  }

  if (session.state === 'AWAITING_SEARCH_RESULT_SELECTION') {
    const selectionIdx = parseInt(text.trim(), 10) - 1;
    if (isNaN(selectionIdx) || !context.nearbyTurfs || selectionIdx < 0 || selectionIdx >= context.nearbyTurfs.length) {
      await whatsappService.sendText(phone, `❌ Invalid selection. Please reply with a number between 1 and ${context.nearbyTurfs?.length || 1}:`);
      return;
    }
    const selectedTurfId = context.nearbyTurfs[selectionIdx];
    const turfOwner = await prisma.botOwner.findUnique({ where: { id: selectedTurfId } });
    if (!turfOwner) {
      await whatsappService.sendText(phone, "❌ Turf not found. Please try searching again by sending your location:");
      await updateSession(phone, 'AWAITING_LOCATION_OR_SEARCH', {}, prisma);
      return;
    }
    context.turfId = turfOwner.id;
    delete context.nearbyTurfs;
    
    session = await prisma.botSession.update({
      where: { phone },
      data: { role: 'CUSTOMER', state: 'PLAYER_START', context: JSON.stringify(context) }
    });
    return handlePlayerFlow(phone, 'Hi', turfOwner, prisma);
  }

  // Otherwise, we are in an active turf's booking states (e.g. AWAITING_DATE_SELECTION, etc.)
  const owner = await prisma.botOwner.findUnique({ where: { id: context.turfId } });
  if (!owner) {
    await whatsappService.sendText(phone, "❌ Turf configuration error. Please send 'hi' to start over.");
    await prisma.botSession.delete({ where: { phone } });
    return;
  }
  return handlePlayerFlow(phone, text, owner, prisma);
}

function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Radius of the earth in km
  const dLat = deg2rad(lat2 - lat1);
  const dLon = deg2rad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2)
    ;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const d = R * c; // Distance in km
  return d;
}

function deg2rad(deg) {
  return deg * (Math.PI / 180);
}

