import { PrismaClient } from '@prisma/client';
import { handleWhatsAppWebhook } from './routes/whatsappBot.js';
import { sendDeveloperVerificationAlert, mockSentMessages, clearMockMessages } from './services/whatsappService.js';

const prisma = new PrismaClient();
const DEVELOPER_NUMBER = '919876543210';
const ONBOARDING_NUMBER = '919000000000';

async function testDevFlow() {
  console.log('🤖 Running Developer WhatsApp Approvals & Rejections Verification...');

  try {
    // 1. Clean Bot Session & Owner data
    console.log('🧹 Wiping tables for clean test context...');
    await prisma.botJoinRequest.deleteMany();
    await prisma.botBooking.deleteMany();
    await prisma.botTurfSlot.deleteMany();
    await prisma.botSession.deleteMany();
    await prisma.botOwner.deleteMany();

    // 2. Create an owner awaiting verification
    const owner = await prisma.botOwner.create({
      data: {
        name: 'Gowtham P',
        mobile: '919555555555',
        turfName: 'Super Turf',
        location: 'https://maps.google.com/?q=Chennai',
        photoUrls: 'http://drive.link/photos',
        gst: '33AAAAA1111A1Z1',
        msme: 'UDYAM-TN-01-0123456',
        openingTime: '06:00 AM',
        closingTime: '10:00 PM',
        pricePerHour: 1200
      }
    });

    console.log(`✅ Test Owner created with ID: ${owner.id}`);

    // 3. Trigger Developer Verification Alert via WhatsApp
    console.log('📢 Dispatching Developer Verification Alert to all DEVELOPER_NUMBERS...');
    clearMockMessages();
    await sendDeveloperVerificationAlert(owner);

    // Verify mock WhatsApp messages contains the alert
    const alertMsg = mockSentMessages.find(m => m.to === DEVELOPER_NUMBER);
    if (!alertMsg) {
      throw new Error(`Failed to receive developer alert on ${DEVELOPER_NUMBER}`);
    }
    console.log('✅ Developer alert successfully received via WhatsApp!');
    if (!alertMsg.text.body.includes(`/approve ${owner.id}`)) {
      throw new Error('Alert message does not contain the /approve command recommendation');
    }
    console.log('✅ Alert contains instructions with ID:', owner.id);

    // 4. Simulate Developer sends `/approve [id]` via WhatsApp
    console.log(`💬 Simulating Developer sends "/approve ${owner.id}" to Onboarding bot...`);
    clearMockMessages();
    await handleWhatsAppWebhook(DEVELOPER_NUMBER, ONBOARDING_NUMBER, `/approve ${owner.id}`, prisma);

    // Check if the developer got approval confirmation
    const devConfirm = mockSentMessages.find(m => m.to === DEVELOPER_NUMBER);
    if (!devConfirm || !devConfirm.text.body.includes('approved successfully')) {
      throw new Error('Developer did not receive approval confirmation message!');
    }
    console.log('✅ Developer received approval confirmation!');

    // Check if the owner got activation welcome message
    const ownerWelcome = mockSentMessages.find(m => m.to === owner.mobile);
    if (!ownerWelcome || !ownerWelcome.text.body.includes('APPROVED')) {
      throw new Error('Owner did not receive Registration Approved activation alert!');
    }
    console.log('✅ Owner received Welcome to STRIKIT alert!');

    // Verify Owner is marked as verified in DB
    const verifiedOwner = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (!verifiedOwner.verified || !verifiedOwner.subscriptionActive) {
      throw new Error('Owner database record is not marked as verified/active!');
    }
    console.log('✅ Owner successfully marked as verified and active in database!');

    // 5. Test Rejection command
    console.log(`💬 Simulating Developer sends "/reject ${owner.id}"...`);
    clearMockMessages();
    await handleWhatsAppWebhook(DEVELOPER_NUMBER, ONBOARDING_NUMBER, `/reject ${owner.id}`, prisma);

    // Check if developer got rejection confirmation
    const devRejectConfirm = mockSentMessages.find(m => m.to === DEVELOPER_NUMBER);
    if (!devRejectConfirm || !devRejectConfirm.text.body.includes('rejected')) {
      throw new Error('Developer did not receive rejection confirmation message!');
    }
    console.log('✅ Developer received rejection confirmation!');

    // Check if owner got rejection notification
    const ownerRejectMsg = mockSentMessages.find(m => m.to === owner.mobile);
    if (!ownerRejectMsg || !ownerRejectMsg.text.body.includes('rejected')) {
      throw new Error('Owner did not receive rejection WhatsApp alert!');
    }
    console.log('✅ Owner received rejection alert!');

    // Verify Owner is marked as unverified in DB
    const rejectedOwner = await prisma.botOwner.findUnique({ where: { id: owner.id } });
    if (rejectedOwner.verified || rejectedOwner.subscriptionActive) {
      throw new Error('Owner database record is still marked as verified/active after rejection!');
    }
    console.log('✅ Owner successfully marked as unverified and inactive in database!');

    console.log('🎉 ALL WHATSAPP DEVELOPER APPROVAL/REJECTION COMMAND FLOWS PASSED SUCCESSFULLY!');
  } catch (err) {
    console.error('❌ Test Failed:', err);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
    process.exit(0);
  }
}

testDevFlow();
