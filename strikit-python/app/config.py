"""
Centralized configuration — single source of truth for all env vars and platform constants.
All money values are in PAISE (integer). Never float for money.
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Type-safe environment variable loading with defaults."""

    # ── Server ──
    PORT: int = 5000
    NODE_ENV: str = "development"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/strikit"

    # ── WhatsApp Meta Cloud API ──
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "STRIKIT_TOKEN"
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_FLOW_ID: str = ""
    ONBOARDING_NUMBER: str = "919360756749"

    # ── Telegram Bot ──
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # ── Razorpay ──
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAYX_ACCOUNT_NUMBER: str = ""

    # ── Admin ──
    ADMIN_API_KEY: str = ""
    DEVELOPER_NUMBERS: str = ""  # comma-separated

    # ── Platform Fee Constants (PAISE — integer only) ──
    PLATFORM_BOOKING_FEE_PAISE: int = 5000    # ₹50
    PLATFORM_JOIN_FEE_PAISE: int = 900        # ₹9
    SUBSCRIPTION_FEE_PAISE: int = 69900       # ₹699

    # ── Rate Limiting ──
    RATE_LIMIT_WHATSAPP: str = "500/minute"
    RATE_LIMIT_TELEGRAM: str = "50/minute"
    RATE_LIMIT_RAZORPAY: str = "30/minute"
    RATE_LIMIT_ADMIN: str = "20/minute"

    # ── WhatsApp API ──
    WHATSAPP_API_VERSION: str = "v21.0"

    # ── Server URLs ──
    BASE_URL: str = "https://bot.strikit.in"
    LOG_LEVEL: str = "INFO"

    # ── Slot Reservation ──
    SLOT_RESERVATION_MINUTES: int = 15

    # ── Cancellation Policy ──
    CANCEL_FULL_REFUND_HOURS: int = 4     # 80% refund if > 4 hours before
    CANCEL_PARTIAL_REFUND_HOURS: int = 2  # 50% refund if > 2 hours before
    RESCHEDULE_FREE_HOURS: int = 6        # Free reschedule if > 6 hours before

    @property
    def developer_numbers_list(self) -> list[str]:
        return [n.strip() for n in self.DEVELOPER_NUMBERS.split(",") if n.strip()]

    @property
    def is_production(self) -> bool:
        return self.NODE_ENV == "production"

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    @property
    def razorpayx_configured(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET and self.RAZORPAYX_ACCOUNT_NUMBER)

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.WHATSAPP_ACCESS_TOKEN and self.WHATSAPP_PHONE_NUMBER_ID)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Singleton instance
settings = Settings()
