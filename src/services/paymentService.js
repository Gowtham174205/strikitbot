import Razorpay from 'razorpay';

let razorpay = null;
if (process.env.RAZORPAY_KEY_ID && process.env.RAZORPAY_KEY_SECRET) {
  razorpay = new Razorpay({
    key_id: process.env.RAZORPAY_KEY_ID,
    key_secret: process.env.RAZORPAY_KEY_SECRET,
  });
}

/**
 * Create a payment link for owner subscription onboarding / renewal (₹699)
 */
export async function createSubscriptionLink(ownerId, amount = 699) {
  if (!razorpay) {
    console.log(`[PaymentService] Razorpay keys not set. Falling back to mock subscription URL for owner: ${ownerId}`);
    return `http://razorpay.mock/sub/${ownerId}`;
  }

  try {
    const paymentLink = await razorpay.paymentLink.create({
      amount: Math.round(amount * 100), // convert to paise
      currency: 'INR',
      accept_partial: false,
      description: `STRIKIT Turf Booking Bot Subscription (Owner ID: ${ownerId})`,
      notify: {
        sms: false,
        email: false
      },
      reminder_enable: false,
      notes: {
        type: 'subscription',
        ownerId: ownerId.toString()
      },
      callback_url: 'https://bot.strikit.in/payment-success',
      callback_method: 'get'
    });

    return paymentLink.short_url;
  } catch (err) {
    console.error(`[PaymentService] Error creating Razorpay subscription link for owner ${ownerId}:`, err);
    throw err;
  }
}

/**
 * Create a payment link for player slot booking
 */
export async function createBookingLink({ phone, ownerId, date, slotTime, captainName, teamName, amount }) {
  if (!razorpay) {
    console.log(`[PaymentService] Razorpay keys not set. Falling back to mock booking URL for slot: ${slotTime}`);
    return `http://razorpay.mock/pay?slot=${encodeURIComponent(slotTime)}&date=${encodeURIComponent(date)}&owner=${ownerId}&phone=${encodeURIComponent(phone)}&amount=${amount}`;
  }

  try {
    const paymentLink = await razorpay.paymentLink.create({
      amount: Math.round(amount * 100),
      currency: 'INR',
      accept_partial: false,
      description: `Turf Booking Fee for slot ${slotTime} on ${date}`,
      customer: {
        contact: phone.startsWith('+') ? phone : `+${phone}`
      },
      notify: {
        sms: false,
        email: false
      },
      reminder_enable: false,
      notes: {
        type: 'booking',
        phone: phone.toString(),
        ownerId: ownerId.toString(),
        date: date.toString(),
        slotTime: slotTime.toString(),
        captainName: captainName.toString(),
        teamName: teamName.toString(),
        amount: amount.toString()
      },
      callback_url: 'https://bot.strikit.in/payment-success',
      callback_method: 'get'
    });

    return paymentLink.short_url;
  } catch (err) {
    console.error(`[PaymentService] Error creating Razorpay booking link:`, err);
    throw err;
  }
}

/**
 * Create a payment link for player join request (₹9)
 */
export async function createJoinRequestLink(requestId, phone, amount = 9) {
  if (!razorpay) {
    console.log(`[PaymentService] Razorpay keys not set. Falling back to mock join request URL: ${requestId}`);
    return `http://razorpay.mock/joinpay?id=${requestId}&phone=${phone}`;
  }

  try {
    const paymentLink = await razorpay.paymentLink.create({
      amount: Math.round(amount * 100),
      currency: 'INR',
      accept_partial: false,
      description: `STRIKIT Player Join Request Platform Fee (Request ID: ${requestId})`,
      customer: {
        contact: phone.startsWith('+') ? phone : `+${phone}`
      },
      notify: {
        sms: false,
        email: false
      },
      reminder_enable: false,
      notes: {
        type: 'join_request',
        requestId: requestId.toString(),
        phone: phone.toString()
      },
      callback_url: 'https://bot.strikit.in/payment-success',
      callback_method: 'get'
    });

    return paymentLink.short_url;
  } catch (err) {
    console.error(`[PaymentService] Error creating Razorpay join request link:`, err);
    throw err;
  }
}
