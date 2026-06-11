"""BotSession model — Conversational state machine context for WhatsApp chat sessions."""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class BotSession(Base):
    __tablename__ = "BotSession"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)       # CUSTOMER | OWNER | ONBOARDING
    state = Column(String, nullable=False)      # Current state machine tag
    context = Column(String, nullable=True)     # JSON context payload
    language = Column(String, default="en")     # en | ta (Tamil)
    updatedAt = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<BotSession phone='{self.phone}' role='{self.role}' state='{self.state}'>"
