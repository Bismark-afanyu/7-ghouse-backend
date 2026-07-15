from pydantic import BaseModel


class BoqLineItem(BaseModel):
    category: str
    category_fr: str
    item: str
    item_key: str
    unit: str
    unit_key: str
    quantity: float
    unit_price: int
    line_total: int


class CostEstimate(BaseModel):
    hub_name: str
    hub_lat: float
    hub_lng: float
    distance_km: float
    line_items: list[BoqLineItem]
    material_subtotal: int
    transport_surcharge: int
    labor_cost: int
    contingency: int
    grand_total_fcfa: int
    grand_total_usd: int
    base_cost_per_m2: int
    quality_tier: str
    terrain_category: str
    foundation_adjustment_pct: float
    breakdown: list[dict]
    notes: list[str]
