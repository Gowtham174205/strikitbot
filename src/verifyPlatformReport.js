import { triggerAndSendMonthlyReport } from './routes/telegramBot.js';
import { mockTelegramMessages, clearMockTelegramMessages } from './services/telegramService.js';
import fs from 'fs';
import path from 'path';

async function testReport() {
  console.log('🤖 Running Platform Report Generator Test...');

  // Force mock mode by clearing env tokens
  process.env.TELEGRAM_BOT_TOKEN = '';
  process.env.TELEGRAM_CHAT_ID = '';

  // 1. Clear previous mock messages
  clearMockTelegramMessages();

  // 2. Prepare mock data
  const mockOwner = {
    id: 1,
    name: 'Gowtham P',
    mobile: '919876543210',
    turfName: 'Strikers Turf',
    location: 'Chennai'
  };

  const mockBookings = [
    {
      id: 101,
      amountPaid: 1200,
      createdAt: new Date(),
      teamName: 'HawksFC',
      captainName: 'John',
      slot: {
        date: '2026-06-05',
        timeSlot: '06:00 PM',
        owner: mockOwner
      }
    },
    {
      id: 102,
      amountPaid: 1200,
      createdAt: new Date(),
      teamName: 'EaglesFC',
      captainName: 'Mike',
      slot: {
        date: '2026-06-05',
        timeSlot: '07:00 PM',
        owner: mockOwner
      }
    }
  ];

  const mockJoinRequests = [
    {
      id: 201,
      status: 'ACCEPTED',
      playerName: 'Giri',
      createdAt: new Date(),
      booking: {
        slot: {
          date: '2026-06-05',
          timeSlot: '06:00 PM',
          owner: mockOwner
        }
      }
    }
  ];

  // 3. Create mock Prisma client
  const mockPrisma = {
    botBooking: {
      findMany: async ({ where }) => {
        console.log(`   Mocking botBooking.findMany query with range: ${where.createdAt.gte.toISOString()} to ${where.createdAt.lte.toISOString()}`);
        return mockBookings;
      }
    },
    botJoinRequest: {
      findMany: async ({ where }) => {
        console.log(`   Mocking botJoinRequest.findMany query with status ${where.status} and range: ${where.createdAt.gte.toISOString()} to ${where.createdAt.lte.toISOString()}`);
        return mockJoinRequests;
      }
    }
  };

  try {
    // 4. Run the report generation
    console.log('🔄 Calling triggerAndSendMonthlyReport...');
    const result = await triggerAndSendMonthlyReport(mockPrisma, { previousMonth: false });

    console.log('✅ Result metadata:', result);
    
    // 5. Verify PDF file was created
    if (!fs.existsSync(result.pdfPath)) {
      throw new Error(`PDF report file was not created at: ${result.pdfPath}`);
    }
    console.log(`✅ PDF report file exists at: ${result.pdfPath} (Size: ${fs.statSync(result.pdfPath).size} bytes)`);

    // 6. Verify Telegram message was mocked / sent
    console.log('✅ Mock Telegram messages:', JSON.stringify(mockTelegramMessages, null, 2));
    if (mockTelegramMessages.length === 0) {
      throw new Error('No Telegram message was sent / mocked!');
    }

    const lastMsg = mockTelegramMessages[mockTelegramMessages.length - 1];
    if (!lastMsg.caption || !lastMsg.caption.includes('STRIKIT Platform Revenue Report')) {
      throw new Error('Telegram message caption does not match expected report caption!');
    }
    console.log('🎉 PLATFORM REPORT TEST PASSED SUCCESSFULLY!');
  } catch (err) {
    console.error('❌ Test Failed:', err);
    process.exit(1);
  }
}

testReport();
