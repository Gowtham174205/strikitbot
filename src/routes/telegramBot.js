import * as whatsappService from '../services/whatsappService.js';
import axios from 'axios';
import dotenv from 'dotenv';
import path from 'path';
import { generatePlatformReport } from '../services/pdfGenerator.js';
import { sendPlatformReport } from '../services/telegramService.js';

dotenv.config();

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;

async function sendMessage(chatId, text) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) {
    console.log(`\n[MOCK TELEGRAM MESSAGE to ${chatId}]:\n${text}\n`);
    return;
  }
  try {
    await axios.post(`https://api.telegram.org/bot${token}/sendMessage`, {
      chat_id: chatId,
      text,
      parse_mode: 'Markdown'
    });
  } catch (err) {
    console.error('Telegram sendMessage Error:', err.response?.data || err.message);
  }
}

export async function triggerAndSendMonthlyReport(prisma, options = {}) {
  const now = new Date();
  let start, end;
  
  if (options.previousMonth) {
    // Previous month (e.g. if we are on the 1st of June, we want May)
    start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    end = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59, 999);
  } else {
    // Current month to date
    start = new Date(now.getFullYear(), now.getMonth(), 1);
    end = now;
  }
  
  // Query bookings
  const bookings = await prisma.botBooking.findMany({
    where: {
      createdAt: {
        gte: start,
        lte: end
      }
    },
    include: {
      slot: {
        include: {
          owner: true
        }
      }
    }
  });

  // Query join requests
  const joinRequests = await prisma.botJoinRequest.findMany({
    where: {
      status: 'ACCEPTED',
      createdAt: {
        gte: start,
        lte: end
      }
    },
    include: {
      booking: {
        include: {
          slot: {
            include: {
              owner: true
            }
          }
        }
      }
    }
  });

  // Generate PDF
  const reportsDir = path.resolve('reports');
  const pdfPath = await generatePlatformReport(bookings, joinRequests, reportsDir);

  // Send to Telegram
  const monthName = start.toLocaleString('default', { month: 'long', year: 'numeric' });
  const caption = `📊 *STRIKIT Platform Revenue Report - ${monthName}*\n\n` +
                  `• Period: ${start.toLocaleDateString()} to ${end.toLocaleDateString()}\n` +
                  `• Total Team Bookings: ${bookings.length} (INR 30 each)\n` +
                  `• Total Accepted Joins: ${joinRequests.length} (INR 9 each)\n` +
                  `• Net Platform Revenue: INR ${(bookings.length * 30 + joinRequests.length * 9).toFixed(2)}`;

  await sendPlatformReport(pdfPath, caption);
  return { pdfPath, caption };
}

export async function handleTelegramWebhook(req, res, prisma) {
  const body = req.body;

  // 1. Handle text message command (/monthlyreport)
  if (body.message && body.message.text) {
    const text = body.message.text.trim();
    const chatId = body.message.chat.id.toString();

    if (text === '/monthlyreport') {
      const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;
      // Security check: restrict to configured chat id (if configured)
      if (TELEGRAM_CHAT_ID && chatId !== TELEGRAM_CHAT_ID) {
        await sendMessage(chatId, '❌ Unauthorized chat. This command is restricted to the admin group.');
        return res.sendStatus(200);
      }

      try {
        await sendMessage(chatId, '🔄 Generating monthly platform report...');
        await triggerAndSendMonthlyReport(prisma, { previousMonth: false });
      } catch (err) {
        console.error('Error in manual /monthlyreport command:', err);
        await sendMessage(chatId, `❌ Error generating report: ${err.message}`);
      }
      return res.sendStatus(200);
    }
  }

  // 2. Handle callback query buttons (Approvals / Rejections)
  if (body.callback_query) {
    const callbackQuery = body.callback_query;
    const data = callbackQuery.data;
    const message = callbackQuery.message;
    const callbackQueryId = callbackQuery.id;

    let ownerId;
    let action = '';

    if (data.startsWith('verify_approve_')) {
      ownerId = parseInt(data.replace('verify_approve_', ''), 10);
      action = 'APPROVE';
    } else if (data.startsWith('verify_reject_')) {
      ownerId = parseInt(data.replace('verify_reject_', ''), 10);
      action = 'REJECT';
    }

    if (ownerId && action) {
      const owner = await prisma.botOwner.findUnique({ where: { id: ownerId } });
      if (!owner) {
        await answerCallbackQuery(callbackQueryId, 'Owner not found.');
        return res.sendStatus(200);
      }

      if (action === 'APPROVE') {
        await prisma.botOwner.update({
          where: { id: ownerId },
          data: { verified: true, subscriptionActive: true }
        });

        await prisma.botSession.upsert({
          where: { phone: owner.mobile },
          update: { state: 'AWAITING_BUSINESS_CONNECT' },
          create: { phone: owner.mobile, role: 'ONBOARDING', state: 'AWAITING_BUSINESS_CONNECT' }
        });

        const updatedText = message.text + `\n\n✅ *Status: APPROVED*`;
        await editTelegramMessage(message.chat.id, message.message_id, updatedText);

        await whatsappService.sendText(
          owner.mobile,
          `🎉 *Congratulations ${owner.name}! Your STRIKIT Registration has been APPROVED!* 🎉\n\n` +
          `Your turf *${owner.turfName}* has been verified by the developer.\n\n` +
          `📲 *Final Step:* Please connect your WhatsApp Business Number to this bot now by typing:\n` +
          `👉 \`/connect [WhatsAppNumber]\` (e.g., \`/connect 919876543210\`)\n\n` +
          `_Powered by STRIKIT_`
        );

        await answerCallbackQuery(callbackQueryId, 'Owner approved successfully!');
      } else if (action === 'REJECT') {
        await prisma.botOwner.update({
          where: { id: ownerId },
          data: { verified: false, subscriptionActive: false }
        });

        const updatedText = message.text + `\n\n❌ *Status: REJECTED*`;
        await editTelegramMessage(message.chat.id, message.message_id, updatedText);

        await whatsappService.sendText(
          owner.mobile,
          `❌ Hello ${owner.name}, your STRIKIT registration for ${owner.turfName} was rejected. Please contact support to check details.`
        );

        await answerCallbackQuery(callbackQueryId, 'Owner rejected.');
      }
    }
  }

  res.sendStatus(200);
}

async function answerCallbackQuery(callbackQueryId, text) {
  if (!TELEGRAM_BOT_TOKEN) return;
  try {
    await axios.post(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
      callback_query_id: callbackQueryId,
      text
    });
  } catch (err) {
    console.error('Telegram answerCallbackQuery Error:', err.message);
  }
}

async function editTelegramMessage(chatId, messageId, text) {
  if (!TELEGRAM_BOT_TOKEN) {
    console.log(`\n[MOCK TELEGRAM MESSAGE EDIT: Chat ${chatId}, Message ${messageId}]`);
    console.log(text);
    console.log('Buttons Removed.\n');
    return;
  }
  try {
    await axios.post(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/editMessageText`, {
      chat_id: chatId,
      message_id: messageId,
      text,
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: [] }
    });
  } catch (err) {
    console.error('Telegram editMessageText Error:', err.message);
  }
}
