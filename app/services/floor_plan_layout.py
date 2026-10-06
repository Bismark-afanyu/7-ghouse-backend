import asyncio
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Optional

_LAYOUT_CACHE: dict = {}

ROOM_CODE_MAP = {
    "living": "LR",
    "living/dining": "LR",
    "dining": "DIN",
    "kitchen": "KIT",
    "master_bedroom": "MBR",
    "bedroom": "BR",
    "bathroom": "BA",
    "hallway": "HL",
    "hall": "HL",
    "corridor": "HL",
    "utility": "UT",
    "laundry": "LND",
    "storage": "STO",
    "pantry": "PNT",
    "garage": "GAR",
    "office": "OFF",
    "study": "STU",
    "other": "OT",
}


@dataclass
class WallOpening:
    wall_side: str
    center_cm: float
    width_cm: float
    height_cm: float
    sill_height_cm: float


@dataclass
class RoomLayout:
    name: str
    room_type: str
    x_cm: float
    y_cm: float
    width_cm: float
    height_cm: float
    windows: list[WallOpening] = None
    doors: list[WallOpening] = None
    room_code: str = ""


@dataclass
class FloorPlanLayout:
    rooms: list[RoomLayout]
    total_width_cm: float
    total_height_cm: float
    source: str = "deterministic"
    wall_height_cm: float = 300.0
    roof_type: str = "gable"
    roof_pitch_degrees: float = 30.0
    foundation_type: str = "slab"
    num_stories: int = 1
    ridge_runs_width: bool = True

    @property
    def total_area_m2(self) -> float:
        return self.total_width_cm * self.total_height_cm / 10000


async def generate_floor_plan_layout(
    num_bedrooms: int = 3,
    num_bathrooms: int = 2,
    kitchen_type: str = "open",
    extras: Optional[list[str]] = None,
    gross_area: str = "150",
    land_length: Optional[float] = None,
    land_width: Optional[float] = None,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
) -> FloorPlanLayout:
    extras = extras or []

    error = validate_feasibility(num_bedrooms, num_bathrooms, kitchen_type, extras, gross_area, num_kitchens=num_kitchens, num_living_rooms=num_living_rooms)
    if error:
        print(f"Pre-flight validation: {error}")
        area_m2 = max(float(gross_area), 30.0)
        layout = _deterministic_layout(num_bedrooms, num_bathrooms, kitchen_type, extras, gross_area, land_length, land_width, num_kitchens=num_kitchens, num_living_rooms=num_living_rooms)
        _add_building_openings(layout)
        _assign_room_codes(layout)
        return layout

    ck = _cache_key(num_bedrooms, num_bathrooms, kitchen_type, extras, gross_area, land_length, land_width, num_kitchens=num_kitchens, num_living_rooms=num_living_rooms)
    cached = _get_cached(ck)
    if cached is not None:
        print(f"Cache hit for config {ck}")
        return _deep_copy_layout(cached)

    layout = await _try_gemini_layout_multi(
        num_bedrooms, num_bathrooms, kitchen_type, extras, gross_area,
        land_length=land_length, land_width=land_width,
        num_kitchens=num_kitchens, num_living_rooms=num_living_rooms,
    )

    if layout is not None and _validate_layout(layout):
        layout = _self_heal_layout(layout)
        _add_building_openings(layout)
        _assign_room_codes(layout)
        if _layout_quality_ok(layout):
            _set_cache(ck, layout)
            return layout
        print("[Layout] AI layout rejected by quality gate (fill/aspect/size); using deterministic grid")
        layout = None

    layout = _deterministic_layout(num_bedrooms, num_bathrooms, kitchen_type, extras, gross_area, land_length, land_width, num_kitchens=num_kitchens, num_living_rooms=num_living_rooms)

    layout = _deterministic_layout(num_bedrooms, num_bathrooms, kitchen_type, extras, gross_area, land_length, land_width, num_kitchens=num_kitchens, num_living_rooms=num_living_rooms)
    layout = _self_heal_layout(layout)
    _add_building_openings(layout)
    _assign_room_codes(layout)
    _set_cache(ck, layout)
    return layout


