from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class GenerationRequest(BaseModel):
    client_name: Optional[str] = Field(None, description="Client or Project Name")
    # Core Metrics
    house_style: str = Field("", description="Architectural style / house style from Cameroon gallery")
    gross_area: str = Field(..., description="Gross floor area in m² (e.g. '250')")
    is_multi_story: bool = Field(False, description="Whether the building has multiple stories")
    num_stories: Optional[int] = Field(None, ge=2, le=5, description="Number of stories (2-5, when multi-story)")
    num_bedrooms: int = Field(..., ge=1, le=6, description="Number of bedrooms (1-6)")
    num_bathrooms: float = Field(..., ge=1.0, le=6.0, description="Number of bathrooms (1, 1.5, 2, 2.5, ..., 6)")
    # Exterior & Structure
    roof_type: str = Field(..., description="Roof type: Gable, Hip, Flat, Pitched")
    foundation: str = Field(..., description="Foundation: Slab, Basement")
    num_garages: int = Field(0, ge=0, le=5, description="Number of garage spaces (0-5)")
    outdoor_spaces: list[str] = Field(default_factory=list, description="Outdoor spaces (porch, patio, deck, balcony, courtyard, breezeway, outdoor kitchen)")
    # Interior Layout & Features
    overall_layout: str = Field(..., description="Layout style: Open Concept, Traditional, Split-Level")
    kitchen_type: str = Field(..., description="Kitchen layout: Open, Close")
    key_rooms: list[str] = Field(default_factory=list, description="Additional key rooms (home office, bonus room, media room, etc.)")
    # Cameroon
    region: str = Field("Center", description="Cameroon Region")
    additional_preferences: Optional[str] = Field(None, description="Extra details or preferences")


class GenerationImage(BaseModel):
    url: str
    storage_path: str


class GenerationResponse(BaseModel):
    id: str
    client_name: Optional[str] = None
    # Core Metrics
    house_style: str = ""
    gross_area: str = ""
    is_multi_story: bool = False
    num_stories: Optional[int] = None
    num_bedrooms: int = 0
    num_bathrooms: float = 0
    # Exterior & Structure
    roof_type: str = ""
    foundation: str = ""
    num_garages: int = 0
    outdoor_spaces: list[str] = []
    # Interior
    overall_layout: str = ""
    kitchen_type: str = ""
    key_rooms: list[str] = []
    # Cameroon
    region: str = "Center"
    additional_preferences: Optional[str] = None
    images: list[GenerationImage]
    prompt_used: str
    created_at: str
    user_id: str


class WorkspaceResponse(BaseModel):
    generation_id: str
    images: list[GenerationImage]
    prompt_used: str


class SingleRoomRequest(BaseModel):
    generation_id: str
    view_type: str
    # Re-uses same fields for regeneration
    house_style: str
    gross_area: str
    is_multi_story: bool = False
    num_stories: Optional[int] = None
    num_bedrooms: int
    num_bathrooms: float
    roof_type: str
    foundation: str
    num_garages: int = 0
    outdoor_spaces: list[str] = []
    overall_layout: str
    kitchen_type: str
    key_rooms: list[str] = []
    region: str = "Center"
    additional_preferences: Optional[str] = None


class SaveGenerationRequest(BaseModel):
    generation_id: str
    client_name: Optional[str] = None
    # Core Metrics
    house_style: str
    gross_area: str
    is_multi_story: bool = False
    num_stories: Optional[int] = None
    num_bedrooms: int
    num_bathrooms: float
    # Exterior & Structure
    roof_type: str
    foundation: str
    num_garages: int = 0
    outdoor_spaces: list[str] = []
    # Interior
    overall_layout: str
    kitchen_type: str
    key_rooms: list[str] = []
    # Cameroon
    region: str = "Center"
    additional_preferences: Optional[str] = None
    prompt_used: str
    images: list[GenerationImage]


class GenerationHistoryItem(BaseModel):
    id: str
    generation_type: str = "house_plan"
    client_name: Optional[str] = None
    house_style: str = ""
    gross_area: str = ""
    num_bedrooms: int = 0
    region: str = "Center"
    thumbnail_url: Optional[str] = None
    image_count: int = 0
    created_at: str


class GenerationUpdate(BaseModel):
    client_name: Optional[str] = None


# --- Floor Plan Schemas (unchanged) ---

class FloorPlanRequest(BaseModel):
    num_bedrooms: int = Field(..., ge=1, le=5, description="Number of bedrooms")
    num_bathrooms: int = Field(..., ge=1, le=4, description="Number of bathrooms")
    gross_area: str = Field(..., description="Gross floor area in m² (e.g. '150')")
    kitchen_type: str = Field(..., description="Kitchen layout: 'open' or 'closed'")
    extras: list[str] = Field(default_factory=list, description="Additional room types (e.g. walk-in closet, laundry room)")
    region: Optional[str] = Field("Center", description="Cameroon target region")
    additional_preferences: Optional[str] = Field(None, description="Extra preferences for the floor plan")


class FloorPlanSpecification(BaseModel):
    num_bedrooms: int
    num_bathrooms: int
    gross_area: str
    kitchen_type: str
    extras: list[str]
    region: str


class FloorPlanWorkspaceResponse(BaseModel):
    generation_id: str
    images: list[GenerationImage]
    prompt_used: str
    specification: FloorPlanSpecification


class SingleFloorPlanViewRequest(BaseModel):
    generation_id: str
    view_type: str
    prompt: Optional[str] = None


class SaveFloorPlanRequest(BaseModel):
    generation_id: str
    client_name: Optional[str] = None
    images: list[GenerationImage]
    prompt_used: str
    specification: FloorPlanSpecification
