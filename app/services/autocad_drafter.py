import io
import json
import asyncio
import random
from typing import List
import ezdxf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import math
import os

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.services.genai_client import get_genai_client
try:
    from svgpathtools import svg2paths
except ImportError:
    svg2paths = None

# ==========================================
# 1. DEFINE DATA STRUCTURES (Pydantic Schema)
# ==========================================

class Wall(BaseModel):
    start_x: float = Field(description="Starting X coordinate of the wall line in millimeters.")
    start_y: float = Field(description="Starting Y coordinate of the wall line in millimeters.")
    end_x: float = Field(description="Ending X coordinate of the wall line in millimeters.")
    end_y: float = Field(description="Ending Y coordinate of the wall line in millimeters.")

class RoomLabel(BaseModel):
    text: str = Field(description="Uppercase room name (e.g., 'MASTER BEDROOM', 'KITCHEN').")
    dimensions: str = Field(description="Room dimensions formatted exactly in feet, e.g., '12 x 12' or '19 x 15'.")
    center_x: float = Field(description="X coordinate for the text center anchor point in millimeters.")
    center_y: float = Field(description="Y coordinate for the text center anchor point in millimeters.")

class AssetPlacement(BaseModel):
    asset_name: str = Field(description="The specific filename of the asset to place (e.g., 'queen_bed.svg', 'door_left.svg').")
    x: float = Field(description="X coordinate to place the asset in millimeters.")
    y: float = Field(description="Y coordinate to place the asset in millimeters.")
    rotation: float = Field(description="Rotation angle in degrees (e.g., 0, 90, 180, 270).")

class Window(BaseModel):
    start_x: float = Field(description="Starting X coordinate of the window on the wall.")
    start_y: float = Field(description="Starting Y coordinate of the window on the wall.")
    end_x: float = Field(description="Ending X coordinate of the window on the wall.")
    end_y: float = Field(description="Ending Y coordinate of the window on the wall.")

class PreciseFloorPlanSchema(BaseModel):
    total_area_m2: float = Field(description="The calculated footprint area in square meters.")
    walls: List[Wall] = Field(description="Array of all structural outer boundaries and internal dividing walls.")
    windows: List[Window] = Field(description="Array of all exterior windows placed on outer walls.", default_factory=list)
    labels: List[RoomLabel] = Field(description="Array of room identification labels positioned accurately inside their spaces.")
    assets: List[AssetPlacement] = Field(description="Array of standard furniture, plumbing, and door blocks placed inside the floor plan.", default_factory=list)

# ── SVG Bounds Cache & Center Computation ─────────────────────────────────
_svg_bounds_cache: dict[str, tuple[float, float, float, float]] = {}

def _get_svg_bounds(filepath: str) -> tuple[float, float, float, float]:
    if filepath in _svg_bounds_cache:
        return _svg_bounds_cache[filepath]
    try:
        paths, _ = svg2paths(filepath)
        all_x, all_y = [], []
        for path in paths:
            for segment in path:
                t = np.linspace(0, 1, 20)
                pts = np.array([segment.point(tt) for tt in t])
                all_x.extend(pts.real)
                all_y.extend(pts.imag)
        bbox = (min(all_x), min(all_y), max(all_x), max(all_y)) if all_x else (0, 0, 100, 100)
    except Exception:
        bbox = (0, 0, 100, 100)
    _svg_bounds_cache[filepath] = bbox
    return bbox


def _svg_center_offset(filepath: str) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = _get_svg_bounds(filepath)
    return ((min_x + max_x) / 2, (min_y + max_y) / 2)


# ── Asset-to-Room Mapping ─────────────────────────────────────────────────
ASSET_ROOM_MAP = {
    "queen_bed.svg": "master bedroom",
    "single_bed.svg": "bedroom",
    "toilet.svg": "bathroom",
    "bathtub.svg": "bathroom",
    "kitchen_sink.svg": "kitchen",
    "kitchen_stove.svg": "kitchen",
    "sofa_3_seater.svg": "living",
    "dining_table_6.svg": "dining",
}

ROOM_ALIASES = {
    "master bedroom": ["master bedroom", "master", "master_bedroom"],
    "bedroom": ["bedroom", "bed"],
    "bathroom": ["bathroom", "bath"],
    "kitchen": ["kitchen", "kit"],
    "living": ["living", "living/dining", "living room", "lounge"],
    "dining": ["dining", "dining room", "dining area"],
}


def _parse_dimensions_to_mm(dim_str: str) -> tuple[float, float]:
    try:
        parts = dim_str.lower().replace('"', '').replace("'", '').split('x')
        if len(parts) == 2:
            return (float(parts[0].strip()) * 304.8, float(parts[1].strip()) * 304.8)
    except (ValueError, AttributeError):
        pass
    return (3657.6, 3657.6)


