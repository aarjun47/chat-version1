# ----------------------------------------------------
# routes/master.py
# All routes here require master JWT.
# Handles client management + credential creation.
# ----------------------------------------------------

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from twilio.rest import Client as TwilioClient

from ..auth import require_master, hash_password
from ..crud import (
    get_all_clients, get_client, create_client,
    update_client, delete_client,
    create_user, update_user_credentials, get_user_by_client_id,
    get_leads_count_by_client, get_appointments_count_by_client
)

router = APIRouter(prefix="/api/master", tags=["master"])


class CreateClientRequest(BaseModel):
    institute_name: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    persona_name: Optional[str] = "Arun"
    system_prompt: Optional[str] = None
    # Credentials for the client's CRM login
    username: str
    password: str
    # Base URL for auto-registering Twilio webhook
    base_url: Optional[str] = None


class UpdateClientRequest(BaseModel):
    institute_name: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    persona_name: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None


class ResetCredentialsRequest(BaseModel):
    username: str
    password: str


# =====================================================
# GET ALL CLIENTS WITH STATS
# =====================================================

@router.get("/clients")
async def get_clients(_: dict = Depends(require_master)):
    clients = await get_all_clients()
    result = []
    for c in clients:
        leads_count = await get_leads_count_by_client(c["id"])
        appts_count = await get_appointments_count_by_client(c["id"])
        user = await get_user_by_client_id(c["id"])
        result.append({
            "id": c["id"],
            "institute_name": c.get("institute_name"),
            "twilio_phone_number": c.get("twilio_phone_number"),
            "twilio_account_sid": c.get("twilio_account_sid"),
            "persona_name": c.get("persona_name"),
            "is_active": c.get("is_active"),
            "webhook_url": c.get("webhook_url"),
            "leads_count": leads_count,
            "appointments_count": appts_count,
            "username": user["username"] if user else None,
            "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
        })
    return result


# =====================================================
# GET SINGLE CLIENT (full detail including auth token)
# =====================================================

@router.get("/clients/{client_id}")
async def get_client_detail(client_id: str, _: dict = Depends(require_master)):
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    leads_count = await get_leads_count_by_client(client_id)
    appts_count = await get_appointments_count_by_client(client_id)
    user = await get_user_by_client_id(client_id)

    return {
        **client,
        "leads_count": leads_count,
        "appointments_count": appts_count,
        "username": user["username"] if user else None,
        "created_at": client["created_at"].isoformat() if client.get("created_at") else None,
    }


# =====================================================
# CREATE CLIENT + AUTO-REGISTER TWILIO WEBHOOK
# =====================================================

@router.post("/clients")
async def create_new_client(body: CreateClientRequest, _: dict = Depends(require_master)):
    # Create the client document
    client = await create_client({
        "institute_name": body.institute_name,
        "twilio_account_sid": body.twilio_account_sid,
        "twilio_auth_token": body.twilio_auth_token,
        "twilio_phone_number": body.twilio_phone_number,
        "persona_name": body.persona_name,
        "system_prompt": body.system_prompt,
    })

    client_id = client["id"]

    # Create login credentials for this client
    await create_user(
        client_id=client_id,
        username=body.username,
        password_hash=hash_password(body.password)
    )

    # Auto-register Twilio webhook if base_url provided
    webhook_url = None
    if body.base_url:
        try:
            twilio = TwilioClient(body.twilio_account_sid, body.twilio_auth_token)
            numbers = twilio.incoming_phone_numbers.list(
                phone_number=body.twilio_phone_number
            )
            if numbers:
                webhook_url = f"{body.base_url}/message/{client_id}"
                numbers[0].update(sms_url=webhook_url, sms_method="POST")
                await update_client(client_id, {"webhook_url": webhook_url})
        except Exception as e:
            print(f"Twilio webhook registration failed: {e}")

    return {
        **client,
        "username": body.username,
        "webhook_url": webhook_url,
        "message": "Client created successfully"
    }


# =====================================================
# UPDATE CLIENT INFO
# =====================================================

@router.put("/clients/{client_id}")
async def update_client_info(
    client_id: str,
    body: UpdateClientRequest,
    _: dict = Depends(require_master)
):
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    await update_client(client_id, update_data)
    return {"status": "updated"}


# =====================================================
# RESET CLIENT LOGIN CREDENTIALS
# =====================================================

@router.post("/clients/{client_id}/reset-credentials")
async def reset_credentials(
    client_id: str,
    body: ResetCredentialsRequest,
    _: dict = Depends(require_master)
):
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    await update_user_credentials(
        client_id=client_id,
        username=body.username,
        password_hash=hash_password(body.password)
    )
    return {"status": "credentials reset", "must_change_password": True}


# =====================================================
# DELETE CLIENT + ALL DATA
# =====================================================

@router.delete("/clients/{client_id}")
async def delete_client_route(client_id: str, _: dict = Depends(require_master)):
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    await delete_client(client_id)
    return {"status": "deleted"}