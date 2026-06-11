"""
BotPayoutLedger — NEW: Idempotent payout tracking with unique constraint.
Prevents duplicate payouts via idempotencyKey and status checks.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotPayoutLedger(Base):
    __tablename__ = "BotPayoutLedger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bookingId = Column(Integer, ForeignKey("BotBooking.id"), nullable=False)
    ownerId = Column(Integer, ForeignKey("BotOwner.id"), nullable=False)
    razorpayPaymentId = Column(String, nullable=False)
    razorpayPayoutId = Column(String, nullable=True)

    # ── Money fields (ALL INTEGER PAISE) ──
    totalPaidPaise = Column(Integer, nullable=False)
    ownerSharePaise = Column(Integer, nullable=False)
    platformFeePaise = Column(Integer, nullable=False)

    ownerUpiId = Column(String, nullable=False)
    status = Column(String, default="PROCESSING")  # PROCESSING | COMPLETED | FAILED | MANUAL_REVIEW

    # ── Idempotency ──
    idempotencyKey = Column(String, unique=True, nullable=False)  # booking_{id}_{paymentId}_{ownerId}
    attemptCount = Column(Integer, default=1)
    failureReason = Column(String, nullable=True)

    createdAt = Column(DateTime, default=func.now())
    updatedAt = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    booking = relationship("BotBooking", back_populates="payoutLedger")
    owner = relationship("BotOwner", back_populates="payout_ledgers")

    def __repr__(self):
        return f"<BotPayoutLedger id={self.id} key='{self.idempotencyKey}' status='{self.status}'>"