def _deep_copy_layout(layout: FloorPlanLayout) -> FloorPlanLayout:
    rooms_copy = []
    for r in layout.rooms:
        wins = [WallOpening(**w.__dict__) for w in (r.windows or [])]
        doors = [WallOpening(**d.__dict__) for d in (r.doors or [])]
        rooms_copy.append(RoomLayout(
            name=r.name, room_type=r.room_type,
            x_cm=r.x_cm, y_cm=r.y_cm,
            width_cm=r.width_cm, height_cm=r.height_cm,
            windows=wins, doors=doors,
            room_code=getattr(r, 'room_code', ''),
        ))
    return FloorPlanLayout(
        rooms=rooms_copy,
        total_width_cm=layout.total_width_cm,
        total_height_cm=layout.total_height_cm,
        source=layout.source,
        wall_height_cm=layout.wall_height_cm,
        roof_type=layout.roof_type,
        roof_pitch_degrees=layout.roof_pitch_degrees,
        foundation_type=layout.foundation_type,
        num_stories=layout.num_stories,
        ridge_runs_width=layout.ridge_runs_width,
    )


async def _try_gemini_layout_multi(
    num_bedrooms: int, num_bathrooms: int,
    kitchen_type: str, extras: list[str], gross_area: str,
    land_length: Optional[float] = None,
    land_width: Optional[float] = None,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
) -> Optional[FloorPlanLayout]:
    try:
        from app.services.genai_client import get_genai_client
        from google.genai import types
        client = get_genai_client()
    except Exception as e:
        print(f"Gemini init failed: {e}")
        return None

    extras_line = ", ".join(extras) if extras else "None"

    land_constraint = ""
    if land_length and land_width:
        land_w_cm = land_width * 100
        land_h_cm = land_length * 100
        land_constraint = (
            f"LAND CONSTRAINTS:\n"
            f"- The building must fit within a {land_width}m x {land_length}m (W x L) plot.\n"
            f"- Total building width must be close to {land_w_cm:.0f} cm.\n"
            f"- Total building height must be close to {land_h_cm:.0f} cm.\n"
            f"- The building aspect ratio should follow the land: approximately {land_width}:{land_length}.\n\n"
        )

    prompt = (
        "You are an expert architectural space planner. Generate exactly TWO alternative "
        "rectangular single-story floor plan layouts as a JSON array. "
        "Output ONLY the JSON array  no markdown, no explanations.\n\n"
        "REQUIREMENTS:\n"
        f"- Bedrooms: {num_bedrooms} (includes 1 master bedroom)\n"
        f"- Bathrooms: {num_bathrooms}\n"
        f"- Kitchens: {num_kitchens}\n"
        f"- Living rooms: {num_living_rooms}\n"
        f"- Kitchen: {kitchen_type} style (\"open\" = open-plan with living area)\n"
        f"- Additional spaces: {extras_line}\n"
        f"- Gross floor area: ~{gross_area} m\u00b2\n\n"
        f"{land_constraint}"
        "OUTPUT STRUCTURE (a JSON array of two objects):\n"
        "[\n"
        "  {\n"
        '    "total_width_cm": <number>,\n'
        '    "total_height_cm": <number>,\n'
        '    "rooms": [\n'
        "      {\n"
        '        "name": <string>,\n'
        '        "type": <"living"|"master_bedroom"|"bedroom"|"bathroom"|"kitchen"|"dining"|"utility"|"hallway"|"other">,\n'
        '        "x_cm": <number>,\n'
        '        "y_cm": <number>,\n'
        '        "width_cm": <number>,\n'
        '        "height_cm": <number>\n'
        "      }\n"
        "    ]\n"
        "  },\n"
        "  { ... second layout ... }\n"
        "]\n\n"
        "CONSTRAINTS:\n"
        f"1. The total area (total_width_cm x total_height_cm / 10000) must be close to {gross_area} m\u00b2.\n"
        "2. Aspect ratio should be approximately 16:9 (total_width_cm / total_height_cm \u2248 1.78).\n"
        "   If land dimensions are provided above, use the land aspect ratio instead.\n"
        "3. All rooms must tile perfectly within the total rectangle \u2014 no gaps, no overlaps.\n"
        "4. Coordinates are top-left corners: x_cm ranges 0 to total_width_cm, y_cm ranges 0 to total_height_cm.\n"
        "5. Typical room widths (cm): Living 400\u2013550, Master Bedroom 350\u2013500, Bedroom 300\u2013400, "
        "Bathroom 180\u2013250, Kitchen 300\u2013400, Utility 150\u2013250.\n"
        "6. The living/dining area must be the largest room.\n"
        "7. Every room shares at least one wall with another room (no isolated rooms).\n"
        "8. Every room must have a minimum dimension of at least 150 cm.\n"
        '9. For "open" kitchen, place the kitchen adjacent to the living/dining area.\n'
        "10. All rooms must be rectangular.\n"
        "11. The two layouts MUST have different room arrangements (different layout topology).\n\n"
        "Generate two valid, realistic, distinct floor plans now as a JSON array."
    )

    models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

    for model_name in models_to_try:
        text = None
        for attempt in range(4):
            try:
                def call(m=model_name):
                    return client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.4,
                            response_mime_type="application/json",
                        ),
                    )

                response = await asyncio.to_thread(call, model_name)
                text = response.text.strip()
                break
            except Exception as e:
                error_str = str(e)
                if attempt < 3:
                    delay = 15.0 * (3 ** attempt) if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str else 2.0 * (2 ** attempt)
                    print(f"Gemini Error layout_multi {model_name} (attempt {attempt+1}): {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    print(f"Gemini Error layout_multi {model_name} (final attempt {attempt+1}): {e}")
                    
        if not text:
            continue

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                variants = [data]
            elif isinstance(data, list):
                variants = data
            else:
                continue

            best_layout = None
            best_fill = 0.0

            for variant in variants:
                if not isinstance(variant, dict):
                    continue
                if "rooms" not in variant or "total_width_cm" not in variant or "total_height_cm" not in variant:
                    continue

                rooms = []
                for r in variant["rooms"]:
                    rooms.append(RoomLayout(
                        name=r["name"],
                        room_type=r.get("type", "other"),
                        x_cm=float(r["x_cm"]),
                        y_cm=float(r["y_cm"]),
                        width_cm=float(r["width_cm"]),
                        height_cm=float(r["height_cm"]),
                    ))

                candidate = FloorPlanLayout(
                    rooms=rooms,
                    total_width_cm=float(variant["total_width_cm"]),
                    total_height_cm=float(variant["total_height_cm"]),
                    source=model_name,
                )

                if not _validate_layout(candidate):
                    continue

                room_area = sum(r.width_cm * r.height_cm for r in candidate.rooms)
                total_area = candidate.total_width_cm * candidate.total_height_cm
                fill = room_area / total_area if total_area > 0 else 0

                if fill > best_fill:
                    best_fill = fill
                    best_layout = candidate

            if best_layout is not None:
                return best_layout

            print(f"  {model_name}: no valid layout found, trying next model...")

        except Exception as e:
            print(f"  {model_name} failed: {e}")
            continue

    return None


def _validate_layout(layout: FloorPlanLayout) -> bool:
    if len(layout.rooms) < 2:
        return False
    if layout.total_width_cm <= 0 or layout.total_height_cm <= 0:
        return False

    for r in layout.rooms:
        if r.width_cm < 50 or r.height_cm < 50:
            return False
        if r.x_cm < 0 or r.y_cm < 0:
            return False
        if r.x_cm + r.width_cm > layout.total_width_cm + 1:
            return False
        if r.y_cm + r.height_cm > layout.total_height_cm + 1:
            return False

        for r2 in layout.rooms:
            if r is r2:
                continue
            overlap = (
                r.x_cm < r2.x_cm + r2.width_cm and
                r.x_cm + r.width_cm > r2.x_cm and
                r.y_cm < r2.y_cm + r2.height_cm and
                r.y_cm + r.height_cm > r2.y_cm
            )
            if overlap:
                return False

    return True


def _layout_quality_ok(layout: FloorPlanLayout) -> bool:
    """Presentation-quality gate for AI-proposed layouts.

    The plan-sheet renderer drafts whatever geometry it receives, so a
    fragmented AI layout (low fill ratio, sliver rooms, extreme envelope)
    becomes immediately visible. Layouts failing these gates fall back to
    the deterministic grid, which always tiles cleanly.
    """
    w, h = layout.total_width_cm, layout.total_height_cm
    envelope_m2 = (w * h) / 10000
    rooms_m2 = sum((r.width_cm * r.height_cm) / 10000 for r in layout.rooms)

    if envelope_m2 <= 0:
        return False
    fill = rooms_m2 / envelope_m2
    if fill < 0.80:
        return False

    aspect = max(w, h) / max(1.0, min(w, h))
    if aspect > 2.4:
        return False

    for r in layout.rooms:
        rt = (r.room_type or "").lower()
        name = (r.name or "").lower()
        is_wet = "bath" in rt or "wc" in rt
        # Circulation spaces legitimately run long and narrow — exempt them
        is_circulation = ("hall" in rt or "corridor" in rt or "stair" in rt
                          or "hall" in name or "corridor" in name or "escalier" in name
                          or "utility" in rt)
        if is_wet:
            if (r.width_cm * r.height_cm) / 10000 < 1.5:
                return False
            continue
        if is_circulation:
            continue
        # Habitable rooms: sensible minimums and proportions
        area = (r.width_cm * r.height_cm) / 10000
        if area < 4.5:
            return False
        r_aspect = max(r.width_cm, r.height_cm) / max(1.0, min(r.width_cm, r.height_cm))
        if r_aspect > 3.5:
            return False

    return True


def validate_feasibility(
    num_bedrooms: int = 3,
    num_bathrooms: int = 2,
    kitchen_type: str = "open",
    extras: Optional[list[str]] = None,
    gross_area: str = "150",
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
) -> Optional[str]:
    extras = extras or []
    area_m2 = float(gross_area)

    min_areas = {
        "living": 16.0,
        "master_bedroom": 12.0,
        "bedroom": 9.0,
        "bathroom": 3.5,
        "kitchen": 6.0,
        "utility": 4.0,
        "hallway": 2.0,
        "other": 4.0,
    }

    required = []
    for _ in range(num_living_rooms):
        required.append(("living", 16.0))
    required.append(("master_bedroom", 14.0))
    for _ in range(num_kitchens):
        required.append(("kitchen", 7.0))
    for _ in range(num_bedrooms - 1):
        required.append(("bedroom", 9.0))
    for _ in range(num_bathrooms):
        required.append(("bathroom", 3.5))
    for extra in extras:
        extra_lower = extra.lower()
        key = "utility" if any(k in extra_lower for k in ["laundry", "pantry", "storage"]) else "other"
        required.append((key, min_areas[key]))

    min_total = sum(area for _, area in required)

    if area_m2 < min_total * 0.7:
        shortfall = min_total - area_m2
        return (
            f"Requested area ({area_m2:.0f}m\u00b2) is too small for "
            f"{num_bedrooms} bedrooms / {num_bathrooms} bathrooms. "
            f"Minimum ~{min_total:.0f}m\u00b2 needed (shortfall: {shortfall:.0f}m\u00b2)."
        )

    if num_bedrooms > 15:
        return f"Maximum 15 bedrooms supported (requested: {num_bedrooms})."

    return None


def _build_wall_segments(layout: FloorPlanLayout) -> list[dict]:
    wall_map: dict[tuple, dict] = {}
    for r in layout.rooms:
        for side, x1, y1, x2, y2 in [
            ("top", r.x_cm, r.y_cm, r.x_cm + r.width_cm, r.y_cm),
            ("right", r.x_cm + r.width_cm, r.y_cm, r.x_cm + r.width_cm, r.y_cm + r.height_cm),
            ("bottom", r.x_cm, r.y_cm + r.height_cm, r.x_cm + r.width_cm, r.y_cm + r.height_cm),
            ("left", r.x_cm, r.y_cm, r.x_cm, r.y_cm + r.height_cm),
        ]:
            key = (round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1))
            if key in wall_map:
                wall_map[key]["shared"] = True
                wall_map[key]["rooms"].append(r)
            else:
                wall_map[key] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "shared": False, "rooms": [r], "side": side}
    return list(wall_map.values())


