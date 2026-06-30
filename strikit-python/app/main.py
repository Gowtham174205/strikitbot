"""
STRIKIT Bot Server — FastAPI application entry point.
Mounts all routes, middleware, schedulers, and serves the WhatsApp/Telegram/Razorpay webhooks.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import init_db, close_db, async_session_factory
from app.middleware.rate_limiter import limiter, rate_limit_exceeded_handler

# Configure structured logging with rotation
import os
from logging.handlers import RotatingFileHandler

os.makedirs("logs", exist_ok=True)
log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
root_logger = logging.getLogger()
root_logger.setLevel(log_level)

# Clear existing handlers to prevent double logging
if root_logger.hasHandlers():
    root_logger.handlers.clear()

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# Rotating File Handler
file_handler = RotatingFileHandler(
    "logs/server.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the FastAPI app."""
    # ── Startup ──
    logger.info("🚀 STRIKIT Bot Server starting...")
    await init_db()
    logger.info("✅ Database connected and tables ensured")

    # Create reports directory
    os.makedirs("reports", exist_ok=True)
    os.makedirs("backups", exist_ok=True)

    # Start APScheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()

    async def _run_monthly_report():
        async with async_session_factory() as db:
            from app.schedulers.monthly_report import check_and_send_monthly_report
            await check_and_send_monthly_report(db)

    async def _run_subscription_check():
        async with async_session_factory() as db:
            from app.schedulers.subscription_expiry import check_subscription_expiry
            await check_subscription_expiry(db)

    async def _run_slot_expiry():
        async with async_session_factory() as db:
            from app.schedulers.slot_expiry import check_slot_expiry
            await check_slot_expiry(db)

    async def _run_reminders():
        async with async_session_factory() as db:
            from app.schedulers.slot_expiry import send_booking_reminders
            await send_booking_reminders(db)

    # Schedule jobs
    scheduler.add_job(_run_monthly_report, "interval", hours=1, id="monthly_report")
    scheduler.add_job(_run_subscription_check, "interval", hours=1, id="subscription_check")
    scheduler.add_job(_run_slot_expiry, "interval", minutes=1, id="slot_expiry")
    scheduler.add_job(_run_reminders, "interval", hours=2, id="booking_reminders")

    scheduler.start()
    logger.info("⏰ Schedulers started: monthly_report, subscription_check, slot_expiry, booking_reminders")

    app.state.scheduler = scheduler

    logger.info(f"🟢 STRIKIT Bot Server ready on port {settings.PORT}")

    yield

    # ── Shutdown ──
    scheduler.shutdown()
    await close_db()
    logger.info("🔴 STRIKIT Bot Server stopped.")


# ── Create FastAPI App ──
app = FastAPI(
    title="STRIKIT Bot API",
    description="WhatsApp & Telegram Booking Bot with hardened payment processing",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware ──
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiter ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ── Security Headers Middleware ──
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


# ── Mount Routes ──
from app.routes.whatsapp import router as whatsapp_router
from app.routes.razorpay import router as razorpay_router
from app.routes.telegram import router as telegram_router
from app.routes.admin import router as admin_router

app.include_router(whatsapp_router)
app.include_router(razorpay_router)
app.include_router(telegram_router)
app.include_router(admin_router)

# ── Serve static reports (protected by admin key query param) ──
if os.path.exists("reports"):
    app.mount("/reports", StaticFiles(directory="reports"), name="reports")

# ── Serve static media files ──
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Health Check ──
@app.get("/health")
async def health_check():
    """Server health + DB connectivity check."""
    try:
        async with async_session_factory() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "active",
        "database": db_status,
        "whatsapp": "configured" if settings.whatsapp_configured else "mock",
        "razorpay": "configured" if settings.razorpay_configured else "mock",
        "telegram": "configured" if settings.telegram_configured else "mock",
    }


@app.get("/status")
async def status():
    """Minimal status endpoint."""
    return {"status": "active"}


# ── Run with: uvicorn app.main:app --host 0.0.0.0 --port 5000 ──
if __name__ == "__main__":
    import uvicorn
    reload_dev = settings.NODE_ENV == "development"
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=reload_dev)
