from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from twilio.request_validator import RequestValidator      # #2 FIX
import traceback
import asyncio
from bson import ObjectId
from twilio.rest import Client as TwilioClient

from .database import clients_col, leads_col, conversations_col, appointments_col, blocklist_col
from .crud import (
    get_or_create_lead, update_lead_field, save_message,
    create_appointment, update_last_interaction,
    get_latest_appointment, update_appointment_time, get_client,
    normalize_service_interest,
)
from .llm import (
    ask_llm, extract_name_with_two_layers, extract_service_interest,
    process_appointment_request, parse_and_format_time_info
)
from .routes.auth import router as auth_router
from .routes.master import router as master_router
from .routes.client import router as client_router

# =====================================================
# RATE LIMITER SETUP
# =====================================================

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# =====================================================
# LLM CONCURRENCY LIMITER
# =====================================================

llm_semaphore = asyncio.Semaphore(50)

# =====================================================
# INPUT VALIDATION
# =====================================================

MAX_MESSAGE_LENGTH = 1000                                  # #9 FIX

# =====================================================
# APP SETUP
# =====================================================

app = FastAPI(title="Lakshya CRM API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://user-ai-studio.vercel.app",
        "https://admin-ai-studio.vercel.app",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router)
app.include_router(master_router)
app.include_router(client_router)


# =====================================================
# STARTUP — MongoDB indexes
# =====================================================

@app.on_event("startup")
async def startup_event():
    await leads_col.create_index(
        [("client_id", 1), ("phone_number", 1)],
        unique=True
    )
    await leads_col.create_index([("client_id", 1), ("created_at", -1)])
    await leads_col.create_index([("client_id", 1), ("service_interest", 1), ("created_at", -1)])
    await conversations_col.create_index([("client_id", 1), ("lead_id", 1), ("created_at", 1)])
    await conversations_col.create_index([("client_id", 1), ("created_at", -1)])
    await appointments_col.create_index([("client_id", 1), ("lead_id", 1), ("created_at", -1)])
    await appointments_col.create_index([("client_id", 1), ("created_at", -1)])
    await clients_col.create_index("twilio_phone_number", unique=True)
    # #4 FIX — blocklist indexes
    await blocklist_col.create_index("jti", unique=True)
    await blocklist_col.create_index("expires_at", expireAfterSeconds=0)  # TTL auto-cleanup


# =====================================================
# HELPERS
# =====================================================

def build_welcome_back_message(lead: dict, client: dict) -> str:
    name = lead.get("name") or ""
    interest = lead.get("service_interest")
    institute = client.get("institute_name", "our institute")
    if interest:
        return (
            f"Hi {name} 🙂 welcome back!\n"
            f"Last time you were looking into {interest}.\n"
            f"Would you like to continue with that or explore something else?"
        )
    return f"Hi {name}! Welcome back to {institute} 😊 How can I assist you today?"


async def send_whatsapp(client: dict, to: str, body: str):
    twilio = TwilioClient(
        client["twilio_account_sid"],
        client["twilio_auth_token"]
    )
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: twilio.messages.create(
            from_=f"whatsapp:{client['twilio_phone_number']}",
            to=f"whatsapp:{to}",
            body=body
        )
    )


# =====================================================
# CORE WEBHOOK PROCESSING LOGIC (runs in background)
# client is passed in — already fetched and validated
# in the webhook handler, no double DB lookup needed
# =====================================================

