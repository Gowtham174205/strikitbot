"""BotJoinRequest model — Single player join request to existing booking."""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotJoinRequest(Base):
    __tablename__ = "BotJoinRequest"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bookingId = Column(Integer, ForeignKey("BotBooking.id"), nullable=False)
    playerName = Column(String, nullable=False)
    playerPhone = Column(String, nullable=False)
    status = Column(String, nullable=False, default="AWAITING_PAYMENT")  # AWAITING_PAYMENT | PENDING | ACCEPTED | REJECTED
    joiningAmount = Column(Integer, nullable=True)  # Paise — amount set by captain
    createdAt = Column(DateTime, default=func.now())

    # Relationships
    booking = relationship("BotBooking", back_populates="joinRequests")

    def __repr__(self):
        return f"<BotJoinRequest id={self.id} player='{self.playerName}' status='{self.status}'>"