def _find_room_rectangles(labels: list[RoomLabel], room_type: str
                         ) -> list[tuple[float, float, float, float]]:
    aliases = ROOM_ALIASES.get(room_type, [room_type])
    rects = []
    for label in labels:
        if any(a in label.text.lower() for a in aliases):
            w_mm, h_mm = _parse_dimensions_to_mm(label.dimensions)
            rects.append((label.center_x - w_mm / 2, label.center_y - h_mm / 2, w_mm, h_mm))
    return rects


def _ensure_furniture_count(layout_data: PreciseFloorPlanSchema):
    """Add missing furniture assets based on room count from labels."""
    room_counts = {"bedroom": 0, "master_bedroom": 0, "bathroom": 0,
                   "kitchen": 0, "living": 0, "dining": 0}
    for label in layout_data.labels:
        t = label.text.lower()
        if "master" in t and "bed" in t:
            room_counts["master_bedroom"] += 1
        elif "bed" in t:
            room_counts["bedroom"] += 1
        elif "bath" in t:
            room_counts["bathroom"] += 1
        elif "kitchen" in t:
            room_counts["kitchen"] += 1
        if "living" in t or "lounge" in t:
            room_counts["living"] += 1
        if "dining" in t:
            room_counts["dining"] += 1

    asset_counts = {}
    for a in layout_data.assets:
        n = a.asset_name.lower()
        asset_counts[n] = asset_counts.get(n, 0) + 1

    REQUIRED = {
        "master_bedroom": [("queen_bed.svg", 1)],
        "bedroom":         [("single_bed.svg", 1)],
        "bathroom":        [("toilet.svg", 1), ("bathtub.svg", 1)],
        "kitchen":         [("kitchen_sink.svg", 1), ("kitchen_stove.svg", 1)],
        "living":          [("sofa_3_seater.svg", 1)],
        "dining":          [("dining_table_6.svg", 1)],
    }

    for room_type, count in room_counts.items():
        if room_type not in REQUIRED or count == 0:
            continue
        for asset_name, per_room in REQUIRED[room_type]:
            needed = count * per_room
            existing = asset_counts.get(asset_name, 0)
            for _ in range(max(0, needed - existing)):
                layout_data.assets.append(AssetPlacement(
                    asset_name=asset_name, x=0, y=0, rotation=0))
                asset_counts[asset_name] = asset_counts.get(asset_name, 0) + 1


def _place_assets_in_rooms(layout_data: PreciseFloorPlanSchema, margin_mm: float = 200.0):
    if not layout_data.assets:
        return
    blocks_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "cad_blocks")
    all_x = [w.start_x for w in layout_data.walls] + [w.end_x for w in layout_data.walls]
    all_y = [w.start_y for w in layout_data.walls] + [w.end_y for w in layout_data.walls]
    if not all_x:
        return
    bbox = (min(all_x), max(all_x), min(all_y), max(all_y))

    # Group assets by room type
    assets_by_room: dict[str, list[AssetPlacement]] = {}
    for asset in layout_data.assets:
        expected = ASSET_ROOM_MAP.get(asset.asset_name.lower())
        if expected is None:
            continue
        assets_by_room.setdefault(expected, []).append(asset)

    for room_type, assets in assets_by_room.items():
        rooms = _find_room_rectangles(layout_data.labels, room_type)
        random.shuffle(assets)
        if rooms:
            random.shuffle(rooms)

        for i, asset in enumerate(assets):
            filepath = os.path.join(blocks_dir, asset.asset_name)
            svg_b = _get_svg_bounds(filepath)
            svg_w = (svg_b[2] - svg_b[0]) * 10.0
            svg_h = (svg_b[3] - svg_b[1]) * 10.0

            if rooms:
                rx, ry, rw, rh = rooms[i % len(rooms)]
                min_x = rx + margin_mm + svg_w / 2
                max_x = rx + rw - margin_mm - svg_w / 2
                min_y = ry + margin_mm + svg_h / 2
                max_y = ry + rh - margin_mm - svg_h / 2
            else:
                min_x = bbox[0] + margin_mm + svg_w / 2
                max_x = bbox[1] - margin_mm - svg_w / 2
                min_y = bbox[2] + margin_mm + svg_h / 2
                max_y = bbox[3] - margin_mm - svg_h / 2

            if min_x < max_x and min_y < max_y:
                asset.x = random.uniform(min_x, max_x)
                asset.y = random.uniform(min_y, max_y)
            else:
                if rooms:
                    rx, ry, rw, rh = rooms[i % len(rooms)]
                    asset.x = rx + rw / 2
                    asset.y = ry + rh / 2
                else:
                    asset.x = (bbox[0] + bbox[1]) / 2
                    asset.y = (bbox[2] + bbox[3]) / 2


