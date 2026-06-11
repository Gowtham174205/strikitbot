"""
Security middleware — HMAC signature verification, admin key auth, input sanitization.
Timing-safe comparisons throughout to prevent brute-force timing attacks.
"""
import hmac
import hashlib
import logging
from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader
from app.config import settings

logger = logging.getLogger(__name__)

admin_key_header = APIKeyHeader(name="x-admin-key", auto_error=False)


# ── Admin API Key Verification (timing-safe) ──

async def require_admin_key(api_key: str = Depends(admin_key_header)):
    """FastAPI dependency — verify admin API key with timing-safe comparison."""
    configured_key = settings.ADMIN_API_KEY
    if not configured_key:
        logger.error("[SECURITY] ADMIN_API_KEY not set. Refusing all admin requests.")
        raise HTTPException(status_code=503, detail="Server misconfiguration. Contact administrator.")

    if not api_key or not hmac.compare_digest(configured_key, api_key):
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing Admin API Key")


# ── WhatsApp Webhook Signature Verification ──

async def verify_whatsapp_signature(request: Request):
    """Verify Meta X-Hub-Signature-256 HMAC signature."""
    app_secret = settings.WHATSAPP_APP_SECRET
    if not app_secret:
        logger.warning("[SECURITY] WHATSAPP_APP_SECRET not set — skipping signature verification.")
        return

    sig_header = request.headers.get("x-hub-signature-256", "")
    if not sig_header:
        logger.warning("[SECURITY] WhatsApp webhook: missing signature header — rejected.")
        raise HTTPException(status_code=403, detail="Forbidden: Missing webhook signature")

    raw_body = await request.body()
    expected_sig = "sha256=" + hmac.new(
        app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, sig_header):
        logger.warning("[SECURITY] WhatsApp webhook: signature mismatch — rejected.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid webhook signature")


# ── Razorpay Webhook Signature Verification ──

def verify_razorpay_signature(raw_body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook HMAC-SHA256 signature."""
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        logger.warning("[SECURITY] RAZORPAY_WEBHOOK_SECRET not set — skipping verification.")
        return True

    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Telegram Webhook Secret Token Verification ──

async def verify_telegram_token(request: Request):
    """Verify Telegram X-Telegram-Bot-Api-Secret-Token header."""
    expected_token = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected_token:
        if settings.is_production:
            logger.error("[SECURITY] TELEGRAM_WEBHOOK_SECRET not set in production — rejecting.")
            raise HTTPException(status_code=403, detail="Forbidden: Telegram webhook not secured")
        logger.warning("[SECURITY] TELEGRAM_WEBHOOK_SECRET not set — skipping verification.")
        return

    provided_token = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(expected_token, provided_token):
        logger.warning("[SECURITY] Telegram webhook: token mismatch — rejected.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Telegram webhook token")


# ── Input Sanitizer ──

def sanitize_input(text: str, max_length: int = 500) -> str:
    """Trim whitespace and cap string length to prevent oversized DB writes."""
    if not isinstance(text, str):
        return ""
    return text.strip()[:max_length]