def _wall_length(w: dict) -> float:
    return ((w["x2"] - w["x1"]) ** 2 + (w["y2"] - w["y1"]) ** 2) ** 0.5


def _wall_span(w: dict, side: str) -> tuple[float, float]:
    """Return (start, end) coordinate along a wall in the wall's own axis."""
    if side in ("top", "bottom"):
        return (min(w["x1"], w["x2"]), max(w["x1"], w["x2"]))
    return (min(w["y1"], w["y2"]), max(w["y1"], w["y2"]))


def _room_wall_extent(room: RoomLayout, side: str) -> tuple[float, float, float]:
    """Return (fixed_coord, start, end) of a room's wall on `side`.

    For top/bottom, fixed_coord is the y of the wall and start/end are x.
    For left/right, fixed_coord is the x of the wall and start/end are y.
    """
    if side == "top":
        return (room.y_cm, room.x_cm, room.x_cm + room.width_cm)
    if side == "bottom":
        return (room.y_cm + room.height_cm, room.x_cm, room.x_cm + room.width_cm)
    if side == "left":
        return (room.x_cm, room.y_cm, room.y_cm + room.height_cm)
    return (room.x_cm + room.width_cm, room.y_cm, room.y_cm + room.height_cm)


def _occupied_intervals(room: RoomLayout, side: str, start: float, end: float) -> list[tuple[float, float]]:
    """Existing openings (plus clearance) on this room's wall, in wall-axis coords."""
    iv = []
    for op in (room.windows or []) + (room.doors or []):
        if op.wall_side != side:
            continue
        # Window/door center is stored relative to the room edge start
        iv.append((op.center_cm - op.width_cm / 2 - 30, op.center_cm + op.width_cm / 2 + 30))
    return iv


