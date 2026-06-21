"""
BotBooking model — HARDENED with paise-only fields and payment/payout status tracking.
All money stored as integer paise. No Float anywhere.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotBooking(Base):
    __tablename__ = "BotBooking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slotId = Column(Integer, ForeignKey("BotTurfSlot.id"), nullable=False)
    teamName = Column(String, nullable=False)
    captainName = Column(String, nullable=False)
    captainPhone = Column(String, nullable=False)
    sport = Column(String, nullable=True)

    # ── Payment Tracking ──
    paymentLinkId = Column(String, nullable=True)        # Razorpay payment link ID (used for idempotency)
    razorpayPaymentId = Column(String, nullable=True)    # Actual payment ID from webhook payload

    # ── Money Fields (ALL INTEGER PAISE — never float!) ──
    totalPaidPaise = Column(Integer, default=0)           # Total user paid (e.g., 125000 = ₹1250)
    ownerSharePaise = Column(Integer, default=0)          # Owner's share (e.g., 120000 = ₹1200)
    platformFeePaise = Column(Integer, default=0)         # STRIKIT fee (e.g., 5000 = ₹50)

    # ── Status Tracking ──
    paymentStatus = Column(String, default="PENDING")     # PENDING | VERIFIED | FAILED | REFUNDED
    payoutStatus = Column(String, default="NOT_STARTED")  # NOT_STARTED | PROCESSING | COMPLETED | FAILED | MANUAL_REVIEW
    reminderSent = Column(Boolean, default=False)
    confirmedAt = Column(DateTime, nullable=True)

    createdAt = Column(DateTime, default=func.now())

    # Relationships
    slot = relationship("BotTurfSlot", back_populates="bookings")
    joinRequests = relationship("BotJoinRequest", back_populates="booking", cascade="all, delete-orphan")
    payoutLedger = relationship("BotPayoutLedger", back_populates="booking")
    auditLogs = relationship("BotPaymentAuditLog", back_populates="booking")

    def __repr__(self):
        return f"<BotBooking id={self.id} team='{self.teamName}' status={self.paymentStatus}/{self.payoutStatus}>"
