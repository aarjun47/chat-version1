from fastapi import FastAPI, Request, Depends, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from .database import SessionLocal, engine
from .models import Base, Lead, Conversation
from .crud import get_or_create_lead, save_message
from .llm import ask_llm, extract_name_with_two_layers
from .twilio_utils import send_whatsapp_message

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")


# ----------------------------
# DB Dependency
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------
# WhatsApp Webhook (Twilio)
# ----------------------------
@app.post("/message")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):

    try:
        form = await request.form()

        user_text = form.get("Body", "").strip()
        from_number = form.get("From", "").replace("whatsapp:", "")

        if not user_text or not from_number:
            return Response(status_code=200)

        # 1️⃣ Get or create lead
        lead = get_or_create_lead(db, from_number)

        # 2️⃣ Name extraction (LLM + Regex fallback)
        if not lead.name:
            extracted_name = extract_name_with_two_layers(user_text)
            if extracted_name:
                lead.name = extracted_name
                db.commit()

        # 3️⃣ Save inbound message
        save_message(
            db=db,
            lead_id=lead.id,
            text=user_text,
            direction="inbound",
            source="whatsapp"
        )

        # 4️⃣ Generate AI reply (safe)
        try:
            ai_reply = ask_llm(user_text)
        except Exception as e:
            print("LLM failure:", e)
            ai_reply = "Sorry, I’m facing a temporary issue. Please try again shortly."

        # 5️⃣ Save outbound message
        save_message(
            db=db,
            lead_id=lead.id,
            text=ai_reply,
            direction="outbound",
            source="ai"
        )

        # 6️⃣ Send reply via Twilio REST API
        send_whatsapp_message(
            to=from_number,
            body=ai_reply
        )

        return Response(status_code=200)

    except Exception as e:
        print("Webhook critical error:", e)
        return Response(status_code=200)


# ----------------------------
# CRM - Leads list
# ----------------------------
@app.get("/crm/leads", response_class=HTMLResponse)
def crm_leads(request: Request, db: Session = Depends(get_db)):

    leads = db.query(Lead).order_by(Lead.created_at.desc()).all()

    return templates.TemplateResponse(
        "leads.html",
        {
            "request": request,
            "leads": leads
        }
    )


# ----------------------------
# CRM - Lead detail + conversation
# ----------------------------
@app.get("/crm/leads/{lead_id}", response_class=HTMLResponse)
def crm_lead_detail(lead_id: int, request: Request, db: Session = Depends(get_db)):

    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    conversations = (
        db.query(Conversation)
        .filter(Conversation.lead_id == lead_id)
        .order_by(Conversation.created_at)
        .all()
    )

    return templates.TemplateResponse(
        "lead_detail.html",
        {
            "request": request,
            "lead": lead,
            "chats": conversations
        }
    )