def _find_free_span(intervals: list[tuple[float, float]], start: float, end: float, need: float) -> Optional[float]:
    """Find a free span of length `need` in [start, end]; prefer the center. Returns center or None."""
    pad = 20.0
    lo, hi = start + pad, end - pad
    if hi - lo < need:
        return None
    clipped = sorted(
        (max(a, lo), min(b, hi)) for a, b in intervals if b > lo and a < hi
    )
    free: list[tuple[float, float]] = []
    cursor = lo
    for a, b in clipped:
        if a - cursor >= need:
            free.append((cursor, a))
        cursor = max(cursor, b)
    if hi - cursor >= need:
        free.append((cursor, hi))
    if not free:
        return None
    mid = (lo + hi) / 2
    best = min(free, key=lambda s: abs((s[0] + s[1]) / 2 - mid) - (s[1] - s[0]) * 0.001)
    return (best[0] + best[1]) / 2


def _add_building_openings(layout: FloorPlanLayout):
    walls = _build_wall_segments(layout)

    for room in layout.rooms:
        room.windows = []
        room.doors = []

    exterior = [w for w in walls if not w["shared"]]
    shared = [w for w in walls if w["shared"]]

    # ── Entry door on the living room's exterior wall ────────────────────────
    living = next((r for r in layout.rooms if r.room_type == "living"), None)
    if living is None:
        living = max(layout.rooms, key=lambda r: r.width_cm * r.height_cm)
    entry_width = 110.0
    for side_pref in ("bottom", "left", "right", "top"):
        fixed, start, end = _room_wall_extent(living, side_pref)
        is_ext = any(
            w["side"] == side_pref and not w["shared"] and living in w["rooms"]
            and abs(_room_wall_extent(living, side_pref)[0] - (w["y1"] if side_pref in ("top", "bottom") else w["x1"])) < 1
            for w in exterior
        )
        if not is_ext:
            continue
        center = _find_free_span([], start, end, entry_width)
        if center is not None:
            living.doors.append(WallOpening(
                wall_side=side_pref, center_cm=center - start,
                width_cm=entry_width, height_cm=220.0, sill_height_cm=0,
            ))
            break

    # ── Interior doors: BFS from the living room through shared walls ────────
    adjacency: dict[int, list[tuple[RoomLayout, dict, str]]] = {}
    for w in shared:
        if len(w["rooms"]) < 2:
            continue
        a, b = w["rooms"][0], w["rooms"][1]
        adjacency.setdefault(id(a), []).append((b, w, w["side"] if w["rooms"][0] is a else
                                                ("top" if w["side"] == "bottom" else
                                                 "bottom" if w["side"] == "top" else
                                                 "left" if w["side"] == "right" else "right")))
        adjacency.setdefault(id(b), []).append((a, w, w["side"] if w["rooms"][1] is b else
                                                ("top" if w["side"] == "bottom" else
                                                 "bottom" if w["side"] == "top" else
                                                 "left" if w["side"] == "right" else "right")))

    connected = {id(living): living}
    queue = [living]
    while queue:
        current = queue.pop(0)
        for neighbor, _w, side in adjacency.get(id(current), []):
            if id(neighbor) not in connected:
                connected[id(neighbor)] = neighbor
                queue.append(neighbor)
                # Place a door on this shared wall, in the neighbor's frame
                fixed, start, end = _room_wall_extent(neighbor, side)
                need = 70.0 if neighbor.room_type in ("bathroom", "wc") else 90.0
                occupied = _occupied_intervals(neighbor, side, start, end)
                center = _find_free_span(occupied, start, end, need)
                if center is None and occupied:
                    # Retry ignoring clearance pads
                    center = _find_free_span([], start, end, need)
                if center is not None:
                    neighbor.doors.append(WallOpening(
                        wall_side=side, center_cm=center - start,
                        width_cm=need, height_cm=210.0, sill_height_cm=0,
                    ))

    # Any room still unreachable (rare, gapped layouts): door on longest shared wall
    for room in layout.rooms:
        if id(room) in connected:
            continue
        best_len, best = -1.0, None
        for neighbor, w, side in adjacency.get(id(room), []):
            fixed, start, end = _room_wall_extent(room, side)
            if end - start > best_len:
                best_len, best = end - start, (side, start, end)
        if best:
            side, start, end = best
            center = _find_free_span([], start, end, 90.0)
            if center is not None:
                room.doors.append(WallOpening(
                    wall_side=side, center_cm=center - start,
                    width_cm=90.0, height_cm=210.0, sill_height_cm=0,
                ))

    # ── Windows on exterior walls, avoiding doors ────────────────────────────
    win_width = 120.0
    win_height = 150.0
    win_sill = 90.0

    for w in exterior:
        length = _wall_length(w)
        if length < 200:
            continue

        for room in w["rooms"]:
            fixed, start, end = _room_wall_extent(room, w["side"])
            occupied = _occupied_intervals(room, w["side"], start, end)
            n_target = max(1, round(length / 400))
            placed = 0
            margin = length * 0.12
            step = (length - 2 * margin) / n_target if n_target else length
            for wi in range(n_target):
                approx_center = margin + step * (wi + 0.5)
                # Snap search around the ideal position
                probe_start, probe_end = start + margin, end - margin
                if probe_end <= probe_start:
                    continue
                center = _find_free_span(occupied, probe_start, probe_end, win_width)
                if center is None:
                    continue
                if abs((center - start) - approx_center) > step:
                    continue  # free span is far from the ideal slot; skip
                room.windows.append(WallOpening(
                    wall_side=w["side"], center_cm=center - start,
                    width_cm=win_width, height_cm=win_height, sill_height_cm=win_sill,
                ))
                occupied.append((center - start - win_width / 2 - 30,
                                 center - start + win_width / 2 + 30))
                placed += 1

    _validate_no_overlapping_openings(layout)



