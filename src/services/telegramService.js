import axios from 'axios';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
dotenv.config();

export const mockTelegramMessages = [];

export function getMockTelegramMessages() {
  return mockTelegramMessages;
}

export function clearMockTelegramMessages() {
  mockTelegramMessages.length = 0;
}

async function sendTelegramRequest(method, payload) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    mockTelegramMessages.push(payload);
    console.log(`\n=== [MOCK TELEGRAM ALERT to ${chatId || 'Admin'}] ===`);
    console.log(payload.text);
    if (payload.reply_markup?.inline_keyboard) {
      console.log('Interactive Buttons:');
      payload.reply_markup.inline_keyboard.forEach(row => {
        row.forEach(btn => {
          console.log(`  - [${btn.text}] => Callback: "${btn.callback_data}"`);
        });
      });
    }
    console.log('==============================================\n');
    return { ok: true, result: { message_id: `tg_mock_${Date.now()}` } };
  }

  try {
    const url = `https://api.telegram.org/bot${token}/${method}`;
    const response = await axios.post(url, {
      chat_id: chatId,
      ...payload
    });
    return response.data;
  } catch (error) {
    console.error('Error sending Telegram message:', error.response?.data || error.message);
    return { ok: false, error: error.message };
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export async function sendAlert(text) {
  const payload = {
    text: `🔔 <b>STRIKIT Alert</b>\n\n${escapeHtml(text)}`,
    parse_mode: 'HTML'
  };
  return sendTelegramRequest('sendMessage', payload);
}

export async function sendVerificationAlert(owner) {
  const text = `🆕 <b>New Owner Onboarding</b>\n\n` +
               `<b>Name:</b> ${escapeHtml(owner.name)}\n` +
               `<b>Phone:</b> ${escapeHtml(owner.mobile)}\n` +
               `<b>Turf:</b> ${escapeHtml(owner.turfName)}\n` +
               `<b>Location:</b> ${escapeHtml(owner.location)}\n` +
               `<b>Photos:</b> ${escapeHtml(owner.photoUrls)}\n` +
               `<b>GST:</b> ${escapeHtml(owner.gst || 'N/A')}\n` +
               `<b>MSME:</b> ${escapeHtml(owner.msme || 'N/A')}\n\n` +
               `Please verify details and action below:`;

  const payload = {
    text,
    parse_mode: 'HTML',
    reply_markup: {
      inline_keyboard: [
        [
          { text: '✅ Approve Owner', callback_data: `verify_approve_${owner.id}` },
          { text: '❌ Reject Owner', callback_data: `verify_reject_${owner.id}` }
        ]
      ]
    }
  };
  return sendTelegramRequest('sendMessage', payload);
}

export async function sendPlatformReport(pdfPath, caption) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    mockTelegramMessages.push({ document: pdfPath, caption });
    console.log(`\n=== [MOCK TELEGRAM DOCUMENT to ${chatId || 'Admin'}] ===`);
    console.log(`File: ${pdfPath}`);
    console.log(`Caption: ${caption}`);
    console.log('==============================================\n');
    return { ok: true };
  }

  try {
    const formData = new FormData();
    formData.append('chat_id', chatId);
    formData.append('caption', caption);
    formData.append('parse_mode', 'Markdown');
    
    const fileBuffer = fs.readFileSync(pdfPath);
    const fileName = path.basename(pdfPath);
    formData.append('document', new Blob([fileBuffer]), fileName);

    const url = `https://api.telegram.org/bot${token}/sendDocument`;
    const response = await axios.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error sending Telegram document:', error.response?.data || error.message);
    return { ok: false, error: error.message };
  }
}
