from datetime import datetime, timezone, timedelta
from bson import ObjectId
from .database import (
    clients_col, users_col, leads_col,
    conversations_col, appointments_col
)

REENGAGE_MINUTES = 15
KNOWN_SERVICE_INTERESTS = {"CA", "ACCA", "CMA", "CS", "CPA"}


def _doc(doc) -> dict:
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    return doc


def _object_id_or_none(value: str):
    try:
        return ObjectId(value)
    except Exception:
        return None


def is_valid_object_id(value: str) -> bool:
    return _object_id_or_none(value) is not None


def normalize_service_interest(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().upper()
    if not normalized:
        return None

    return normalized if normalized in KNOWN_SERVICE_INTERESTS else normalized


def normalize_username(username: str) -> str:
    return username.strip()


# =====================================================
# CLIENT OPERATIONS
# =====================================================

async def create_client(data: dict) -> dict:
    data["created_at"] = datetime.now(timezone.utc)
    data["is_active"] = True
    result = await clients_col.insert_one(data)
    data["id"] = str(result.inserted_id)
    data.pop("_id", None)
    return data


async def get_client(client_id: str) -> dict:
    try:
        doc = await clients_col.find_one({"_id": ObjectId(client_id)})
        return _doc(doc)
    except Exception:
        return None


async def get_all_clients() -> list:
    cursor = clients_col.find().sort("created_at", -1)
    docs = await cursor.to_list(length=1000)
    return [_doc(d) for d in docs]


async def update_client(client_id: str, fields: dict):
    await clients_col.update_one(
        {"_id": ObjectId(client_id)},
        {"$set": fields}
    )


async def delete_client(client_id: str):
    await clients_col.delete_one({"_id": ObjectId(client_id)})
    # Clean up all related data
    await users_col.delete_many({"client_id": client_id})
    await leads_col.delete_many({"client_id": client_id})
    await conversations_col.delete_many({"client_id": client_id})
    await appointments_col.delete_many({"client_id": client_id})


# =====================================================
# USER (CLIENT CREDENTIALS) OPERATIONS
# =====================================================

async def create_user(client_id: str, username: str, password_hash: str) -> dict:
    doc = {
        "client_id": client_id,
        "username": normalize_username(username),
        "password_hash": password_hash,
        "must_change_password": True,
        "created_at": datetime.now(timezone.utc),
    }
    result = await users_col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


async def get_user_by_username(username: str) -> dict:
    doc = await users_col.find_one({"username": normalize_username(username)})
    return _doc(doc)


async def get_user_by_client_id(client_id: str) -> dict:
    doc = await users_col.find_one({"client_id": client_id})
    return _doc(doc)


async def update_user_password(user_id: str, new_hash: str):
    await users_col.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "password_hash": new_hash,
            "must_change_password": False
        }}
    )


async def update_user_credentials(client_id: str, username: str, password_hash: str):
    """Master resets credentials for a client."""
    await users_col.update_one(
        {"client_id": client_id},
        {"$set": {
            "username": normalize_username(username),
            "password_hash": password_hash,
            "must_change_password": True
        }},
        upsert=True
    )


# =====================================================
# LEAD OPERATIONS
# =====================================================

async def get_or_create_lead(client_id: str, phone_number: str) -> dict:
    doc = await leads_col.find_one({
        "client_id": client_id,
        "phone_number": phone_number
    })

    if not doc:
        new_lead = {
            "client_id": client_id,
            "phone_number": phone_number,
            "name": None,
            "service_interest": None,
            "state": "normal",
            "pending_appointment_time": None,
            "last_interaction_at": None,
            "created_at": datetime.now(timezone.utc),
        }
        result = await leads_col.insert_one(new_lead)
        new_lead["id"] = str(result.inserted_id)
        new_lead.pop("_id", None)
        return new_lead

    lead = _doc(doc)

    if (
        lead.get("state") == "active_chat"
        and lead.get("last_interaction_at") is not None
    ):
        last = lead["last_interaction_at"]
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last > timedelta(minutes=REENGAGE_MINUTES):
            await leads_col.update_one(
                {"_id": ObjectId(lead["id"])},
                {"$set": {"state": "session_expired"}}
            )
            lead["state"] = "session_expired"

    return lead