def _assign_room_codes(layout):
    """Assign architectural room codes (BR1, BR2, MBR, LR, KIT, BA1, etc.)."""
    counters = {}
    for room in layout.rooms:
        rt = (room.room_type or '').lower()
        base = ROOM_CODE_MAP.get(rt, "OT")
        if base not in counters:
            counters[base] = 0
        counters[base] += 1
        room.room_code = f"{base}{counters[base]}"
    return layout


def _validate_no_overlapping_openings(layout: FloorPlanLayout):
    """Drop later openings that physically overlap earlier ones on the same wall."""
    for room in layout.rooms:
        seen: list[tuple[str, float, float]] = []
        for op_list in (room.doors, room.windows):
            keep = []
            for op in op_list:
                a = op.center_cm - op.width_cm / 2
                b = op.center_cm + op.width_cm / 2
                if any(op.wall_side == s2 and a < b2 and b > a2 for s2, a2, b2 in seen):
                    continue
                seen.append((op.wall_side, a, b))
                keep.append(op)
            op_list[:] = keep


def _self_heal_layout(layout: FloorPlanLayout) -> FloorPlanLayout:
    fixed = False

    for r in layout.rooms:
        if r.width_cm < 80:
            r.width_cm = 80
            fixed = True
        if r.height_cm < 80:
            r.height_cm = 80
            fixed = True

    for r in layout.rooms:
        if r.x_cm + r.width_cm > layout.total_width_cm:
            r.width_cm = max(80, layout.total_width_cm - r.x_cm)
            fixed = True
        if r.y_cm + r.height_cm > layout.total_height_cm:
            r.height_cm = max(80, layout.total_height_cm - r.y_cm)
            fixed = True

    for i, r in enumerate(layout.rooms):
        for j, r2 in enumerate(layout.rooms):
            if i >= j:
                continue
            ox = max(0, min(r.x_cm + r.width_cm, r2.x_cm + r2.width_cm) - max(r.x_cm, r2.x_cm))
            oy = max(0, min(r.y_cm + r.height_cm, r2.y_cm + r2.height_cm) - max(r.y_cm, r2.y_cm))
            if ox > 0 and oy > 0:
                if ox < oy:
                    if r.x_cm < r2.x_cm:
                        r.width_cm = max(80, r2.x_cm - r.x_cm)
                    else:
                        r2.width_cm = max(80, r.x_cm - r2.x_cm)
                else:
                    if r.y_cm < r2.y_cm:
                        r.height_cm = max(80, r2.y_cm - r.y_cm)
                    else:
                        r2.height_cm = max(80, r.y_cm - r2.y_cm)
                fixed = True

    _close_gaps(layout)

    if fixed:
        layout.source = f"{layout.source}_healed"
    return layout


