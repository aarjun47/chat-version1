from sqlalchemy.orm import Session
from .models import Lead, Conversation


def get_or_create_lead(db: Session, phone: str):
    lead = db.query(Lead).filter(Lead.phone == phone).first()
    if not lead:
        lead = Lead(phone=phone)
        db.add(lead)
        db.commit()
        db.refresh(lead)
    return lead


def save_message(db: Session, lead_id: int, text: str, direction: str, source: str):
    msg = Conversation(
        lead_id=lead_id,
        message_text=text,
        direction=direction,
        source=source
    )
    db.add(msg)
    db.commit()
