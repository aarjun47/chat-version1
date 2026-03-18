# ----------------------------------------------------
# routes/client.py
# All routes scoped to the logged-in client's data.
# client_id is read from the JWT — never from the URL.
# =====================================================

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId

from ..auth import require_client, verify_password, hash_password
from ..crud import (
    get_client,
    get_leads_by_client,
    get_conversations_by_lead,
    get_appointments_by_client,
    get_user_by_client_id,
    update_user_password,
    get_leads_count_by_client,
    get_appointments_count_by_client,
)
from ..database import leads_col

router = APIRouter(prefix="/api/client", tags=["client"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def fmt_date(dt):
    return dt.isoformat() if dt else None


# =====================================================
# PROFILE — client sees their own institute info
# =====================================================

@router.get("/profile")
async def get_profile(user: dict = Depends(require_client)):
    client_id = user["client_id"]
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    leads_count = await get_leads_count_by_client(client_id)
    appts_count = await get_appointments_count_by_client(client_id)

    return {
        "institute_name": client.get("institute_name"),
        "twilio_phone_number": client.get("twilio_phone_number"),
        "persona_name": client.get("persona_name"),
        "is_active": client.get("is_active"),
        "leads_count": leads_count,
        "appointments_count": appts_count,
        # Never expose twilio_auth_token or account_sid to client
    }


# =====================================================
# CHANGE PASSWORD
# =====================================================

@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(require_client)
):
    client_id = user["client_id"]
    db_user = await get_user_by_client_id(client_id)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, db_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    await update_user_password(db_user["id"], hash_password(body.new_password))
    return {"status": "password updated"}


# =====================================================
# LEADS — scoped to this client only
# =====================================================

@router.get("/leads")
async def get_leads(user: dict = Depends(require_client)):
    client_id = user["client_id"]
    leads = await get_leads_by_client(client_id)
    return [
        {
            "id": l["id"],
            "phone_number": l.get("phone_number"),
            "name": l.get("name"),
            "service_interest": l.get("service_interest"),
            "state": l.get("state"),
            "last_interaction_at": fmt_date(l.get("last_interaction_at")),
            "created_at": fmt_date(l.get("created_at")),
        }
        for l in leads
    ]


# =====================================================
# LEAD DETAIL + CONVERSATIONS
# =====================================================

@router.get("/leads/{lead_id}")
async def get_lead_detail(lead_id: str, user: dict = Depends(require_client)):
    client_id = user["client_id"]

    # Enforce: client can only access their own leads
    lead = await leads_col.find_one({
        "_id": ObjectId(lead_id),
        "client_id": client_id
    })

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    chats = await get_conversations_by_lead(lead_id)

    return {
        "lead": {
            "id": str(lead["_id"]),
            "phone_number": lead.get("phone_number"),
            "name": lead.get("name"),
            "service_interest": lead.get("service_interest"),
            "state": lead.get("state"),
            "last_interaction_at": fmt_date(lead.get("last_interaction_at")),
            "created_at": fmt_date(lead.get("created_at")),
        },
        "chats": [
            {
                "id": c["id"],
                "text": c.get("text"),
                "direction": c.get("direction"),
                "source": c.get("source"),
                "created_at": fmt_date(c.get("created_at")),
            }
            for c in chats
        ]
    }


# =====================================================
# APPOINTMENTS — scoped to this client only
# =====================================================

@router.get("/appointments")
async def get_appointments(user: dict = Depends(require_client)):
    client_id = user["client_id"]
    appts = await get_appointments_by_client(client_id)

    result = []
    for a in appts:
        lead = await leads_col.find_one({"_id": ObjectId(a["lead_id"])})
        result.append({
            "id": a["id"],
            "lead_id": a.get("lead_id"),
            "lead_name": lead.get("name") if lead else None,
            "phone_number": lead.get("phone_number") if lead else None,
            "requested_time": a.get("requested_time"),
            "status": a.get("status"),
            "created_at": fmt_date(a.get("created_at")),
        })
    return result