import express from 'express';
import dotenv from 'dotenv';
import { PrismaClient } from '@prisma/client';
import adminRouter from './routes/admin.js';
import axios from 'axios';

dotenv.config();

const app = express();
app.use(express.json());
const prisma = new PrismaClient();
app.set('prisma', prisma);
app.use('/api/admin', adminRouter);

const PORT = 5002;
const BASE_URL = `http://localhost:${PORT}/api/admin`;
const ADMIN_KEY = process.env.ADMIN_API_KEY || 'STRIKIT_ADMIN_SECRET';

let server;

async function runTests() {
  console.log('--- Starting Admin API Automated Verification Flow ---');
  
  // 1. Start test server
  server = app.listen(PORT, async () => {
    console.log(`Test server running on port ${PORT}`);
    
    try {
      // 2. Test Authorization
      console.log('\n[Test 1] Testing Authorization...');
      try {
        await axios.get(`${BASE_URL}/owners`);
        console.error('FAIL: Allowed request without x-admin-key');
        process.exit(1);
      } catch (err) {
        if (err.response && err.response.status === 401) {
          console.log('SUCCESS: Blocked request without x-admin-key (401)');
        } else {
          console.error('FAIL: Unexpected response for missing key', err.message);
          process.exit(1);
        }
      }

      try {
        await axios.get(`${BASE_URL}/owners`, {
          headers: { 'x-admin-key': 'INVALID_KEY' }
        });
        console.error('FAIL: Allowed request with invalid key');
        process.exit(1);
      } catch (err) {
        if (err.response && err.response.status === 401) {
          console.log('SUCCESS: Blocked request with invalid key (401)');
        } else {
          console.error('FAIL: Unexpected response for invalid key', err.message);
          process.exit(1);
        }
      }

      // 3. Create dummy owner for testing
      console.log('\n[Test 2] Creating dummy owner directly in DB...');
      const uniqueSuffix = Date.now().toString().slice(-6);
      const testMobile = `9199999${uniqueSuffix}`;
      const testBusinessMobile = `9188888${uniqueSuffix}`;
      
      const dummyOwner = await prisma.botOwner.create({
        data: {
          name: 'Test Owner Name',
          mobile: testMobile,
          turfName: 'Super Arena Turf',
          location: 'https://maps.google.com/test',
          photoUrls: 'https://test.com/photo.jpg',
          gst: '33AAAAA0000A1Z1',
          msme: 'UDYAM-TN-01-0000001',
          verified: false,
          subscriptionActive: false,
          businessPhone: testBusinessMobile
        }
      });
      console.log(`SUCCESS: Created test owner ID ${dummyOwner.id}`);

      // 4. Test Listing & Search
      console.log('\n[Test 3] Testing GET /owners and search...');
      const listRes = await axios.get(`${BASE_URL}/owners`, {
        headers: { 'x-admin-key': ADMIN_KEY }
      });
      
      const foundInList = listRes.data.some(o => o.id === dummyOwner.id);
      if (foundInList) {
        console.log('SUCCESS: Found newly created owner in total list');
      } else {
        console.error('FAIL: Owner not found in list');
        process.exit(1);
      }

      // Search by turf name
      const searchRes1 = await axios.get(`${BASE_URL}/owners?search=Super Arena`, {
        headers: { 'x-admin-key': ADMIN_KEY }
      });
      if (searchRes1.data.some(o => o.id === dummyOwner.id)) {
        console.log('SUCCESS: Found owner when searching by turf name');
      } else {
        console.error('FAIL: Owner not found when searching by turf name');
        process.exit(1);
      }

      // Search by phone
      const searchRes2 = await axios.get(`${BASE_URL}/owners?search=${testMobile}`, {
        headers: { 'x-admin-key': ADMIN_KEY }
      });
      if (searchRes2.data.some(o => o.id === dummyOwner.id)) {
        console.log('SUCCESS: Found owner when searching by mobile');
      } else {
        console.error('FAIL: Owner not found when searching by mobile');
        process.exit(1);
      }

      // 5. Test Approval
      console.log('\n[Test 4] Testing POST /owners/:id/approve...');
      const approveRes = await axios.post(`${BASE_URL}/owners/${dummyOwner.id}/approve`, {}, {
        headers: { 'x-admin-key': ADMIN_KEY }
      });
      console.log('Approval response:', approveRes.data.message);

      // Verify db changes
      const approvedOwner = await prisma.botOwner.findUnique({
        where: { id: dummyOwner.id }
      });
      if (approvedOwner.verified && approvedOwner.subscriptionActive && approvedOwner.subscriptionExpiry) {
        console.log('SUCCESS: DB fields updated correctly (verified=true, subscriptionActive=true)');
        const daysDiff = (new Date(approvedOwner.subscriptionExpiry) - new Date()) / (1000 * 60 * 60 * 24);
        console.log(`Subscription trial expiry set to: ${approvedOwner.subscriptionExpiry} (~${daysDiff.toFixed(1)} days from now)`);
      } else {
        console.error('FAIL: DB fields not updated correctly on approval', approvedOwner);
        process.exit(1);
      }

      // Verify onboarding session created/updated
      const session = await prisma.botSession.findUnique({
        where: { phone: testMobile }
      });
      if (session && session.role === 'ONBOARDING' && session.state === 'AWAITING_BUSINESS_CONNECT') {
        console.log('SUCCESS: Onboarding session created/updated with correct state');
      } else {
        console.error('FAIL: Onboarding session not correctly set', session);
        process.exit(1);
      }

      // 6. Test Rejection / Deactivation
      console.log('\n[Test 5] Testing POST /owners/:id/reject...');
      const rejectRes = await axios.post(`${BASE_URL}/owners/${dummyOwner.id}/reject`, {}, {
        headers: { 'x-admin-key': ADMIN_KEY }
      });
      console.log('Rejection response:', rejectRes.data.message);

      const rejectedOwner = await prisma.botOwner.findUnique({
        where: { id: dummyOwner.id }
      });
      if (!rejectedOwner.verified && !rejectedOwner.subscriptionActive && rejectedOwner.subscriptionExpiry === null) {
        console.log('SUCCESS: DB fields updated correctly (verified=false, subscriptionActive=false, expiry=null)');
      } else {
        console.error('FAIL: DB fields not updated correctly on rejection', rejectedOwner);
        process.exit(1);
      }

      const sessionAfterReject = await prisma.botSession.findUnique({
        where: { phone: testMobile }
      });
      if (!sessionAfterReject) {
        console.log('SUCCESS: Onboarding session deleted on rejection');
      } else {
        console.error('FAIL: Onboarding session still exists after rejection', sessionAfterReject);
        process.exit(1);
      }

      // 7. Test Cascading Deletion
      console.log('\n[Test 6] Testing DELETE /owners/:id with cascading records...');
      // Re-approve to get a session
      await axios.post(`${BASE_URL}/owners/${dummyOwner.id}/approve`, {}, { headers: { 'x-admin-key': ADMIN_KEY } });
      
      // Also add a session for the businessPhone
      await prisma.botSession.create({
        data: {
          phone: testBusinessMobile,
          role: 'OWNER',
          state: 'DASHBOARD'
        }
      });
      
      // Create a slot
      const slot = await prisma.botTurfSlot.create({
        data: {
          ownerId: dummyOwner.id,
          date: '2026-07-01',
          timeSlot: '06:00 PM',
          status: 'AVAILABLE'
        }
      });
      console.log(`Created slot ID: ${slot.id}`);

      // Create a booking
      const booking = await prisma.botBooking.create({
        data: {
          slotId: slot.id,
          teamName: 'Fighters FC',
          captainName: 'Gowtham',
          captainPhone: '919000000001',
          amountPaid: 1000.0
        }
      });
      console.log(`Created booking ID: ${booking.id}`);

      // Create a join request
      const joinRequest = await prisma.botJoinRequest.create({
        data: {
          bookingId: booking.id,
          playerName: 'Dinesh',
          playerPhone: '919000000002',
          status: 'PENDING'
        }
      });
      console.log(`Created join request ID: ${joinRequest.id}`);

      // Perform DELETE request
      const deleteRes = await axios.delete(`${BASE_URL}/owners/${dummyOwner.id}`, {
        headers: { 'x-admin-key': ADMIN_KEY }
      });
      console.log('Delete response:', deleteRes.data.message);

      // Verify all cascading items are deleted from database
      const deletedOwner = await prisma.botOwner.findUnique({ where: { id: dummyOwner.id } });
      const deletedSlot = await prisma.botTurfSlot.findUnique({ where: { id: slot.id } });
      const deletedBooking = await prisma.botBooking.findUnique({ where: { id: booking.id } });
      const deletedJoinRequest = await prisma.botJoinRequest.findUnique({ where: { id: joinRequest.id } });
      const deletedSession1 = await prisma.botSession.findUnique({ where: { phone: testMobile } });
      const deletedSession2 = await prisma.botSession.findUnique({ where: { phone: testBusinessMobile } });

      let cascadeSuccess = true;
      if (deletedOwner) { console.error('FAIL: BotOwner still exists'); cascadeSuccess = false; }
      if (deletedSlot) { console.error('FAIL: BotTurfSlot still exists'); cascadeSuccess = false; }
      if (deletedBooking) { console.error('FAIL: BotBooking still exists'); cascadeSuccess = false; }
      if (deletedJoinRequest) { console.error('FAIL: BotJoinRequest still exists'); cascadeSuccess = false; }
      if (deletedSession1) { console.error('FAIL: BotSession (owner mobile) still exists'); cascadeSuccess = false; }
      if (deletedSession2) { console.error('FAIL: BotSession (business mobile) still exists'); cascadeSuccess = false; }

      if (cascadeSuccess) {
        console.log('SUCCESS: All cascading records (owner, slots, bookings, join requests, sessions) completely purged!');
      } else {
        console.error('FAIL: Cascading deletion did not clean up all related records.');
        process.exit(1);
      }

      console.log('\n--- ALL ADMIN API TESTS PASSED SUCCESSFULLY! ---');
      cleanupAndExit(0);
    } catch (error) {
      console.error('\nFAIL: Error occurred during test run:', error.message);
      if (error.response) {
        console.error('API Error Response Data:', error.response.data);
      }
      cleanupAndExit(1);
    }
  });
}

function cleanupAndExit(code) {
  prisma.$disconnect();
  server.close(() => {
    console.log('Test server closed.');
    process.exit(code);
  });
}

runTests();
