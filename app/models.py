from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClientModel(BaseModel):
    id: Optional[str] = None
    institute_name: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    persona_name: str
    system_prompt: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserModel(BaseModel):
    """Login credentials for a client user."""
    id: Optional[str] = None
    client_id: str                        # which client this user belongs to
    username: str
    password_hash: str
    must_change_password: bool = True     # forced on first login
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LeadModel(BaseModel):
    id: Optional[str] = None
    client_id: str
    phone_number: str
    name: Optional[str] = None
    service_interest: Optional[str] = None
    state: str = "normal"
    pending_appointment_time: Optional[str] = None
    last_interaction_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationModel(BaseModel):
    id: Optional[str] = None
    client_id: str
    lead_id: str
    text: str
    direction: str
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppointmentModel(BaseModel):
    id: Optional[str] = None
    client_id: str
    lead_id: str
    requested_time: str
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
