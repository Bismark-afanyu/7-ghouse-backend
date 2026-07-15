from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime


class AnalyzePdfRequest(BaseModel):
    pdf_data: str = Field(..., description="Base64 data URL of the PDF floor plan")


class PdfAnalysisResult(BaseModel):
    rooms: list[dict] = Field(default_factory=list, description="Identified rooms with dimensions")
    layout_issues: list[str] = Field(default_factory=list, description="Gaps or issues found in the plan")
    suggestions: list[str] = Field(default_factory=list, description="Improvement suggestions")
    summary: str = Field("", description="Overall summary of the floor plan")


class PlotDimension(BaseModel):
    length_m: Optional[float] = Field(None, description="Length in meters")
    width_m: Optional[float] = Field(None, description="Width in meters")


class PlotSetbacks(BaseModel):
    front: Optional[float] = Field(None, description="Front setback in meters")
    rear: Optional[float] = Field(None, description="Rear setback in meters")
    left: Optional[float] = Field(None, description="Left setback in meters")
    right: Optional[float] = Field(None, description="Right setback in meters")


class PlotAnalysisResult(BaseModel):
    plot_description: str = Field("", description="General description of the plot")
    terrain_type: str = Field("", description="Type of terrain: flat, sloped, steep, uneven")
    terrain_notes: str = Field("", description="Detailed notes about the terrain")
    orientation_notes: str = Field("", description="Orientation of the plot if visible")
    constraints: list[str] = Field(default_factory=list, description="Observed constraints")
    suggested_dimensions: Optional[PlotDimension] = Field(None, description="Suggested plot dimensions")
    suggested_building_footprint: Optional[PlotDimension] = Field(None, description="Suggested building footprint")
    setback_suggestions: Optional[PlotSetbacks] = Field(None, description="Suggested setbacks")
    error: Optional[str] = Field(None, description="Error message if analysis failed")
    # Image classification
    image_type: str = Field("", description="cadastral_plan, satellite, architectural_plan, hand_drawn, floor_plan, other")
    # Extracted administrative info from survey/cadastral documents
    admin_info: Optional[dict] = Field(None, description="Administrative metadata from survey document (country, region, subdivision, beneficiary, surveyor, block, lot, etc.)")
    # Extracted dimensions from the document
    extracted_dimensions: Optional[dict] = Field(None, description="Area, length, width, boundary segment dimensions")
    # Boundary coordinates (raw X/Y from the plan, in local coordinate system)
    extracted_boundary: Optional[list[list[float]]] = Field(None, description="Boundary corner coordinates [[x1,y1], ...] from survey table")
    # GPS coordinates (if found directly on the image)
    extracted_gps: Optional[dict] = Field(None, description="GPS lat/lng if found on image")
    # Access information
    access_info: Optional[dict] = Field(None, description="Access type and description (e.g. servitude, road)")
    # Nearby land title references
    nearby_references: Optional[list[str]] = Field(None, description="Nearby TF/land title reference numbers")