# ==========================================
# 2. RUN THE AI LOGIC LAYER (Gemini API Call)
# ==========================================

async def generate_precise_layout_data(gross_area: str, bedrooms: int, bathrooms: float, kitchen_type: str = "open", extras: List[str] = None, num_kitchens: int = 1, num_living_rooms: int = 1) -> PreciseFloorPlanSchema:
    client = get_genai_client()
    
    extras_str = ", ".join(extras) if extras else "None"
    
    prompt = f"""
    You are a professional architectural layout calculation tool.
    Generate a precise, 100% flat 2D residential floor plan based on these parameters:
    - Target Gross Area: {gross_area} m²
    - Bedrooms: {bedrooms}
    - Bathrooms: {bathrooms}
    - Kitchens: {num_kitchens}
    - Living rooms: {num_living_rooms}
    - Kitchen Type: {kitchen_type}
    - Additional Spaces: {extras_str}

    Execution Instructions:
    1. Base Unit: Coordinates must be in millimeters (mm). 1 m² = 1,000,000 mm².
    2. Origin Constraints: Start the extreme bottom-left exterior wall vertex at (0.0, 0.0).
    3. Structural Layout: Rooms must share walls seamlessly without overlapping or leaving blank interior gaps. Generate realistic overall home dimensions.
    4. Room Requirements: Include an entryway, a living/dining area, {num_kitchens} kitchen(s) ({kitchen_type}), {bedrooms} separate bedrooms, {bathrooms} separate bathrooms, and {extras_str}. Connect all spaces with logical interior circulation pathways.
    5. Text Anchor points: Place the label coordinates strictly within the middle bounding space of its respective room. Include dimensions in feet format (e.g. "12 x 12").
     6. Standard Asset Placements: You must intelligently place standard CAD assets inside the rooms. 
        - Valid `asset_name`s are ONLY the following exactly: 'queen_bed.svg', 'single_bed.svg', 'sofa_3_seater.svg', 'dining_table_6.svg', 'toilet.svg', 'bathtub.svg', 'kitchen_sink.svg', 'kitchen_stove.svg', 'door_left.svg', 'door_right.svg'.
        - The (x, y) coordinate for each asset represents its CENTER point (not top-left corner).
        - Real-world sizes after 10x SVG scaling: queen_bed=1600x2000mm, single_bed=900x2000mm, toilet=1000x1000mm, bathtub=1500x700mm, kitchen_sink=800x500mm, kitchen_stove=600x600mm, sofa_3_seater=2000x800mm, dining_table_6=1600x1000mm, doors=1000x1000mm.
        - Use these sizes to place assets with proper clearance from walls (at least 200mm).
        - Place doors exactly on walls to act as room entrances.
        - Place beds in bedrooms.
        - Place the sofa and dining table in the living/dining spaces.
        - Place toilet and bathtub in bathrooms.
        - Place sink and stove in each kitchen.
    7. Windows: Distribute realistically sized windows on exterior walls to let light into the bedrooms, living room, and kitchen.
    """
    
    def _call():
        return client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PreciseFloorPlanSchema,
                temperature=0.1,
            ),
        )
        
    response = await asyncio.to_thread(_call)
    
    if not response.text:
        raise Exception("Failed to generate precise floor plan data")
        
    return PreciseFloorPlanSchema.model_validate_json(response.text)

# ==========================================
# 3. GENERATE APP IMAGE PREVIEW (Matplotlib)
# ==========================================

