from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class GenerationRequest(BaseModel):
    client_name: Optional[str] = Field(None, description="Client or Project Name")
    property_type: str = Field(..., description="Type of property (e.g., Villa, Apartment, Duplex)")
    num_rooms: int = Field(..., ge=1, le=20, description="Number of rooms")
    land_size: str = Field(..., description="Land size with unit (e.g., '500 sqm')")
    architectural_style: str = Field(..., description="Preferred style (e.g., Modern, Colonial, Mediterranean)")
    additional_preferences: Optional[str] = Field(None, description="Extra details or preferences")


class GenerationImage(BaseModel):
    url: str
    storage_path: str


class GenerationResponse(BaseModel):
    id: str
    client_name: Optional[str] = None
    property_type: str
    num_rooms: int
    land_size: str
    architectural_style: str
    additional_preferences: Optional[str] = None
    images: list[GenerationImage]
    prompt_used: str
    created_at: str
    user_id: str


class GenerationHistoryItem(BaseModel):
    id: str
    client_name: Optional[str] = None
    property_type: str
    architectural_style: str
    num_rooms: int
    land_size: str
    thumbnail_url: Optional[str] = None
    image_count: int = 0
    created_at: str