class GenerationRequest(BaseModel):
    client_name: Optional[str] = Field(None, description="Client or Project Name")
    # Building Type
    building_type: str = Field("single_family", description="Building type: single_family, apartment, duplex, townhouse, commercial")
    # Core Metrics
    house_style: str = Field("", description="Architectural style / house style")
    gross_area: Optional[str] = Field(None, description="Gross floor area in m². Auto-computed from land dimensions if not provided.")
    is_multi_story: bool = Field(False, description="Whether the building has multiple stories")
    num_stories: Optional[int] = Field(None, ge=2, le=5, description="Number of stories (2-5, when multi-story)")
    num_bedrooms: int = Field(..., ge=1, le=20, description="Number of bedrooms (1-20)")
    num_bathrooms: float = Field(..., ge=1.0, le=20.0, description="Number of bathrooms (1, 1.5, 2, 2.5, ..., 20)")
    num_living_rooms: int = Field(1, ge=1, le=20, description="Number of living rooms (1-20)")
    num_kitchens: int = Field(1, ge=1, le=20, description="Number of kitchens (1-20)")
    # Exterior & Structure
    roof_type: str = Field(..., description="Roof type: Gable, Hip, Flat, Pitched")
    foundation: str = Field(..., description="Foundation: Slab, Basement")
    num_garages: int = Field(0, ge=0, le=5, description="Number of garage spaces (0-5)")
    outdoor_spaces: list[str] = Field(default_factory=list, description="Outdoor spaces (porch, patio, deck, balcony, courtyard, breezeway, outdoor kitchen)")
    # Interior Layout & Features
    overall_layout: str = Field(..., description="Layout style: Open Concept, Traditional, Split-Level")
    kitchen_type: str = Field(..., description="Kitchen layout: Open, Close")
    key_rooms: list[str] = Field(default_factory=list, description="Additional key rooms (home office, bonus room, media room, etc.)")
    # Apartment-specific fields (only used when building_type == "apartment")
    units_per_floor: Optional[int] = Field(None, ge=1, le=10, description="Number of apartment units per floor")
    num_floors: Optional[int] = Field(None, ge=1, le=10, description="Number of floors with apartment units")
    unit_bedrooms: Optional[int] = Field(None, ge=1, le=10, description="Bedrooms per apartment unit")
    unit_bathrooms: Optional[float] = Field(None, ge=1.0, le=10.0, description="Bathrooms per apartment unit")
    unit_kitchens: Optional[int] = Field(None, ge=1, le=5, description="Kitchens per apartment unit")
    unit_living_rooms: Optional[int] = Field(None, ge=1, le=5, description="Living rooms per apartment unit")
    # Cameroon
    region: str = Field("Center", description="Cameroon Region")
    division: str = Field("", description="Cameroon Division (sub-region)")
    additional_preferences: Optional[str] = Field(None, description="Extra details or preferences")
    # Reference file
    reference_file_data: Optional[str] = Field(None, description="Base64 data URL of reference image or PDF")
    reference_file_type: Optional[str] = Field(None, description="Type of reference file: 'image' or 'pdf'")
    reference_analysis: Optional[str] = Field(None, description="Text analysis from PDF floor plan analysis")
    # Land dimensions & shape
    land_shape: str = Field("rectangle", description="Shape of land: rectangle, l_shape, polygon")
    land_length: Optional[float] = Field(None, description="Land length in meters (for rectangle & L-shape)")
    land_width: Optional[float] = Field(None, description="Land width in meters (for rectangle & L-shape)")
    land_vertices: Optional[list[list[float]]] = Field(None, description="Polygon vertices as [[x1,y1],[x2,y2],...] for polygon shape")
    terrain_shape: Optional[str] = Field(None, description="Terrain/land shape description (e.g. flat, sloped, steep)")
    # Coordinates / geolocation
    latitude: Optional[float] = Field(None, description="Latitude of building site")
    longitude: Optional[float] = Field(None, description="Longitude of building site")
    location_name: Optional[str] = Field(None, description="Place name or address for geocoding")
    # Material source hub
    material_source_hub: Optional[str] = Field(None, description="Material source hub: douala, yaounde, bafoussam, bamenda, garoua, maroua, bertoua, kribi, or 'custom'")
    custom_hub_name: Optional[str] = Field(None, description="Custom hub name (when material_source_hub='custom')")
    custom_hub_lat: Optional[float] = Field(None, description="Custom hub latitude")
    custom_hub_lng: Optional[float] = Field(None, description="Custom hub longitude")

    @model_validator(mode="after")
    def _compute_totals_and_gross_area(self):
        # Compute totals for apartment buildings from per-unit config
        if self.building_type == "apartment" and self.units_per_floor and self.num_floors:
            total_units = self.units_per_floor * self.num_floors
            if self.unit_bedrooms:
                self.num_bedrooms = total_units * self.unit_bedrooms
            if self.unit_bathrooms:
                self.num_bathrooms = total_units * self.unit_bathrooms
            if self.unit_kitchens:
                self.num_kitchens = total_units * self.unit_kitchens
            if self.unit_living_rooms:
                self.num_living_rooms = total_units * self.unit_living_rooms
            # Auto-set multi-story for apartment buildings
            if self.num_floors and self.num_floors > 1:
                self.is_multi_story = True
                self.num_stories = self.num_floors

        if self.gross_area:
            return self

        if self.land_length and self.land_width:
            area = self.land_length * self.land_width
            self.gross_area = str(int(area))
            return self

        if self.land_vertices and len(self.land_vertices) >= 3:
            area = _polygon_area(self.land_vertices)
            self.gross_area = str(int(area))
            return self

        raise ValueError(
            "Either gross_area, land_length+land_width, or land_vertices must be provided"
        )


def _polygon_area(vertices: list[list[float]]) -> float:
    n = len(vertices)
    area = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


class GenerationImage(BaseModel):
    url: str
    storage_path: str
    label: Optional[str] = None
    view_key: Optional[str] = None


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
    division: str = ""
    additional_preferences: Optional[str] = None
    images: list[GenerationImage]
    prompt_used: str
    created_at: str
    user_id: str
    # PDF & DXF
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[str] = None
    dxf_url: Optional[str] = None