async def process_webhook(client_id: str, form: dict, client: dict):
    try:
        user_text = form.get("Body", "").strip()
        from_number = form.get("From", "").replace("whatsapp:", "")

        if not user_text or not from_number:
            return

        # #9 FIX — Truncate oversized messages before they hit the LLM
        if len(user_text) > MAX_MESSAGE_LENGTH:
            print(f"Warning: Message from {from_number} truncated ({len(user_text)} chars)")
            user_text = user_text[:MAX_MESSAGE_LENGTH]

        lead = await get_or_create_lead(client_id, from_number)
        lead_id = lead["id"]

        greeting_type = "NONE"
        if not lead.get("name"):
            greeting_type = "NEW_USER"
        elif lead.get("state") == "session_expired":
            greeting_type = "WELCOME_BACK"

        if not lead.get("name"):
            extracted_name = extract_name_with_two_layers(user_text)
            if extracted_name:
                await update_lead_field(lead_id, {"name": extracted_name})
                lead["name"] = extracted_name

        extracted_service = extract_service_interest(user_text)
        appointment_words = ["appointment", "appointemnt", "callback", "call back", "confirm"]
        if extracted_service and extracted_service.lower() not in appointment_words:
            normalized_service = normalize_service_interest(extracted_service)
            if lead.get("service_interest") != normalized_service:
                await update_lead_field(lead_id, {"service_interest": normalized_service})
                lead["service_interest"] = normalized_service

        await save_message(client_id, lead_id, user_text, "inbound", "whatsapp")

        if greeting_type == "NEW_USER":
            async with llm_semaphore:
                ai_reply = await ask_llm(user_text, lead=lead, greeting_type=greeting_type, client=client)
            await save_message(client_id, lead_id, ai_reply, "outbound", "ai")
            await update_lead_field(lead_id, {"state": "normal"})
            await update_last_interaction(lead_id)
            await send_whatsapp(client, from_number, ai_reply)
            return

        text_lower = user_text.lower()
        user_is_greeting = text_lower.strip() in ["hi", "hello", "hey"]

        if greeting_type == "WELCOME_BACK":
            welcome_msg = build_welcome_back_message(lead, client)
            if user_is_greeting:
                ai_reply = welcome_msg
            else:
                async with llm_semaphore:
                    llm_reply = await ask_llm(user_text, lead=lead, greeting_type="NONE", client=client)
                ai_reply = welcome_msg + "\n\n" + llm_reply
            await save_message(client_id, lead_id, ai_reply, "outbound", "ai")
            await update_lead_field(lead_id, {"state": "normal"})
            await update_last_interaction(lead_id)
            await send_whatsapp(client, from_number, ai_reply)
            return

        appointment_words_detect = ["appointment", "appointemnt", "callback", "call"]
        asking_words = ["when", "what", "where"]
        is_view_appointment = (
            not user_is_greeting
            and any(w in text_lower for w in appointment_words_detect)
            and any(a in text_lower for a in asking_words)
        )
        reschedule_keywords = ["reschedule", "change appointment"]

        if is_view_appointment:
            latest_appt = await get_latest_appointment(client_id, lead_id)
            ai_reply = (
                f"Your appointment is scheduled for {latest_appt['requested_time']}."
                if latest_appt
                else "You don't have a scheduled callback yet. Would you like to book one?"
            )

        elif not user_is_greeting and any(k in text_lower for k in reschedule_keywords):
            latest_appt = await get_latest_appointment(client_id, lead_id)
            if latest_appt:
                await update_lead_field(lead_id, {"state": "awaiting_appointment_time"})
                ai_reply = "Sure 🙂 Please share the new day and time you prefer."
            else:
                ai_reply = "You don't have a scheduled callback yet. Would you like to book one?"

        elif lead.get("state") == "awaiting_appointment_time":
            formatted_time = parse_and_format_time_info(user_text)
            if formatted_time:
                latest_appt = await get_latest_appointment(client_id, lead_id)
                if latest_appt:
                    await update_appointment_time(latest_appt["id"], formatted_time)
                    await update_lead_field(lead_id, {"state": "normal"})
                    ai_reply = f"Done 🙂 Your callback is now rescheduled to {formatted_time}."
                else:
                    ai_reply = "I couldn't find an existing appointment."
            else:
                ai_reply = "Please share the new day and time."

        else:
            appointment_data = process_appointment_request(
                user_text, current_lead_state=lead.get("state", "normal")
            )

            if lead.get("state") == "awaiting_appointment_confirmation":
                confirm_words = ["confirm", "yes", "ok", "okay", "done", "sure"]
                if (
                    appointment_data["intent"] == "confirm_appointment"
                    or any(w in text_lower for w in confirm_words)
                ):
                    pending_time = lead.get("pending_appointment_time")
                    if pending_time:
                        await create_appointment(client_id, lead_id, pending_time, status="confirmed")
                        ai_reply = f"Callback scheduled! ✅ Our team will contact you on {pending_time}."
                        await update_lead_field(lead_id, {"state": "normal", "pending_appointment_time": None})
                    else:
                        ai_reply = "Please share the time again."
                else:
                    ai_reply = "Okay, what day and time works best for you?"
                    await update_lead_field(lead_id, {"state": "normal", "pending_appointment_time": None})

            elif appointment_data["intent"] == "schedule_appointment":
                time_info = appointment_data.get("time_info")
                if time_info:
                    formatted_time = parse_and_format_time_info(time_info)
                    await update_lead_field(lead_id, {
                        "pending_appointment_time": formatted_time,
                        "state": "awaiting_appointment_confirmation"
                    })
                    name = lead.get("name") or ""
                    ai_reply = f"Okay {name}, I'll schedule a callback on {formatted_time}. Please confirm 🙂"
                else:
                    ai_reply = "What day and time works best for you?"
            else:
                async with llm_semaphore:
                    ai_reply = await ask_llm(user_text, lead=lead, greeting_type=greeting_type, client=client)

        name = lead.get("name")
        if name and not user_is_greeting and "welcome back" not in ai_reply.lower():
            for pattern in [f"Hi {name}", f"Hello {name}", f"Hey {name}",
                            f"Hi {name}!", f"Hello {name}!", f"Hey {name}!"]:
                if ai_reply.strip().startswith(pattern):
                    ai_reply = ai_reply.replace(pattern, f"Okay {name}", 1)
                    break

        await save_message(client_id, lead_id, ai_reply, "outbound", "ai")
        if lead.get("state") not in ("awaiting_appointment_confirmation", "awaiting_appointment_time"):
            await update_lead_field(lead_id, {"state": "active_chat"})
        await update_last_interaction(lead_id)
        await send_whatsapp(client, from_number, ai_reply)

    except Exception as e:
        print("Webhook processing error:", e)
        traceback.print_exc()


# =====================================================
# WHATSAPP WEBHOOK
# #2 FIX — Twilio signature validated before processing
# #7 FIX — Rate limited to 30 requests/min per IP
# =====================================================

@app.post("/message/{client_id}")
@limiter.limit("30/minute")
async def whatsapp_webhook(client_id: str, request: Request, background_tasks: BackgroundTasks):
    # Fetch client first — needed for signature validation
    client = await get_client(client_id)
    if not client or not client.get("is_active"):
        return Response(status_code=404)

    form = await request.form()
    form_data = dict(form)

    # #2 FIX — Validate the request actually came from Twilio
    validator = RequestValidator(client["twilio_auth_token"])
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    if not validator.validate(url, form_data, signature):
        print(f"Invalid Twilio signature for client {client_id} — request rejected")
        return Response(status_code=403)

    # Pass client along so process_webhook doesn't need another DB lookup
    background_tasks.add_task(process_webhook, client_id, form_data, client)
    return Response(status_code=200)


# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
async def health():
    return {"status": "ok"}
