"""BotTurfSlot model — Time slot availability per turf per date."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotTurfSlot(Base):
    __tablename__ = "BotTurfSlot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ownerId = Column(Integer, ForeignKey("BotOwner.id"), nullable=False)
    date = Column(String, nullable=False)       # YYYY-MM-DD
    timeSlot = Column(String, nullable=False)    # e.g. "06:00 PM"
    status = Column(String, nullable=False)      # AVAILABLE | BOOKED | BLOCKED
    blockedByOwner = Column(Boolean, default=False)
    createdAt = Column(DateTime, default=func.now())

    # Relationships
    owner = relationship("BotOwner", back_populates="slots")
    bookings = relationship("BotBooking", back_populates="slot", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("ownerId", "date", "timeSlot", name="uq_owner_date_timeslot"),
    )

    def __repr__(self):
        return f"<BotTurfSlot id={self.id} date='{self.date}' slot='{self.timeSlot}' status='{self.status}'>"