def _close_gaps(layout: FloorPlanLayout):
    sorted_x = sorted(layout.rooms, key=lambda r: r.x_cm)
    for i in range(len(sorted_x) - 1):
        r1 = sorted_x[i]
        r2 = sorted_x[i + 1]
        r1_end = r1.x_cm + r1.width_cm
        if r2.x_cm > r1_end + 5 and _vertically_aligned(r1, r2):
            gap = r2.x_cm - r1_end
            r1.width_cm += gap / 2
            r2.x_cm -= gap / 2
            r1.width_cm = max(80, r1.width_cm)
            r2.x_cm = max(0, r2.x_cm)

    sorted_y = sorted(layout.rooms, key=lambda r: r.y_cm)
    for i in range(len(sorted_y) - 1):
        r1 = sorted_y[i]
        r2 = sorted_y[i + 1]
        r1_end = r1.y_cm + r1.height_cm
        if r2.y_cm > r1_end + 5 and _horizontally_aligned(r1, r2):
            gap = r2.y_cm - r1_end
            r1.height_cm += gap / 2
            r2.y_cm -= gap / 2
            r1.height_cm = max(80, r1.height_cm)
            r2.y_cm = max(0, r2.y_cm)


def _vertically_aligned(r1, r2, threshold: float = 0.3) -> bool:
    overlap = min(r1.y_cm + r1.height_cm, r2.y_cm + r2.height_cm) - max(r1.y_cm, r2.y_cm)
    return overlap > threshold * max(r1.height_cm, r2.height_cm)


