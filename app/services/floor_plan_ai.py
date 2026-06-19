"""
Floor plan renderer: Imagen 4.0 AI primary, PIL fallback.
"""
import asyncio
import io
import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.db.firebase import settings
from app.services.floor_plan_layout import FloorPlanLayout, RoomLayout


# ── PIL Fallback Renderer ───────────────────────────────────────────────────

WALL_THICKNESS_CM = 15.0
ROOM_COLORS = {
    'bedroom': '#DCEEFB', 'master_bedroom': '#B8DCF0', 'kitchen': '#FFF3CD',
    'bathroom': '#D1ECF1', 'living': '#FDEBD0', 'dining': '#E8DAEF',
    'hallway': '#EAECEE', 'hall': '#EAECEE', 'utility': '#D5F5E3',
    'default': '#FFFFFF',
}


def _room_color(room: RoomLayout) -> str:
    rt = (room.room_type or '').lower()
    for key, color in ROOM_COLORS.items():
        if key in rt:
            return color
    name = (room.name or '').lower()
    for key, color in ROOM_COLORS.items():
        if key in name:
            return color
    return ROOM_COLORS['default']


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _render_fallback(layout: FloorPlanLayout, annotated: bool = False) -> bytes:
    """Render a clean floor plan using PIL only."""
    margin_cm = max(layout.total_width_cm, layout.total_height_cm) * 0.25
    total_w = layout.total_width_cm + margin_cm * 2
    total_h = layout.total_height_cm + margin_cm * 2

    scale = min(2400 / total_w, 1800 / total_h)
    img_w = int(total_w * scale)
    img_h = int(total_h * scale)

    img = Image.new("RGB", (img_w, img_h), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    try:
        font_code = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(14, int(18 * scale / 10)))
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(10, int(13 * scale / 10)))
        font_area = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(8, int(10 * scale / 10)))
        font_dim = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(8, int(10 * scale / 10)))
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(12, int(16 * scale / 10)))
    except OSError:
        font_code = ImageFont.load_default()
        font_name = font_code
        font_area = font_code
        font_dim = font_code
        font_title = font_code

    def tx(cm):
        return int((cm + margin_cm) * scale)

    def ty(cm):
        return int((cm + margin_cm) * scale)

    # Draw room fills
    for room in layout.rooms:
        x1, y1 = tx(room.x_cm), ty(room.y_cm)
        x2, y2 = tx(room.x_cm + room.width_cm), ty(room.y_cm + room.height_cm)
        color = _hex_to_rgb(_room_color(room))
        draw.rectangle([x1, y1, x2, y2], fill=color, outline=None)

    # Draw double-line walls
    ht = WALL_THICKNESS_CM / 2
    drawn_walls = set()
    for room in layout.rooms:
        x1, y1 = room.x_cm, room.y_cm
        x2, y2 = x1 + room.width_cm, y1 + room.height_cm

        for (wx1, wy1), (wx2, wy2) in [
            ((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
            ((x1, y2), (x2, y2)), ((x1, y1), (x1, y2)),
        ]:
            key = (round(min(wx1, wx2), 1), round(min(wy1, wy2), 1),
                   round(max(wx1, wx2), 1), round(max(wy1, wy2), 1))
            if key in drawn_walls:
                continue
            drawn_walls.add(key)

            is_h = abs(wy1 - wy2) < 0.01
            if is_h:
                sy = ty(wy1)
                draw.line([tx(wx1), sy - int(ht * scale), tx(wx2), sy - int(ht * scale)],
                          fill="#2c3e50", width=max(1, int(scale * 0.15)))
                draw.line([tx(wx1), sy + int(ht * scale), tx(wx2), sy + int(ht * scale)],
                          fill="#2c3e50", width=max(1, int(scale * 0.15)))
            else:
                sx = tx(wx1)
                draw.line([sx - int(ht * scale), ty(wy1), sx - int(ht * scale), ty(wy2)],
                          fill="#2c3e50", width=max(1, int(scale * 0.15)))
                draw.line([sx + int(ht * scale), ty(wy1), sx + int(ht * scale), ty(wy2)],
                          fill="#2c3e50", width=max(1, int(scale * 0.15)))

    # Draw room labels
    for room in layout.rooms:
        cx = tx(room.x_cm + room.width_cm / 2)
        cy = ty(room.y_cm + room.height_cm / 2)
        code = getattr(room, 'room_code', '') or ''
        area_m2 = (room.width_cm * room.height_cm) / 10000

        if code:
            draw.text((cx, cy - int(12 * scale / 10)), code, font=font_code,
                      fill="#1a1a1a", anchor="mm")
            draw.text((cx, cy + int(4 * scale / 10)), room.name, font=font_name,
                      fill="#333333", anchor="mm")
            draw.text((cx, cy + int(16 * scale / 10)), f"{area_m2:.1f} m\u00b2",
                      font=font_area, fill="#666666", anchor="mm")
        else:
            draw.text((cx, cy - int(6 * scale / 10)), room.name, font=font_name,
                      fill="#1a1a1a", anchor="mm")
            draw.text((cx, cy + int(8 * scale / 10)), f"{area_m2:.1f} m\u00b2",
                      font=font_area, fill="#666666", anchor="mm")

    if annotated:
        # Overall dimensions
        min_x = min(r.x_cm for r in layout.rooms)
        max_x = max(r.x_cm + r.width_cm for r in layout.rooms)
        min_y = min(r.y_cm for r in layout.rooms)
        max_y = max(r.y_cm + r.height_cm for r in layout.rooms)
        total_w_m = (max_x - min_x) / 100
        total_h_m = (max_y - min_y) / 100

        dim_y = ty(max_y) + int(margin_cm * scale * 0.35)
        draw.text(((tx(min_x) + tx(max_x)) // 2, dim_y),
                  f"{total_w_m:.2f} m", font=font_dim, fill="#c0392b", anchor="mt")
        draw.line([tx(min_x), dim_y - 4, tx(max_x), dim_y - 4], fill="#c0392b", width=1)

        dim_x = tx(min_x) - int(margin_cm * scale * 0.35)
        draw.text((dim_x, (ty(min_y) + ty(max_y)) // 2),
                  f"{total_h_m:.2f} m", font=font_dim, fill="#c0392b", anchor="mm")

        # Title
        title_y = ty(max_y) + int(margin_cm * scale * 0.6)
        draw.text(((tx(min_x) + tx(max_x)) // 2, title_y),
                  "FLOOR PLAN - 7G House Project", font=font_title,
                  fill="#2c3e50", anchor="mt")
        draw.text(((tx(min_x) + tx(max_x)) // 2, title_y + int(18 * scale / 10)),
                  f"Scale 1:100 | {datetime.date.today().isoformat()}",
                  font=font_area, fill="#666666", anchor="mt")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


# ── AI Prompt Builder ───────────────────────────────────────────────────────

def _build_floor_plan_prompt(layout: FloorPlanLayout, annotated: bool = False) -> str:
    """Build a detailed architectural prompt for Imagen from layout data."""
    room_descriptions = []
    for room in layout.rooms:
        w_m = room.width_cm / 100
        h_m = room.height_cm / 100
        area_m2 = w_m * h_m
        code = getattr(room, 'room_code', '') or ''
        room_descriptions.append(
            f"- {code} {room.name}: {w_m:.1f}m x {h_m:.1f}m ({area_m2:.1f}m\u00b2)"
        )

    rooms_text = "\n".join(room_descriptions)
    total_w = layout.total_width_cm / 100
    total_h = layout.total_height_cm / 100
    total_area = total_w * total_h

    style_instruction = ""
    if annotated:
        style_instruction = (
            "Include dimension lines with measurements in meters along the exterior walls. "
            "Add a professional title block in the bottom-right corner reading "
            "'FLOOR PLAN - 7G House Project' with 'Scale 1:100' and today's date. "
            "Add a north arrow indicator. "
            "Add a graphic scale bar at the bottom-left. "
            "Add a legend in the top-right explaining symbols for walls, doors, and windows."
        )

    return (
        "Generate a professional architectural 2D floor plan drawing for a single-story "
        "residential house.\n\n"
        "STYLE: Clean black-and-white technical blueprint drawing with thin black lines on "
        "white background. Architectural drafting style as produced by CAD software. "
        "No colors, no shading, no 3D effects. Pure technical line drawing.\n\n"
        f"BUILDING DIMENSIONS: {total_w:.1f}m wide x {total_h:.1f}m deep "
        f"({total_area:.1f}m\u00b2)\n\n"
        f"ROOMS (all rooms must tile perfectly within the building rectangle with no gaps "
        f"or overlaps):\n{rooms_text}\n\n"
        "WALLS: Draw walls as double parallel lines (15cm thick) with solid black fill. "
        "Interior walls separate rooms, exterior walls form the building perimeter.\n\n"
        "DOORS: Draw each door as a gap in the wall with a thin dashed 90-degree swing arc. "
        "Label D01, D02, D03... in small text. Place one door per room.\n\n"
        "WINDOWS: Draw each window as three parallel thin lines filling the wall thickness. "
        "Label W01, W02, W03... in small text outside the building. Exterior walls only.\n\n"
        "ROOM LABELS centered in each room: Room code in bold (LR1, MBR1, KIT1, BR1, BA1), "
        "room name below, area in small text below name.\n\n"
        f"{style_instruction}\n\n"
        "All text must be legible. All rooms must be properly labeled."
    )


# ── Main Entry Point ────────────────────────────────────────────────────────

async def render_floor_plan_ai(
    layout: FloorPlanLayout,
    annotated: bool = False,
) -> Optional[bytes]:
    """
    Generate a floor plan image.
    Tries Imagen 4.0 first, falls back to PIL renderer.

    Returns:
        PNG image as bytes, or None on total failure.
    """
    # Try Imagen first
    try:
        from google import genai
        from google.genai import types

        api_key = settings.GEMINI_API_KEY
        if api_key:
            client = genai.Client(api_key=api_key)
            prompt = _build_floor_plan_prompt(layout, annotated)
            print(f"[FloorPlanAI] Trying Imagen (annotated={annotated})...")

            def call_imagen():
                return client.models.generate_images(
                    model="imagen-4.0-generate-001",
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/png",
                        aspect_ratio="16:9",
                    ),
                )

            response = await asyncio.to_thread(call_imagen)
            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                print(f"[FloorPlanAI] Imagen OK: {len(img_bytes)} bytes")
                return img_bytes
            print("[FloorPlanAI] Imagen returned no images, falling back to PIL")
        else:
            print("[FloorPlanAI] No GEMINI_API_KEY, using PIL fallback")
    except Exception as e:
        print(f"[FloorPlanAI] Imagen failed: {e}, falling back to PIL")

    # PIL fallback
    print(f"[FloorPlanAI] Using PIL fallback renderer (annotated={annotated})")
    img_bytes = await asyncio.to_thread(_render_fallback, layout, annotated)
    print(f"[FloorPlanAI] PIL fallback: {len(img_bytes)} bytes")
    return img_bytes
