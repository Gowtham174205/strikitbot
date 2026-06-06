import axios from 'axios';
import dotenv from 'dotenv';
dotenv.config();

// Temporary memory store for testing/simulating sent WhatsApp messages in local environment
export const mockSentMessages = [];

export function getMockMessages() {
  return mockSentMessages;
}

export function clearMockMessages() {
  mockSentMessages.length = 0;
}

const WHATSAPP_API_URL = 'https://graph.facebook.com/v19.0';
const PHONE_NUMBER_ID = process.env.WHATSAPP_PHONE_NUMBER_ID;
const ACCESS_TOKEN = process.env.WHATSAPP_ACCESS_TOKEN;

async function sendWhatsAppRequest(payload) {
  // If not configured, print mock output
  if (!ACCESS_TOKEN || !PHONE_NUMBER_ID) {
    mockSentMessages.push(payload);
    console.log(`\n--- [MOCK WHATSAPP OUTGOING to ${payload.to}] ---`);
    if (payload.type === 'text') {
      console.log(payload.text.body);
    } else if (payload.type === 'interactive') {
      const interactive = payload.interactive;
      console.log(`${interactive.body?.text || 'Interactive Message:'}`);
      if (interactive.type === 'button') {
        console.log(`Buttons: [${interactive.action.buttons.map(b => b.reply.title).join(']  [')}]`);
      } else if (interactive.type === 'list') {
        console.log(`List Menu Button: "${interactive.action.button}"`);
        interactive.action.sections.forEach(sec => {
          console.log(` * Section: ${sec.title || 'Options'}`);
          sec.rows.forEach(r => console.log(`   - [ID: ${r.id}] ${r.title}: ${r.description || ''}`));
        });
      }
    } else if (payload.type === 'document') {
      console.log(`Attachment [PDF Document]: ${payload.document.filename} (Link: ${payload.document.link})`);
      if (payload.document.caption) console.log(`Caption: ${payload.document.caption}`);
    }
    console.log('-------------------------------------------------\n');
    return { data: { messaging_product: 'whatsapp', contacts: [{ input: payload.to, wa_id: payload.to }], messages: [{ id: `wamid.mock_${Date.now()}` }] } };
  }

  try {
    const response = await axios.post(
      `${WHATSAPP_API_URL}/${PHONE_NUMBER_ID}/messages`,
      payload,
      {
        headers: {
          'Authorization': `Bearer ${ACCESS_TOKEN}`,
          'Content-Type': 'application/json'
        }
      }
    );
    return response.data;
  } catch (error) {
    console.error('Error sending WhatsApp message:', error.response?.data || error.message);
    throw error;
  }
}

export async function sendText(to, text) {
  const payload = {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to,
    type: 'text',
    text: { body: text }
  };
  return sendWhatsAppRequest(payload);
}

export async function sendButtons(to, text, buttons) {
  // Format buttons to Meta Cloud API format
  // buttons: [{ id: 'btn_1', title: 'Option 1' }, ...] (Max 3 buttons)
  const formattedButtons = buttons.slice(0, 3).map(btn => ({
    type: 'reply',
    reply: {
      id: btn.id,
      title: btn.title.substring(0, 20) // Meta limit: 20 chars
    }
  }));

  const payload = {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to,
    type: 'interactive',
    interactive: {
      type: 'button',
      body: { text },
      action: {
        buttons: formattedButtons
      }
    }
  };
  return sendWhatsAppRequest(payload);
}

export async function sendList(to, text, buttonText, sections) {
  // Meta Cloud API interactive list format
  // sections: [{ title: 'Sec 1', rows: [{ id: 'r1', title: 'Row 1', description: 'Desc 1' }] }]
  const payload = {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to,
    type: 'interactive',
    interactive: {
      type: 'list',
      body: { text },
      action: {
        button: buttonText.substring(0, 20), // Meta limit: 20 chars
        sections: sections
      }
    }
  };
  return sendWhatsAppRequest(payload);
}

export async function sendDocument(to, fileUrl, filename, caption = '') {
  const payload = {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to,
    type: 'document',
    document: {
      link: fileUrl,
      filename,
      caption
    }
  };
  return sendWhatsAppRequest(payload);
}

export async function sendDeveloperVerificationAlert(owner) {
  const devNumbersStr = process.env.DEVELOPER_NUMBERS || '';
  const developerNumbers = devNumbersStr.split(',').map(n => n.trim()).filter(Boolean);

  if (developerNumbers.length === 0) {
    console.log(`[Developer Notification] No developer numbers configured in env.`);
    return;
  }

  const text = `🆕 *New Owner Onboarding Request* 🆕\n\n` +
               `• *ID:* ${owner.id}\n` +
               `• *Name:* ${owner.name}\n` +
               `• *Phone:* ${owner.mobile}\n` +
               `• *Turf:* ${owner.turfName}\n` +
               `• *Location:* ${owner.location}\n` +
               `• *Photos:* ${owner.photoUrls}\n` +
               `• *GST:* ${owner.gst || 'N/A'}\n` +
               `• *MSME:* ${owner.msme || 'N/A'}\n\n` +
               `*Action Commands:*\n` +
               `👉 To approve: reply with \`/approve ${owner.id}\`\n` +
               `👉 To reject: reply with \`/reject ${owner.id}\`\n\n` +
               `_Powered by STRIKIT_`;

  for (const phone of developerNumbers) {
    try {
      console.log(`[Developer Alert] Forwarding onboarding request for owner ${owner.id} to developer: ${phone}`);
      await sendText(phone, text);
    } catch (err) {
      console.error(`Failed to send developer alert to ${phone}:`, err.message);
    }
  }
}