async def render_preview_image(layout_data: PreciseFloorPlanSchema) -> bytes:
    def _render():
        fig, ax = plt.subplots(figsize=(12, 12))
        ax.set_facecolor('#F8FAFC')
        
        # Determine max grid size
        max_x = max([w.end_x for w in layout_data.walls] + [w.start_x for w in layout_data.walls], default=10000)
        max_y = max([w.end_y for w in layout_data.walls] + [w.start_y for w in layout_data.walls], default=10000)
        
        # 1. Draw Grid
        for x in np.arange(0, max_x + 2000, 1000):
            ax.axvline(x, color='#E2E8F0', linewidth=0.5, zorder=0)
        for y in np.arange(0, max_y + 2000, 1000):
            ax.axhline(y, color='#E2E8F0', linewidth=0.5, zorder=0)

        # 2. Draw Walls (Black Outline + White Core)
        for wall in layout_data.walls:
            ax.plot([wall.start_x, wall.end_x], [wall.start_y, wall.end_y], color='black', linewidth=6, solid_capstyle='butt', zorder=1)
            ax.plot([wall.start_x, wall.end_x], [wall.start_y, wall.end_y], color='white', linewidth=3, solid_capstyle='butt', zorder=2)
            
        # 3. Draw Windows
        if hasattr(layout_data, 'windows'):
            for win in layout_data.windows:
                ax.plot([win.start_x, win.end_x], [win.start_y, win.end_y], color='black', linewidth=6, solid_capstyle='butt', zorder=3)
                ax.plot([win.start_x, win.end_x], [win.start_y, win.end_y], color='white', linewidth=4, solid_capstyle='butt', zorder=4)
                ax.plot([win.start_x, win.end_x], [win.start_y, win.end_y], color='black', linewidth=1, solid_capstyle='butt', zorder=5)

        # 4. Inject text annotations with white background
        for label in layout_data.labels:
            text_str = f"{label.text}\n{label.dimensions}" if getattr(label, 'dimensions', None) else label.text
            bg_w, bg_h = 1400, 500
            ax.add_patch(plt.Rectangle(
                (label.center_x - bg_w / 2, label.center_y - bg_h / 2),
                bg_w, bg_h,
                facecolor='white', edgecolor='none', zorder=7.5
            ))
            ax.text(label.center_x, label.center_y, text_str,
                    fontsize=9, fontweight='normal', ha='center', va='center', color='black', zorder=8)
            
        # 5. Draw placed assets with White Masks
        if svg2paths and getattr(layout_data, 'assets', None):
            blocks_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "cad_blocks")
            _ensure_furniture_count(layout_data)
            _place_assets_in_rooms(layout_data)
            for asset in layout_data.assets:
                filepath = os.path.join(blocks_dir, asset.asset_name)
                if not os.path.exists(filepath):
                    continue
                try:
                    paths, _ = svg2paths(filepath)
                    theta = math.radians(asset.rotation)
                    cos_t = math.cos(theta)
                    sin_t = math.sin(theta)
                    scale_factor = 10.0
                    
                    svg_cx, svg_cy = _svg_center_offset(filepath)
                    
                    all_x = []
                    all_y = []
                    
                    for path in paths:
                        for segment in path:
                            t = np.linspace(0, 1, 15)
                            pts = np.array([segment.point(tt) for tt in t])
                            centered = pts - (svg_cx + 1j * svg_cy)
                            rx = centered.real * scale_factor
                            ry = centered.imag * scale_factor
                            
                            rot_x = rx * cos_t - ry * sin_t
                            rot_y = rx * sin_t + ry * cos_t
                            
                            final_x = rot_x + asset.x
                            final_y = rot_y + asset.y
                            
                            all_x.extend(final_x)
                            all_y.extend(final_y)
                            
                            ax.plot(final_x, final_y, color='black', linewidth=1.2, solid_capstyle='round', zorder=7)
                            
                    if all_x and all_y:
                        is_door = 'door' in asset.asset_name.lower()
                        if not is_door:
                            min_x, max_x_a = min(all_x), max(all_x)
                            min_y, max_y_a = min(all_y), max(all_y)
                            pad = 50
                            ax.add_patch(plt.Rectangle((min_x - pad, min_y - pad), 
                                                       (max_x_a - min_x) + 2*pad, 
                                                       (max_y_a - min_y) + 2*pad, 
                                                       facecolor='white', edgecolor='none', zorder=6))
                except Exception as e:
                    print(f"Failed to draw asset {asset.asset_name}: {e}")

        # Clean the viewport to look like a clean blueprint sheet
        ax.set_aspect('equal')
        ax.axis('off')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='#F8FAFC')
        plt.close(fig)
        return buf.getvalue()
        
    return await asyncio.to_thread(_render)

# ==========================================
# 4. GENERATE AUTOCAD EXPORT FILE (ezdxf)
# ==========================================

async def render_autocad_dxf(layout_data: PreciseFloorPlanSchema) -> bytes:
    def _render():
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        
        # Create distinct standardized CAD layers
        doc.layers.new(name='A-WALL', dxfattribs={'color': 7})      # White/Black lines
        doc.layers.new(name='A-TEXT', dxfattribs={'color': 2})      # Yellow annotations
        
        # Draw vector paths in millimeter scaling
        for wall in layout_data.walls:
            msp.add_line((wall.start_x, wall.start_y), (wall.end_x, wall.end_y), dxfattribs={'layer': 'A-WALL'})
            
        # Add native vector MTEXT typography entities
        for label in layout_data.labels:
            mtext = msp.add_mtext(label.text, dxfattribs={'layer': 'A-TEXT'})
            mtext.dxf.char_height = 200  # Set clean default font height to 200mm
            mtext.set_placement((label.center_x, label.center_y), align=ezdxf.enums.MTextEntityAlignment.CENTER)
            
        buf = io.StringIO()
        doc.write(buf)
        return buf.getvalue().encode('utf-8')
        
    return await asyncio.to_thread(_render)
