import math
import logging
from typing import Optional

from app.data.cameroon_materials import get_material_price, MATERIALS
from app.data.cameroon_locations import SUPPLY_HUBS, get_transport_multiplier
from app.schemas.cost_estimate import CostEstimate, BoqLineItem
from app.services.geocoding import geocode_location

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _find_nearest_hub(lat: float, lng: float) -> tuple[str, float, float, str]:
    nearest = None
    nearest_dist = float("inf")
    for key, hub in SUPPLY_HUBS.items():
        d = haversine_km(lat, lng, hub["lat"], hub["lng"])
        if d < nearest_dist:
            nearest_dist = d
            nearest = (key, hub["lat"], hub["lng"], hub["name"])
    return nearest or ("douala", 4.0511, 9.7679, "Douala")


async def _resolve_hub_coords(
    material_source_hub: str,
    custom_hub_name: Optional[str],
    custom_hub_lat: Optional[float],
    custom_hub_lng: Optional[float],
    site_lat: Optional[float],
    site_lng: Optional[float],
) -> tuple[float, float, str]:
    key = material_source_hub.strip().lower() if material_source_hub else ""

    if key == "custom" and custom_hub_lat is not None and custom_hub_lng is not None:
        name = custom_hub_name or "Custom Location"
        return custom_hub_lat, custom_hub_lng, name

    if key == "custom" and custom_hub_name:
        coords = await geocode_location(custom_hub_name)
        if coords:
            return coords[0], coords[1], custom_hub_name

    if key in SUPPLY_HUBS:
        hub = SUPPLY_HUBS[key]
        return hub["lat"], hub["lng"], hub["name"]

    if site_lat is not None and site_lng is not None:
        _, hub_lat, hub_lng, hub_name = _find_nearest_hub(site_lat, site_lng)
        return hub_lat, hub_lng, hub_name

    hub = SUPPLY_HUBS["douala"]
    return hub["lat"], hub["lng"], hub["name"]


