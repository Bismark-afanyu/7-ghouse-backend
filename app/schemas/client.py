from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClientBase(BaseModel):
    name: str = Field(..., description="Full name or company name of the client")
    email: Optional[str] = Field(None, description="Contact email address")
    phone: Optional[str] = Field(None, description="Contact phone number")
    notes: Optional[str] = Field(None, description="Additional notes or preferences for this client")


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class ClientResponse(ClientBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str
