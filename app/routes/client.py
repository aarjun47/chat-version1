# ----------------------------------------------------
# routes/client.py
# All routes scoped to the logged-in client's data.
# client_id is read from the JWT — never from the URL.
# =====================================================

from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..auth import require_client, verify_password, hash_password
from ..crud import (
    get_client,
    get_leads_by_client,
    get_conversations_by_lead,
    get_appointments_by_client,
    get_lead_by_id_for_client,
    get_leads_by_ids_for_client,
    is_valid_object_id,
    normalize_service_interest,
    get_user_by_client_id,
    update_user_password,
    get_leads_count_by_client,
    get_appointments_count_by_client,
)

router = APIRouter(prefix="/api/client", tags=["client"])
IST = ZoneInfo("Asia/Kolkata")
ANALYTICS_RANGES = {"all", "today", "yesterday", "last_7_days", "last_30_days"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def fmt_date(dt):
    return dt.isoformat() if dt else None


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_ist(dt: datetime | None) -> datetime | None:
    normalized = _ensure_utc(dt)
    return normalized.astimezone(IST) if normalized else None


def _resolve_timeframe_bounds(range_key: str):
    now_ist = datetime.now(IST)
    today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_key == "all":
        return None, None
    if range_key == "today":
        return today_start, today_start + timedelta(days=1)
    if range_key == "yesterday":
        start = today_start - timedelta(days=1)
        return start, today_start
    if range_key == "last_7_days":
        start = today_start - timedelta(days=6)
        return start, today_start + timedelta(days=1)
    if range_key == "last_30_days":
        start = today_start - timedelta(days=29)
        return start, today_start + timedelta(days=1)
    raise HTTPException(status_code=400, detail="Invalid analytics range")


def _filter_docs_by_timeframe(docs: list[dict], range_key: str) -> list[dict]:
    start_ist, end_ist = _resolve_timeframe_bounds(range_key)
    if start_ist is None:
        return docs

    filtered = []
    for doc in docs:
        created_at_ist = _to_ist(doc.get("created_at"))
        if created_at_ist and start_ist <= created_at_ist < end_ist:
            filtered.append(doc)
    return filtered


def _build_hourly_series(leads: list[dict], start_ist: datetime):
    counts = {hour: 0 for hour in range(24)}
    for lead in leads:
        created_at_ist = _to_ist(lead.get("created_at"))
        if created_at_ist:
            counts[created_at_ist.hour] += 1

    return [
        {"label": f"{hour:02d}:00", "value": counts[hour]}
        for hour in range(24)
    ]


def _build_daily_series(leads: list[dict], start_ist: datetime, days: int):
    counts = {
        (start_ist + timedelta(days=offset)).date(): 0
        for offset in range(days)
    }

    for lead in leads:
        created_at_ist = _to_ist(lead.get("created_at"))
        if created_at_ist:
            day_key = created_at_ist.date()
            if day_key in counts:
                counts[day_key] += 1

    return [
        {
            "label": day.strftime("%d %b"),
            "value": counts[day],
        }
        for day in counts
    ]


def _build_all_time_cumulative_series(leads: list[dict]):
    if not leads:
        return []

    lead_dates = sorted(
        _to_ist(lead.get("created_at")).date()
        for lead in leads
        if _to_ist(lead.get("created_at"))
    )
    if not lead_dates:
        return []

    start_day = lead_dates[0]
    end_day = datetime.now(IST).date()
    counts = Counter(lead_dates)
    running_total = 0
    points = []
    current_day = start_day

    while current_day <= end_day:
        running_total += counts.get(current_day, 0)
        points.append({
            "label": current_day.strftime("%d %b %Y"),
            "value": running_total,
        })
        current_day += timedelta(days=1)

    return points


def _build_lead_growth(leads: list[dict], range_key: str):
    start_ist, _ = _resolve_timeframe_bounds(range_key)

    if range_key == "all":
        return {
            "chart_type": "line",
            "granularity": "cumulative_daily",
            "points": _build_all_time_cumulative_series(leads),
        }
    if range_key in {"today", "yesterday"}:
        return {
            "chart_type": "bar",
            "granularity": "hourly",
            "points": _build_hourly_series(leads, start_ist),
        }

    days = 7 if range_key == "last_7_days" else 30
    return {
        "chart_type": "bar",
        "granularity": "daily",
        "points": _build_daily_series(leads, start_ist, days),
    }


def _build_enquiry_distribution(leads: list[dict]):
    counts = Counter(
        normalize_service_interest(lead.get("service_interest")) or "Unknown"
        for lead in leads
    )
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    total = sum(counts.values())

    breakdown = [
        {
            "label": label,
            "count": count,
            "percentage": round((count / total) * 100, 1) if total else 0,
        }
        for label, count in ordered
    ]

    return {
        "top": breakdown[:5],
        "breakdown": breakdown,
        "total": total,
    }


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
    if not is_valid_object_id(lead_id):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")

    lead = await get_lead_by_id_for_client(client_id, lead_id)

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    chats = await get_conversations_by_lead(client_id, lead_id)

    return {
        "lead": {
            "id": lead["id"],
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
    leads_by_id = await get_leads_by_ids_for_client(
        client_id,
        [a["lead_id"] for a in appts if a.get("lead_id")]
    )

    result = []
    for a in appts:
        lead = leads_by_id.get(a["lead_id"])
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


# =====================================================
# ANALYTICS — scoped to this client only
# =====================================================

@router.get("/analytics")
async def get_analytics(
    range_key: str = Query("all", alias="range"),
    user: dict = Depends(require_client),
):
    if range_key not in ANALYTICS_RANGES:
        raise HTTPException(status_code=400, detail="Invalid analytics range")

    client_id = user["client_id"]
    leads = await get_leads_by_client(client_id)
    appointments = await get_appointments_by_client(client_id)

    filtered_leads = _filter_docs_by_timeframe(leads, range_key)
    filtered_appointments = _filter_docs_by_timeframe(appointments, range_key)
    enquiry_distribution = _build_enquiry_distribution(filtered_leads)

    return {
        "range": range_key,
        "kpis": {
            "total_leads": len(filtered_leads),
            "total_appointments": len(filtered_appointments),
        },
        "lead_growth_distribution": _build_lead_growth(filtered_leads, range_key),
        "enquiry_type_distribution": enquiry_distribution,
    }
