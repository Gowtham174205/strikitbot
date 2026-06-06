import express from 'express';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import { PrismaClient } from '@prisma/client';
import { handleWhatsAppWebhook } from './routes/whatsappBot.js';
import { handleTelegramWebhook, triggerAndSendMonthlyReport } from './routes/telegramBot.js';
import razorpayRouter from './routes/razorpay.js';
import adminRouter from './routes/admin.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;
const prisma = new PrismaClient();

app.set('prisma', prisma);
app.use(express.json());

// Create reports folder if not exists
const reportsDir = path.resolve('reports');
if (!fs.existsSync(reportsDir)) {
  fs.mkdirSync(reportsDir, { recursive: true });
}

// Serve generated PDF reports
app.use('/reports', express.static(reportsDir));

/**
 * WhatsApp Webhook: Token verification challenge for Meta Developer Setup (GET)
 */
app.get('/webhook/whatsapp', (req, res) => {
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];

  const VERIFY_TOKEN = process.env.WHATSAPP_VERIFY_TOKEN || 'STRIKIT_TOKEN';

  if (mode === 'subscribe' && token === VERIFY_TOKEN) {
    console.log('WhatsApp Webhook Verified.');
    res.status(200).send(challenge);
  } else {
    res.sendStatus(403);
  }
});

/**
 * WhatsApp Webhook: Receives message payloads from Meta servers (POST)
 */
app.post('/webhook/whatsapp', async (req, res) => {
  try {
    const entry = req.body.entry?.[0];
    const change = entry?.changes?.[0];
    const value = change?.value;
    
    if (value && value.messages) {
      const message = value.messages[0];
      const from = message.from; // sender phone number
      const to = value.metadata?.phone_number_id || value.metadata?.display_phone_number || process.env.ONBOARDING_NUMBER; // receiver number
      
      // Parse message text, list reply, button reply, image, or document
      let text = '';
      let mediaId = '';
      let mediaType = '';
      
      if (message.type === 'text') {
        text = message.text.body;
      } else if (message.type === 'interactive') {
        const interactive = message.interactive;
        if (interactive.type === 'button_reply') {
          text = interactive.button_reply.id;
        } else if (interactive.type === 'list_reply') {
          text = interactive.list_reply.id;
        }
      } else if (message.type === 'image') {
        mediaId = message.image.id;
        mediaType = 'image';
        text = message.image.caption || '';
      } else if (message.type === 'document') {
        mediaId = message.document.id;
        mediaType = 'document';
        text = message.document.caption || '';
      }

      console.log(`[WhatsApp Webhook Received] From: ${from} -> To: ${to} | Text: "${text}" | Media: ${mediaType} (${mediaId})`);
      await handleWhatsAppWebhook(from, to, text, prisma, mediaId, mediaType);
    }
    
    res.sendStatus(200);
  } catch (error) {
    console.error('WhatsApp Webhook Handler Error:', error.message);
    res.sendStatus(500);
  }
});

/**
 * Telegram Webhook Endpoint
 */
app.post('/webhook/telegram', async (req, res) => {
  try {
    await handleTelegramWebhook(req, res, prisma);
  } catch (error) {
    console.error('Telegram Webhook Handler Error:', error.message);
    res.sendStatus(500);
  }
});

// Mount Razorpay simulator router
app.use('/razorpay', razorpayRouter);

// Mount Admin API router
app.use('/api/admin', adminRouter);

app.get('/status', (req, res) => {
  res.json({ status: 'active', time: new Date() });
});

function startMonthlyReportScheduler(prisma) {
  const checkReport = async () => {
    try {
      const now = new Date();
      // We trigger the report for the previous month when we are in the next month.
      const prevMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const year = prevMonthDate.getFullYear();
      const month = String(prevMonthDate.getMonth() + 1).padStart(2, '0');
      const targetMonthStr = `${year}-${month}`; // e.g. "2026-05"

      const markerPath = path.resolve('reports', '.last_sent_monthly_report.txt');
      let lastSent = '';
      if (fs.existsSync(markerPath)) {
        lastSent = fs.readFileSync(markerPath, 'utf8').trim();
      }

      // If we haven't sent the report for the previous month yet
      if (lastSent !== targetMonthStr) {
        console.log(`[Scheduler] Generating and sending monthly platform report for ${targetMonthStr}...`);
        await triggerAndSendMonthlyReport(prisma, { previousMonth: true });
        fs.writeFileSync(markerPath, targetMonthStr, 'utf8');
        console.log(`[Scheduler] Monthly report for ${targetMonthStr} sent and marked.`);
      }
    } catch (err) {
      console.error('[Scheduler] Error in monthly report check:', err);
    }
  };

  // Run check on startup (wait 5s for server binding)
  setTimeout(checkReport, 5000);
  
  // Check every 1 hour
  setInterval(checkReport, 60 * 60 * 1000);
}

// Start the scheduler
startMonthlyReportScheduler(prisma);

app.listen(PORT, () => {
  console.log(`STRIKIT Bot Server listening on port ${PORT}`);
});