async def update_lead_field(lead_id: str, fields: dict):
    if "service_interest" in fields:
        fields["service_interest"] = normalize_service_interest(fields["service_interest"])

    await leads_col.update_one(
        {"_id": ObjectId(lead_id)},
        {"$set": fields}
    )


async def update_last_interaction(lead_id: str):
    await leads_col.update_one(
        {"_id": ObjectId(lead_id)},
        {"$set": {"last_interaction_at": datetime.now(timezone.utc)}}
    )


async def get_leads_by_client(client_id: str) -> list:
    cursor = leads_col.find({"client_id": client_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=10000)
    return [_doc(d) for d in docs]


async def get_lead_by_id_for_client(client_id: str, lead_id: str) -> dict:
    oid = _object_id_or_none(lead_id)
    if not oid:
        return None

    doc = await leads_col.find_one({
        "_id": oid,
        "client_id": client_id,
    })
    return _doc(doc)


async def get_leads_count_by_client(client_id: str) -> int:
    return await leads_col.count_documents({"client_id": client_id})


# =====================================================
# CONVERSATION OPERATIONS
# =====================================================

async def save_message(client_id: str, lead_id: str, text: str, direction: str, source: str) -> dict:
    doc = {
        "client_id": client_id,
        "lead_id": lead_id,
        "text": text,
        "direction": direction,
        "source": source,
        "created_at": datetime.now(timezone.utc),
    }
    result = await conversations_col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


async def get_recent_messages(client_id: str, lead_id: str, limit: int = 6) -> list:
    cursor = (
        conversations_col
        .find({
            "client_id": client_id,
            "lead_id": lead_id,
        })
        .sort("created_at", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [_doc(d) for d in docs]


async def get_conversations_by_lead(client_id: str, lead_id: str) -> list:
    cursor = conversations_col.find({
        "client_id": client_id,
        "lead_id": lead_id,
    }).sort("created_at", 1)
    docs = await cursor.to_list(length=10000)
    return [_doc(d) for d in docs]


# =====================================================
# APPOINTMENT OPERATIONS
# =====================================================

async def create_appointment(client_id: str, lead_id: str, requested_time: str, status: str = "pending") -> dict:
    doc = {
        "client_id": client_id,
        "lead_id": lead_id,
        "requested_time": requested_time,
        "status": status,
        "created_at": datetime.now(timezone.utc),
    }
    result = await appointments_col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


async def get_latest_appointment(client_id: str, lead_id: str) -> dict:
    cursor = (
        appointments_col
        .find({
            "client_id": client_id,
            "lead_id": lead_id,
        })
        .sort("created_at", -1)
        .limit(1)
    )
    docs = await cursor.to_list(length=1)
    return _doc(docs[0]) if docs else None


async def update_appointment_time(appointment_id: str, new_time: str):
    await appointments_col.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"requested_time": new_time}}
    )


async def get_appointments_by_client(client_id: str) -> list:
    cursor = appointments_col.find({"client_id": client_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=10000)
    return [_doc(d) for d in docs]


async def get_leads_by_ids_for_client(client_id: str, lead_ids: list[str]) -> dict[str, dict]:
    object_ids = [oid for oid in (_object_id_or_none(lead_id) for lead_id in lead_ids) if oid]
    if not object_ids:
        return {}

    cursor = leads_col.find({
        "_id": {"$in": object_ids},
        "client_id": client_id,
    })
    docs = await cursor.to_list(length=len(object_ids))
    scoped_docs = [_doc(doc) for doc in docs]
    return {doc["id"]: doc for doc in scoped_docs}


async def get_appointments_count_by_client(client_id: str) -> int:
    return await appointments_col.count_documents({"client_id": client_id})