def _horizontally_aligned(r1, r2, threshold: float = 0.3) -> bool:
    overlap = min(r1.x_cm + r1.width_cm, r2.x_cm + r2.width_cm) - max(r1.x_cm, r2.x_cm)
    return overlap > threshold * max(r1.width_cm, r2.width_cm)


def _cache_key(
    num_bedrooms: int, num_bathrooms: int,
    kitchen_type: str, extras: list[str], gross_area: str,
    land_length: Optional[float] = None, land_width: Optional[float] = None,
    num_kitchens: int = 1, num_living_rooms: int = 1,
) -> str:
    area_bucket = str(round(float(gross_area) / 10) * 10)
    land_part = f"|{land_length or ''}x{land_width or ''}"
    raw = f"{num_bedrooms}|{num_bathrooms}|{kitchen_type}|{sorted(extras)}|{area_bucket}{land_part}|{num_kitchens}|{num_living_rooms}"
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[FloorPlanLayout]:
    return _LAYOUT_CACHE.get(key)


def _set_cache(key: str, layout: FloorPlanLayout):
    _LAYOUT_CACHE[key] = layout


def _deterministic_layout(
    num_bedrooms: int, num_bathrooms: int,
    kitchen_type: str, extras: list[str], gross_area: str,
    land_length: Optional[float] = None,
    land_width: Optional[float] = None,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
) -> FloorPlanLayout:
    area_m2 = max(float(gross_area), 30.0)

    room_specs: list[tuple[str, str, float]] = []
    for i in range(num_living_rooms):
        room_specs.append((f"Living/Dining" if num_living_rooms == 1 else f"Living/Dining {i + 1}", "living", 1.5))
    room_specs.append(("Master Bedroom", "master_bedroom", 1.0))
    for i in range(num_kitchens):
        room_specs.append((f"Kitchen" if num_kitchens == 1 else f"Kitchen {i + 1}", "kitchen", 0.7))

    for i in range(max(0, num_bedrooms - 1)):
        room_specs.append((f"Bedroom {i + 1}", "bedroom", 0.65))

    for i in range(num_bathrooms):
        room_specs.append((f"Bathroom {i + 1}", "bathroom", 0.3))

    for extra in extras:
        room_specs.append((extra, "other" if extra.lower() not in ROOM_CODE_MAP else extra.lower(), 0.4))

    n = len(room_specs)

    if land_length and land_width:
        total_width_cm = land_width * 100
        total_height_cm = land_length * 100
        building_area_m2 = (total_width_cm * total_height_cm) / 10000
        if building_area_m2 < area_m2 * 0.5:
            total_width_cm = math.sqrt(area_m2 * 10000 * 16 / 9)
            total_height_cm = total_width_cm * 9 / 16
    else:
        aspect = 16.0 / 9.0
        total_area_cm2 = area_m2 * 10000
        total_width_cm = math.sqrt(total_area_cm2 * aspect)
        total_height_cm = total_width_cm / aspect

    if n <= 3:
        num_cols = n
    elif n <= 6:
        num_cols = 3
    else:
        num_cols = 4

    rows: list[list[tuple[str, str, float]]] = []
    for i in range(0, n, num_cols):
        rows.append(room_specs[i:i + num_cols])

    row_weights = [sum(w for _, _, w in row) for row in rows]
    total_row_weight = sum(row_weights)

    rooms: list[RoomLayout] = []
    y_cm = 0.0
    for row_idx, row in enumerate(rows):
        row_weight = row_weights[row_idx]
        row_height = total_height_cm * row_weight / total_row_weight

        x_cm = 0.0
        row_w = sum(w for _, _, w in row)
        for name, room_type, weight in row:
            room_width = total_width_cm * weight / row_w
            room_width = max(room_width, 100.0)

            rooms.append(RoomLayout(
                name=name,
                room_type=room_type,
                x_cm=x_cm,
                y_cm=y_cm,
                width_cm=room_width,
                height_cm=row_height,
            ))
            x_cm += room_width

        y_cm += row_height

    return FloorPlanLayout(
        rooms=rooms,
        total_width_cm=total_width_cm,
        total_height_cm=total_height_cm,
        source="deterministic",
    )