async def estimate_construction_cost(
    gross_area: float,
    num_bedrooms: int,
    num_bathrooms: float,
    roof_type: str,
    is_multi_story: bool,
    num_stories: int,
    quality_tier: str,
    region: str,
    division: Optional[str],
    site_lat: Optional[float],
    site_lng: Optional[float],
    material_source_hub: str,
    custom_hub_name: Optional[str],
    custom_hub_lat: Optional[float],
    custom_hub_lng: Optional[float],
    terrain_category: str = "flat",
) -> CostEstimate:
    stories = max(1, num_stories)
    is_pitched = roof_type.lower() not in ("flat", "slab")

    quality = quality_tier if quality_tier in ("basic", "standard", "premium") else "standard"
    transport_mul = get_transport_multiplier(region, division)

    def price(material_id: str) -> int:
        return get_material_price(material_id, quality) * transport_mul

    hub_lat, hub_lng, hub_name = await _resolve_hub_coords(
        material_source_hub, custom_hub_name, custom_hub_lat, custom_hub_lng, site_lat, site_lng,
    )

    distance_km = 0.0
    if site_lat is not None and site_lng is not None:
        distance_km = haversine_km(site_lat, site_lng, hub_lat, hub_lng)

    line_items: list[BoqLineItem] = []
    cat_keys = {}
    for mc in MATERIALS:
        cat_keys[mc["category"]] = (mc["category"], mc["category_fr"])

    def add_item(cat: str, item_key: str, unit: str, quantity: float, unit_price: int):
        if quantity <= 0:
            return
        cat_name, cat_fr = cat_keys.get(cat, (cat, cat))
        item_name = _material_name(item_key)
        line_items.append(BoqLineItem(
            category=cat_name,
            category_fr=cat_fr,
            item=item_name,
            item_key=item_key,
            unit=unit,
            unit_key=unit,
            quantity=round(quantity, 2),
            unit_price=round(unit_price),
            line_total=round(quantity * unit_price),
        ))

    def _material_name(mid: str) -> str:
        for mc in MATERIALS:
            for it in mc["items"]:
                if it["id"] == mid:
                    return it["name"]
        return mid

    concrete_vol = gross_area * 0.12
    gravel_vol = concrete_vol * 0.55
    sand_vol = concrete_vol * 0.30
    foundation_cement = concrete_vol * 7
    foundation_steel = gross_area * 4.5
    excavation_vol = gross_area * 0.25

    add_item("Foundation & Concrete", "cement_foundation", "bags", foundation_cement, price("cement"))
    add_item("Foundation & Concrete", "gravel_5_15", "m3", gravel_vol, price("gravel"))
    add_item("Foundation & Concrete", "sharp_sand", "m3", sand_vol, price("river_sand"))
    add_item("Foundation & Concrete", "steel_rebar_avg", "kg", foundation_steel, price("steel_kg"))
    add_item("Foundation & Concrete", "binding_wire", "kg", foundation_steel * 0.015, price("binding_wire"))
    add_item("Foundation & Concrete", "polyane_dpc", "m2", gross_area * 1.05, price("polyane"))
    add_item("Foundation & Concrete", "excavation", "m3", excavation_vol, 2500)

    slab_vol = gross_area * 0.15 * stories
    col_beam_vol = gross_area * 0.04 * stories
    struct_concrete_vol = slab_vol + col_beam_vol
    struct_steel = gross_area * 18 * stories

    add_item("Foundation & Concrete", "cement_slab_beams", "bags", struct_concrete_vol * 7, price("cement"))
    add_item("Foundation & Concrete", "gravel_struct", "m3", struct_concrete_vol * 0.55, price("gravel"))
    add_item("Foundation & Concrete", "sharp_sand_struct", "m3", struct_concrete_vol * 0.30, price("river_sand"))
    add_item("Foundation & Concrete", "steel_12mm", "bars", struct_steel * 0.4 / 9.4, price("steel_12mm"))
    add_item("Foundation & Concrete", "steel_10mm", "bars", struct_steel * 0.6 / 6.2, price("steel_10mm"))
    add_item("Foundation & Concrete", "binding_wire_struct", "kg", struct_steel * 0.015, price("binding_wire"))
    add_item("Foundation & Concrete", "formwork_plywood", "sheets", gross_area * stories * 0.04, price("formwork_plywood"))
    add_item("Foundation & Concrete", "formwork_timber", "lm", gross_area * stories * 0.5, price("formwork_timber"))
    add_item("Blockwork & Masonry", "wire_mesh", "rolls", gross_area * stories * 0.015, price("wire_mesh"))

    wall_area = gross_area * 0.85 * stories
    block_count = wall_area * 10
    mortar_vol = wall_area * 0.012
    mortar_cement = mortar_vol * 500 / 50
    mortar_sand = mortar_vol * 1.2

    add_item("Blockwork & Masonry", "block_9inch", "blocks", block_count, price("block_9inch"))
    add_item("Blockwork & Masonry", "cement_masonry", "bags", mortar_cement, price("cement_masonry"))
    add_item("Blockwork & Masonry", "pit_sand", "m3", mortar_sand, price("pit_sand"))

    roof_area = gross_area * (1.35 if is_pitched else 1.05)
    truss_length = roof_area * 2.5
    ridge_length = math.sqrt(gross_area * 4) * (1.0 if is_pitched else 0)

    add_item("Roofing & Ceiling", "roofing_sheets", "m2", roof_area * 1.05, price("roofing_aluminum"))
    add_item("Roofing & Ceiling", "ridge_caps", "lm", ridge_length * 1.1, price("ridge_cap"))
    add_item("Roofing & Ceiling", "roof_timber", "lm", truss_length * 1.1, price("timber_truss"))
    add_item("Roofing & Ceiling", "roofing_nails", "kg", roof_area * 0.08, price("roofing_nails"))
    add_item("Roofing & Ceiling", "ceiling_plasterboard", "sheets", gross_area * 0.35, price("ceiling_board"))
    add_item("Roofing & Ceiling", "ceiling_timber", "lm", gross_area * 1.8, price("ceiling_timber"))
    add_item("Roofing & Ceiling", "insulation_foil", "m2", gross_area * 1.05, price("insulation_foil"))
    add_item("Roofing & Ceiling", "gutter_downpipes", "lm", math.sqrt(gross_area) * 4 * 1.1, price("gutter"))

    door_count = num_bedrooms + math.ceil(num_bathrooms) + 2
    window_area = gross_area * 0.12

    add_item("Doors & Windows", "door_room", "each", door_count, price("door_room"))
    add_item("Doors & Windows", "door_main", "each", 1, price("door_main"))
    add_item("Doors & Windows", "door_bathroom", "each", math.ceil(num_bathrooms), price("door_bathroom"))
    add_item("Doors & Windows", "door_kitchen", "each", 1, price("door_kitchen"))
    add_item("Doors & Windows", "door_hardware", "sets", door_count + 2, price("door_hardware"))
    add_item("Doors & Windows", "window_aluminum", "m2", window_area, price("window_aluminum"))
    add_item("Doors & Windows", "window_ironmongery", "sets", round(window_area / 1.5), price("window_ironmongery"))

    floor_tile_area = gross_area * 0.85
    wall_tile_area = num_bathrooms * 18 + 12
    plaster_area = wall_area * 2
    plaster_cement = plaster_area * 0.012 * 500 / 50

    add_item("Finishing & Tiling", "tile_floor", "m2", floor_tile_area * 1.05, price("tile_floor_standard"))
    add_item("Finishing & Tiling", "tile_wall", "m2", wall_tile_area * 1.05, price("tile_wall_standard"))
    add_item("Finishing & Tiling", "tile_adhesive", "bags", (floor_tile_area + wall_tile_area) * 0.1, price("tile_adhesive"))
    add_item("Finishing & Tiling", "tile_grout", "pcs", round((floor_tile_area + wall_tile_area) * 0.01 + 1), price("tile_grout"))
    add_item("Finishing & Tiling", "cement_plaster", "bags", plaster_cement, price("cement_plaster"))
    add_item("Finishing & Tiling", "skirting", "lm", math.sqrt(gross_area) * 4 * 1.2, price("skirting"))

    paint_area = plaster_area * 0.6
    paint_liters = paint_area / 10
    primer_liters = paint_area / 15

    add_item("Painting", "paint_interior", "pails", math.ceil(paint_liters / 10), price("paint_interior"))
    add_item("Painting", "paint_exterior", "pails", math.ceil(gross_area * 0.15 / 10 + 1), price("paint_exterior"))
    add_item("Painting", "paint_primer", "pails", math.ceil(primer_liters / 10), price("paint_primer"))
    add_item("Painting", "putty", "bags", round(paint_area * 0.02), price("putty"))

    add_item("Plumbing & Sanitary", "wc_suite", "each", num_bathrooms + 1, price("wc_suite"))
    add_item("Plumbing & Sanitary", "washbasin", "each", num_bathrooms + 1, price("washbasin"))
    add_item("Plumbing & Sanitary", "shower_set", "each", num_bathrooms, price("shower_set"))
    add_item("Plumbing & Sanitary", "kitchen_sink", "each", 1, price("kitchen_sink"))
    add_item("Plumbing & Sanitary", "faucet", "each", num_bathrooms * 2 + 2, price("faucet"))
    add_item("Plumbing & Sanitary", "pvc_pipe_40mm", "lm", gross_area * 0.15, price("pvc_pipe_40mm"))
    add_item("Plumbing & Sanitary", "pvc_pipe_50mm", "lm", gross_area * 0.1, price("pvc_pipe_50mm"))
    add_item("Plumbing & Sanitary", "ppr_pipe", "lm", gross_area * 0.2, price("ppr_pipe"))
    add_item("Plumbing & Sanitary", "pipe_fittings", "pcs", round(gross_area * 0.25), price("pipe_fittings"))
    add_item("Plumbing & Sanitary", "water_tank", "each", 1, price("water_tank_1000l"))

    add_item("Electrical", "cable_1_5mm", "lm", gross_area * 0.8, price("cable_1_5mm"))
    add_item("Electrical", "cable_2_5mm", "lm", gross_area * 1.2, price("cable_2_5mm"))
    add_item("Electrical", "cable_4mm", "lm", gross_area * 0.3, price("cable_4mm"))
    add_item("Electrical", "conduit_pvc", "lm", gross_area * 1.0, price("conduit_pvc"))
    add_item("Electrical", "socket_outlet", "each", round(gross_area * 0.06), price("socket_outlet"))
    add_item("Electrical", "light_switch", "each", round(gross_area * 0.05), price("light_switch"))
    add_item("Electrical", "breaker", "each", round(gross_area * 0.02 + 2), price("breaker"))
    add_item("Electrical", "breaker_box", "each", 1, price("breaker_box"))
    add_item("Electrical", "light_fitting", "each", round(gross_area * 0.04 + 2), price("light_fitting"))
    add_item("Electrical", "conduit_fittings", "pcs", round(gross_area * 0.15), price("conduit_fittings"))

    add_item("Miscellaneous & Labour", "nails_assorted", "kg", gross_area * 0.15, price("nails_assorted"))
    add_item("Miscellaneous & Labour", "waterproofing", "m2", gross_area * 0.3, price("waterproofing"))

    material_subtotal = sum(i.line_total for i in line_items)

    transport_surcharge = round((material_subtotal * (transport_mul - 1)) / transport_mul)

    distance_surcharge = 0
    if distance_km > 50:
        distance_surcharge = round(material_subtotal * (distance_km / 500) * 0.03)
        transport_surcharge += distance_surcharge

    labor_rate = 0.20 if quality == "basic" else (0.23 if quality == "standard" else 0.25)
    labor_cost = round(material_subtotal * labor_rate)

    terrain_factors = {"flat": 0.0, "gentle": 0.03, "moderate": 0.07, "steep": 0.12}
    foundation_adj_pct = terrain_factors.get(terrain_category, 0.0)
    terrain_adjustment = round(material_subtotal * foundation_adj_pct)

    contingency_rate = 0.10
    contingency_base = material_subtotal + transport_surcharge + labor_cost + terrain_adjustment
    contingency = round(contingency_base * contingency_rate)

    grand_total = contingency_base + contingency
    grand_total_usd = round(grand_total / 610)

    base_cost_per_m2 = round(grand_total / gross_area) if gross_area > 0 else 0

    breakdown = [
        {"label": "Materials", "label_fr": "Matériaux", "pct": round((material_subtotal / grand_total) * 100), "amount": material_subtotal},
        {"label": "Transport", "label_fr": "Transport", "pct": round((transport_surcharge / grand_total) * 100), "amount": transport_surcharge},
        {"label": "Labour", "label_fr": "Main-d'œuvre", "pct": round((labor_cost / grand_total) * 100), "amount": labor_cost},
        {"label": "Terrain Adjustment", "label_fr": "Ajustement Terrain", "pct": round((terrain_adjustment / grand_total) * 100), "amount": terrain_adjustment},
        {"label": "Contingency", "label_fr": "Imprévus", "pct": round((contingency / grand_total) * 100), "amount": contingency},
    ]

    notes = []
    if distance_km > 0:
        notes.append(f"Material source hub: {hub_name} ({distance_km:.0f} km from building site)")
    if distance_surcharge > 0:
        notes.append(f"Distance surcharge applied: {distance_surcharge:,} FCFA ({distance_km:.0f} km)")
    if foundation_adj_pct > 0:
        notes.append(f"Terrain-based foundation adjustment: +{foundation_adj_pct * 100:.0f}%")
    notes.append(f"Exchange rate: 1 USD ≈ 610 FCFA")

    return CostEstimate(
        hub_name=hub_name,
        hub_lat=hub_lat,
        hub_lng=hub_lng,
        distance_km=round(distance_km, 1),
        line_items=line_items,
        material_subtotal=material_subtotal,
        transport_surcharge=transport_surcharge,
        labor_cost=labor_cost,
        contingency=contingency,
        grand_total_fcfa=grand_total,
        grand_total_usd=grand_total_usd,
        base_cost_per_m2=base_cost_per_m2,
        quality_tier=quality,
        terrain_category=terrain_category,
        foundation_adjustment_pct=foundation_adj_pct,
        breakdown=breakdown,
        notes=notes,
    )