class RoomMeasurement(BaseModel):
    name: str = Field(..., description="Room name")
    code: str = Field("", description="Room code/label")
    room_type: str = Field("", description="Room type identifier")
    width_m: float = Field(..., description="Room width in meters")
    height_m: float = Field(..., description="Room height in meters")
    area_m2: float = Field(..., description="Room area in square meters")


class WorkspaceResponse(BaseModel):
    generation_id: str
    images: list[GenerationImage]
    prompt_used: str
    cost_estimate: Optional[dict] = None


class SingleRoomRequest(BaseModel):
    generation_id: str
    view_type: str
    # Re-uses same fields for regeneration
    house_style: str
    gross_area: str
    building_type: str = "single_family"
    is_multi_story: bool = False
    num_stories: Optional[int] = None
    num_bedrooms: int
    num_bathrooms: float
    num_living_rooms: int = 1
    num_kitchens: int = 1
    roof_type: str
    foundation: str
    num_garages: int = 0
    outdoor_spaces: list[str] = []
    overall_layout: str
    kitchen_type: str
    key_rooms: list[str] = []
    region: str = "Center"
    division: str = ""
    additional_preferences: Optional[str] = None


class SaveGenerationRequest(BaseModel):
    generation_id: str
    client_name: Optional[str] = None
    # Core Metrics
    house_style: str
    gross_area: str
    building_type: str = "single_family"
    is_multi_story: bool = False
    num_stories: Optional[int] = None
    num_bedrooms: int
    num_bathrooms: float
    num_living_rooms: int = 1
    num_kitchens: int = 1
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
    division: str = ""
    additional_preferences: Optional[str] = None
    prompt_used: str
    images: list[GenerationImage]
    cost_estimate: Optional[dict] = None
    room_measurements: list[dict] = Field(default_factory=list)


class GenerationHistoryItem(BaseModel):
    id: str
    generation_type: str = "house_plan"
    client_name: Optional[str] = None
    house_style: str = ""
    gross_area: str = ""
    num_bedrooms: int = 0
    region: str = "Center"
    division: str = ""
    thumbnail_url: Optional[str] = None
    image_count: int = 0
    created_at: str
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[str] = None
    dxf_url: Optional[str] = None


class GenerationUpdate(BaseModel):
    client_name: Optional[str] = None


# --- Floor Plan Schemas (unchanged) ---

class FloorPlanRequest(BaseModel):
    num_bedrooms: int = Field(..., ge=1, le=20, description="Number of bedrooms")
    num_bathrooms: int = Field(..., ge=1, le=20, description="Number of bathrooms")
    num_living_rooms: int = Field(1, ge=1, le=20, description="Number of living rooms")
    num_kitchens: int = Field(1, ge=1, le=20, description="Number of kitchens")
    gross_area: str = Field(..., description="Gross floor area in m² (e.g. '150')")
    kitchen_type: str = Field(..., description="Kitchen layout: 'open' or 'closed'")
    extras: list[str] = Field(default_factory=list, description="Additional room types (e.g. walk-in closet, laundry room)")
    region: Optional[str] = Field("Center", description="Cameroon target region")
    division: str = Field("", description="Cameroon target division")
    additional_preferences: Optional[str] = Field(None, description="Extra preferences for the floor plan")


class FloorPlanSpecification(BaseModel):
    num_bedrooms: int
    num_bathrooms: int
    num_living_rooms: int = 1
    num_kitchens: int = 1
    gross_area: str
    kitchen_type: str
    extras: list[str]
    region: str
    division: str = ""


class FloorPlanWorkspaceResponse(BaseModel):
    generation_id: str
    images: list[GenerationImage]
    prompt_used: str
    specification: FloorPlanSpecification
    dxf_url: Optional[str] = None
    room_measurements: list[RoomMeasurement] = Field(default_factory=list, description="Individual room dimensions")


class CleanupRequest(BaseModel):
    storage_paths: list[str]


class SingleFloorPlanViewRequest(BaseModel):
    generation_id: str
    view_type: str
    prompt: Optional[str] = None
    specification: Optional[FloorPlanSpecification] = None


class SaveFloorPlanRequest(BaseModel):
    generation_id: str
    client_name: Optional[str] = None
    images: list[GenerationImage]
    prompt_used: str
    specification: FloorPlanSpecification
    room_measurements: list[dict] = Field(default_factory=list)
