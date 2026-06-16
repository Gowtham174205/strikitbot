"""
BotOwner model — Turf owner registration and subscription management.
Column names match existing PostgreSQL schema (camelCase) for zero-migration compatibility.
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotOwner(Base):
    __tablename__ = "BotOwner"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    mobile = Column(String, unique=True, nullable=False)
    turfName = Column(String, nullable=False)
    location = Column(String, nullable=False)
    photoUrls = Column(String, nullable=False)
    gst = Column(String, nullable=True)
    msme = Column(String, nullable=True)
    msmeCardUrl = Column(String, nullable=True)
    utilityBillUrl = Column(String, nullable=True)
    upiId = Column(String, nullable=True)
    razorpayContactId = Column(String, nullable=True)
    razorpayFundAccountId = Column(String, nullable=True)
    verified = Column(Boolean, default=False)
    businessPhone = Column(String, unique=True, nullable=True)
    subscriptionActive = Column(Boolean, default=False)
    subscriptionExpiry = Column(DateTime, nullable=True)
    subscriptionPlan = Column(String, default="TRIAL")
    createdAt = Column(DateTime, default=func.now())
    openingTime = Column(String, default="06:00 AM")
    closingTime = Column(String, default="10:00 PM")
    # ── HARDENED: Integer paise instead of Float rupees ──
    pricePerHourPaise = Column(Integer, default=100000)  # ₹1000 = 100000 paise
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Relationships
    slots = relationship("BotTurfSlot", back_populates="owner", cascade="all, delete-orphan")
    payout_ledgers = relationship("BotPayoutLedger", back_populates="owner")

    def __repr__(self):
        return f"<BotOwner id={self.id} name='{self.name}' turf='{self.turfName}'>"
