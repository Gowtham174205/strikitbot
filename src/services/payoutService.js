import axios from 'axios';
import dotenv from 'dotenv';
dotenv.config();

const KEY_ID = process.env.RAZORPAY_KEY_ID;
const KEY_SECRET = process.env.RAZORPAY_KEY_SECRET;
const ACCOUNT_NUMBER = process.env.RAZORPAYX_ACCOUNT_NUMBER;

const isConfigured = !!(KEY_ID && KEY_SECRET && ACCOUNT_NUMBER);

// Base64 basic auth string
const authHeader = isConfigured
  ? `Basic ${Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString('base64')}`
  : '';

/**
 * Creates a contact in RazorpayX
 */
export async function createContact({ name, mobile, referenceId }) {
  if (!isConfigured) {
    console.log(`[PayoutService] RazorpayX not fully configured. Simulating Contact creation for: ${name}`);
    return `cont_mock_${Math.random().toString(36).substring(2, 10)}`;
  }

  try {
    const response = await axios.post(
      'https://api.razorpay.com/v1/contacts',
      {
        name,
        contact: mobile.replace(/[^0-9]/g, '').slice(-10), // Take last 10 digits
        type: 'vendor',
        reference_id: referenceId.toString()
      },
      {
        headers: {
          Authorization: authHeader,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data.id;
  } catch (err) {
    console.error('[PayoutService] Error creating RazorpayX Contact:', err.response?.data || err.message);
    throw err;
  }
}

/**
 * Creates a VPA (UPI) Fund Account in RazorpayX
 */
export async function createFundAccount(contactId, upiId) {
  if (!isConfigured) {
    console.log(`[PayoutService] RazorpayX not fully configured. Simulating Fund Account creation for: ${upiId}`);
    return `fa_mock_${Math.random().toString(36).substring(2, 10)}`;
  }

  try {
    const response = await axios.post(
      'https://api.razorpay.com/v1/fund_accounts',
      {
        contact_id: contactId,
        account_type: 'vpa',
        vpa: {
          address: upiId.trim()
        }
      },
      {
        headers: {
          Authorization: authHeader,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data.id;
  } catch (err) {
    console.error('[PayoutService] Error creating RazorpayX Fund Account:', err.response?.data || err.message);
    throw err;
  }
}

/**
 * Executes a Payout to an owner's UPI ID (VPA) using RazorpayX
 */
export async function executePayout({ owner, amount, bookingId }) {
  console.log(`[PayoutService] Initiating split payout of ₹${amount} for owner ${owner.name} (UPI: ${owner.upiId})`);

  if (!isConfigured) {
    console.log(`[PayoutService] RazorpayX not fully configured (missing KEY_ID, KEY_SECRET, or RAZORPAYX_ACCOUNT_NUMBER).`);
    console.log(`[SIMULATION SUCCESS] Simulated payout of ₹${amount} to UPI: ${owner.upiId}`);
    return {
      payoutId: `pout_mock_${Math.random().toString(36).substring(2, 10)}`,
      status: 'processed',
      simulated: true
    };
  }

  const prisma = owner.prisma; // If passed, to update cache in the DB

  try {
    let contactId = owner.razorpayContactId;
    let fundAccountId = owner.razorpayFundAccountId;

    // 1. Create and cache Contact ID if not present
    if (!contactId) {
      console.log(`[PayoutService] Contact ID not cached for owner ${owner.id}. Creating new...`);
      contactId = await createContact({
        name: owner.name,
        mobile: owner.mobile,
        referenceId: `owner_${owner.id}`
      });

      if (prisma) {
        await prisma.botOwner.update({
          where: { id: owner.id },
          data: { razorpayContactId: contactId }
        });
      }
    }

    // 2. Create and cache Fund Account ID if not present
    if (!fundAccountId) {
      console.log(`[PayoutService] Fund Account ID not cached for owner ${owner.id}. Creating new...`);
      fundAccountId = await createFundAccount(contactId, owner.upiId);

      if (prisma) {
        await prisma.botOwner.update({
          where: { id: owner.id },
          data: { razorpayFundAccountId: fundAccountId }
        });
      }
    }

    // 3. Trigger the RazorpayX Payout
    const response = await axios.post(
      'https://api.razorpay.com/v1/payouts',
      {
        account_number: ACCOUNT_NUMBER,
        fund_account_id: fundAccountId,
        amount: Math.round(amount * 100), // convert to paise
        currency: 'INR',
        mode: 'UPI',
        purpose: 'vendor bill',
        queue_if_low_balance: true,
        reference_id: `booking_${bookingId}`
      },
      {
        headers: {
          Authorization: authHeader,
          'Content-Type': 'application/json'
        }
      }
    );

    console.log(`[PayoutService] Payout successful. Payout ID: ${response.data.id}, Status: ${response.data.status}`);

    return {
      payoutId: response.data.id,
      status: response.data.status,
      simulated: false
    };
  } catch (err) {
    console.error('[PayoutService] Error executing RazorpayX Payout:', err.response?.data || err.message);
    throw err;
  }
}
