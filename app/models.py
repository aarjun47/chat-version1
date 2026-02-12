from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from .database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True, index=True)
    name = Column(String, default="N/A")
    status = Column(String, default="New")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    direction = Column(String)   # inbound / outbound
    message_text = Column(Text)
    source = Column(String)      # whatsapp / ai / admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())
