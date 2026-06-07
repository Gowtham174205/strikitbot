import crypto from 'crypto';

// ---------------------------------------------------------------------------
// 1. SECURITY RESPONSE HEADERS
//    Call applySecurityHeaders(app) once in server.js before any routes.
// ---------------------------------------------------------------------------
export function applySecurityHeaders(app) {
  app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('X-XSS-Protection', '1; mode=block');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader(
      'Permissions-Policy',
      'geolocation=(), camera=(), microphone=()'
    );
    // Remove fingerprinting header
    res.removeHeader('X-Powered-By');
    next();
  });
}

// ---------------------------------------------------------------------------
// 2. ADMIN API KEY VERIFICATION (timing-safe)
//    Replaces the inline verifyAdminApiKey in admin.js and razorpay.js.
//    Hard-fails if ADMIN_API_KEY env var is not configured — no fallback.
// ---------------------------------------------------------------------------
export function requireAdminKey(req, res, next) {
  const configuredKey = process.env.ADMIN_API_KEY;

  if (!configuredKey) {
    console.error(
      '[SECURITY] ADMIN_API_KEY is not set in environment. Refusing all admin requests.'
    );
    return res.status(503).json({ error: 'Server misconfiguration. Contact administrator.' });
  }

  const providedKey = req.headers['x-admin-key'] || '';

  // Timing-safe comparison prevents brute-force timing attacks
  let keysMatch = false;
  try {
    const a = Buffer.from(configuredKey, 'utf8');
    const b = Buffer.from(providedKey, 'utf8');
    if (a.length === b.length) {
      keysMatch = crypto.timingSafeEqual(a, b);
    }
  } catch {
    keysMatch = false;
  }

  if (!keysMatch) {
    return res.status(401).json({ error: 'Unauthorized: Invalid or missing Admin API Key' });
  }

  next();
}

// ---------------------------------------------------------------------------
// 3. WHATSAPP WEBHOOK SIGNATURE VERIFICATION
//    Meta sends an X-Hub-Signature-256 header on every POST.
//    We verify it using your Meta App Secret (WHATSAPP_APP_SECRET).
//
//    IMPORTANT: This middleware must run BEFORE express.json() parses the body,
//    so it relies on the raw Buffer stored in req.rawBody by server.js.
// ---------------------------------------------------------------------------
export function verifyWhatsAppSignature(req, res, next) {
  const appSecret = process.env.WHATSAPP_APP_SECRET;

  // If secret is not configured (e.g. local dev without Meta credentials),
  // skip signature check but log a warning.
  if (!appSecret) {
    console.warn(
      '[SECURITY WARNING] WHATSAPP_APP_SECRET not set — skipping webhook signature verification. ' +
      'Set this in production!'
    );
    return next();
  }

  const sigHeader = req.headers['x-hub-signature-256'];
  if (!sigHeader) {
    console.warn('[SECURITY] WhatsApp webhook received with no signature header — rejected.');
    return res.status(403).json({ error: 'Forbidden: Missing webhook signature' });
  }

  const rawBody = req.rawBody; // set by the rawBodyCapture middleware in server.js
  if (!rawBody) {
    console.error('[SECURITY] rawBody not available for signature check.');
    return res.status(400).json({ error: 'Bad Request' });
  }

  const expectedSig =
    'sha256=' +
    crypto.createHmac('sha256', appSecret).update(rawBody).digest('hex');

  let sigMatch = false;
  try {
    const a = Buffer.from(expectedSig, 'utf8');
    const b = Buffer.from(sigHeader, 'utf8');
    if (a.length === b.length) {
      sigMatch = crypto.timingSafeEqual(a, b);
    }
  } catch {
    sigMatch = false;
  }

  if (!sigMatch) {
    console.warn('[SECURITY] WhatsApp webhook signature mismatch — request rejected.');
    return res.status(403).json({ error: 'Forbidden: Invalid webhook signature' });
  }

  next();
}

// ---------------------------------------------------------------------------
// 4. TELEGRAM WEBHOOK SECRET TOKEN VERIFICATION
//    Telegram sends X-Telegram-Bot-Api-Secret-Token when you set a secret
//    token via setWebhook. Configure TELEGRAM_WEBHOOK_SECRET in your .env.
// ---------------------------------------------------------------------------
export function verifyTelegramToken(req, res, next) {
  const expectedToken = process.env.TELEGRAM_WEBHOOK_SECRET;

  // If not configured, skip (warn in dev, enforce in production)
  if (!expectedToken) {
    if (process.env.NODE_ENV === 'production') {
      console.error(
        '[SECURITY] TELEGRAM_WEBHOOK_SECRET not set in production — rejecting Telegram webhook.'
      );
      return res.status(403).json({ error: 'Forbidden: Telegram webhook not secured' });
    }
    console.warn(
      '[SECURITY WARNING] TELEGRAM_WEBHOOK_SECRET not set — skipping Telegram webhook verification.'
    );
    return next();
  }

  const providedToken = req.headers['x-telegram-bot-api-secret-token'] || '';

  let tokensMatch = false;
  try {
    const a = Buffer.from(expectedToken, 'utf8');
    const b = Buffer.from(providedToken, 'utf8');
    if (a.length === b.length) {
      tokensMatch = crypto.timingSafeEqual(a, b);
    }
  } catch {
    tokensMatch = false;
  }

  if (!tokensMatch) {
    console.warn('[SECURITY] Telegram webhook token mismatch — request rejected.');
    return res.status(403).json({ error: 'Forbidden: Invalid Telegram webhook token' });
  }

  next();
}

// ---------------------------------------------------------------------------
// 5. REPORT FILE AUTHENTICATION
//    Protects express.static '/reports' directory — requires admin key.
// ---------------------------------------------------------------------------
export function requireAdminKeyForReports(req, res, next) {
  const configuredKey = process.env.ADMIN_API_KEY;
  const providedKey =
    req.headers['x-admin-key'] ||
    req.query['admin_key'] || // allow ?admin_key= in URL for direct browser access
    '';

  if (!configuredKey) {
    return res.status(503).json({ error: 'Server misconfiguration.' });
  }

  let keysMatch = false;
  try {
    const a = Buffer.from(configuredKey, 'utf8');
    const b = Buffer.from(providedKey, 'utf8');
    if (a.length === b.length) {
      keysMatch = crypto.timingSafeEqual(a, b);
    }
  } catch {
    keysMatch = false;
  }

  if (!keysMatch) {
    return res.status(401).json({ error: 'Unauthorized: Admin key required to access reports' });
  }

  next();
}

// ---------------------------------------------------------------------------
// 6. INPUT SANITIZER
//    Trims whitespace and caps string length to prevent oversized DB writes.
//    Call: sanitizeInput(str, 500)
// ---------------------------------------------------------------------------
export function sanitizeInput(str, maxLength = 500) {
  if (typeof str !== 'string') return '';
  return str.trim().slice(0, maxLength);
}
