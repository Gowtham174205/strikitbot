"""
BotOwnerRefundRequest model — tracks refund requests filed by turf owners.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BotOwnerRefundRequest(Base):
    __tablename__ = "BotOwnerRefundRequest"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ownerId = Column(Integer, ForeignKey("BotOwner.id", ondelete="CASCADE"), nullable=False)
    reason = Column(String, nullable=False)
    status = Column(String, default="PENDING")  # PENDING | RESOLVED | REJECTED
    createdAt = Column(DateTime, default=func.now())

    # Relationships
    owner = relationship("BotOwner")

    def __repr__(self):
        return f"<BotOwnerRefundRequest id={self.id} ownerId={self.ownerId} status='{self.status}'>"
