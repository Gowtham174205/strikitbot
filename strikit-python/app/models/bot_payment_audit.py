"""
BotPaymentAuditLog — NEW: Full audit trail for every payment event.
Every webhook, verification, mismatch, payout attempt, and error is logged here.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotPaymentAuditLog(Base):
    __tablename__ = "BotPaymentAuditLog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bookingId = Column(Integer, ForeignKey("BotBooking.id"), nullable=True)
    eventType = Column(String, nullable=False)
    # Event types:
    #   WEBHOOK_RECEIVED    - Raw webhook payload received from Razorpay
    #   PAYMENT_VERIFIED    - Payment amount matched and booking confirmed
    #   AMOUNT_MISMATCH     - Paid amount != expected amount
    #   PAYOUT_INITIATED    - RazorpayX payout API call started
    #   PAYOUT_SUCCESS      - Payout completed successfully
    #   PAYOUT_FAILED       - Payout API call failed
    #   DUPLICATE_BLOCKED   - Duplicate webhook/payment blocked by idempotency
    #   MANUAL_REVIEW       - Flagged for manual developer review
    #   REFUND_INITIATED    - Refund process started
    #   REFUND_COMPLETED    - Refund processed successfully

    payload = Column(Text, nullable=True)   # JSON stringified webhook/error data
    message = Column(String, nullable=False)
    createdAt = Column(DateTime, default=func.now())

    # Relationships
    booking = relationship("BotBooking", back_populates="auditLogs")

    def __repr__(self):
        return f"<BotPaymentAuditLog id={self.id} event='{self.eventType}' booking={self.bookingId}>"
