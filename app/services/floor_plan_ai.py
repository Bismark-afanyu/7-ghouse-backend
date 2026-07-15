"""
Floor plan renderer: Imagen 4.0 AI primary with post-processing, PIL fallback.
"""
import asyncio
import io
import os
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
    """
    Render a professional architectural floor plan using PIL.
    Produces black-and-white CAD-style drawing with proper walls, doors, windows.
    """
    # Calculate image dimensions with generous margins for annotations
    margin_cm = max(layout.total_width_cm, layout.total_height_cm) * 0.35
    img_w_px = 2400
    img_h_px = int(img_w_px * (layout.total_height_cm + margin_cm * 2) /
                   (layout.total_width_cm + margin_cm * 2))
    img = Image.new("RGB", (img_w_px, img_h_px), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    scale = img_w_px / (layout.total_width_cm + margin_cm * 2)

    def tx(x_cm):
        return int((x_cm + margin_cm) * scale)

    def ty(y_cm):
        return int((y_cm + margin_cm) * scale)

    # Load fonts
    font_code = font_name = font_area = font_dim = font_title = font_small = font_door = None
    try:
        font_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "fonts", "NotoSans-Variable.ttf"
        )
        if os.path.exists(font_path):
            font_code = ImageFont.truetype(font_path, max(30, int(img_w_px * 0.024)))
            font_name = ImageFont.truetype(font_path, max(20, int(img_w_px * 0.016)))
            font_area = ImageFont.truetype(font_path, max(14, int(img_w_px * 0.011)))
            font_dim = ImageFont.truetype(font_path, max(16, int(img_w_px * 0.013)))
            font_title = ImageFont.truetype(font_path, max(24, int(img_w_px * 0.020)))
            font_small = ImageFont.truetype(font_path, max(12, int(img_w_px * 0.010)))
            font_door = ImageFont.truetype(font_path, max(11, int(img_w_px * 0.009)))
    except (OSError, FileNotFoundError):
        pass

    if font_code is None:
        font_code = ImageFont.load_default()
        font_name = font_code
        font_area = font_code
        font_dim = font_code
        font_title = font_code
        font_small = font_code
        font_door = font_code

    # Colors
    BLACK = "#1a1a1a"
    DARK_GRAY = "#333333"
    MED_GRAY = "#666666"
    LIGHT_GRAY = "#cccccc"
    WALL_COLOR = "#2c3e50"
    DIM_COLOR = "#555555"

    wall_half = WALL_THICKNESS_CM / 2
    wall_px = max(8, int(WALL_THICKNESS_CM * scale))

    # ── Build wall segment map (avoid drawing overlapping walls) ─────────────
    # Collect all horizontal and vertical wall segments
    h_walls = []  # (x1, x2, y)
    v_walls = []  # (x, y1, y2)

    for room in layout.rooms:
        rx, ry = room.x_cm, room.y_cm
        rw, rh = room.width_cm, room.height_cm

        # Top wall
        h_walls.append((rx - wall_half, rx + rw + wall_half, ry - wall_half))
        # Bottom wall
        h_walls.append((rx - wall_half, rx + rw + wall_half, ry + rh + wall_half))
        # Left wall
        v_walls.append((rx - wall_half, ry - wall_half, ry + rh + wall_half))
        # Right wall
        v_walls.append((rx + rw + wall_half, ry - wall_half, ry + rh + wall_half))

    # ── Draw Room Fills ──────────────────────────────────────────────────────
    for room in layout.rooms:
        x1, y1 = tx(room.x_cm), ty(room.y_cm)
        x2, y2 = tx(room.x_cm + room.width_cm), ty(room.y_cm + room.height_cm)
        draw.rectangle([x1, y1, x2, y2], fill="#f5f5f5", outline=None)

    # ── Draw Walls (filled rectangles, no overlap issues) ────────────────────
    def draw_wall_rect(x1_cm, y1_cm, x2_cm, y2_cm):
        """Draw a filled wall rectangle."""
        px1, py1 = tx(x1_cm), ty(y1_cm)
        px2, py2 = tx(x2_cm), ty(y2_cm)
        draw.rectangle([px1, py1, px2, py2], fill=WALL_COLOR, outline=WALL_COLOR)

    for room in layout.rooms:
        rx, ry = room.x_cm, room.y_cm
        rw, rh = room.width_cm, room.height_cm

        # Top wall (horizontal)
        draw_wall_rect(rx - wall_half, ry - wall_half, rx + rw + wall_half, ry + wall_half)
        # Bottom wall (horizontal)
        draw_wall_rect(rx - wall_half, ry + rh - wall_half, rx + rw + wall_half, ry + rh + wall_half)
        # Left wall (vertical)
        draw_wall_rect(rx - wall_half, ry - wall_half, rx + wall_half, ry + rh + wall_half)
        # Right wall (vertical)
        draw_wall_rect(rx + rw - wall_half, ry - wall_half, rx + rw + wall_half, ry + rh + wall_half)

    # ── Draw Room Interior (white fill on top of walls) ──────────────────────
    for room in layout.rooms:
        x1, y1 = tx(room.x_cm), ty(room.y_cm)
        x2, y2 = tx(room.x_cm + room.width_cm), ty(room.y_cm + room.height_cm)
        draw.rectangle([x1, y1, x2, y2], fill="#FFFFFF", outline=None)

    # ── Draw Wall Hatching (diagonal lines in wall cavities) ─────────────────
    for room in layout.rooms:
        rx, ry = room.x_cm, room.y_cm
        rw, rh = room.width_cm, room.height_cm

        # Top wall hatching
        wx1, wy1 = tx(rx - wall_half), ty(ry - wall_half)
        wx2, wy2 = tx(rx + rw + wall_half), ty(ry + wall_half)
        step = max(6, wall_px // 3)
        for d in range(0, (wx2 - wx1) + (wy2 - wy1), step):
            lx1 = max(wx1, wx1 + d - (wy2 - wy1))
            ly1 = min(wy2, wy1 + max(0, d - (wx2 - wx1)))
            lx2 = min(wx2, wx1 + d)
            ly2 = max(wy1, wy1 + max(0, (wx2 - wx1) - d))
            if lx1 < lx2 and ly1 < ly2:
                draw.line([int(lx1), int(ly1), int(lx2), int(ly2)], fill="#4a6274", width=1)

        # Bottom wall hatching
        wx1, wy1 = tx(rx - wall_half), ty(ry + rh - wall_half)
        wx2, wy2 = tx(rx + rw + wall_half), ty(ry + rh + wall_half)
        for d in range(0, (wx2 - wx1) + (wy2 - wy1), step):
            lx1 = max(wx1, wx1 + d - (wy2 - wy1))
            ly1 = min(wy2, wy1 + max(0, d - (wx2 - wx1)))
            lx2 = min(wx2, wx1 + d)
            ly2 = max(wy1, wy1 + max(0, (wx2 - wx1) - d))
            if lx1 < lx2 and ly1 < ly2:
                draw.line([int(lx1), int(ly1), int(lx2), int(ly2)], fill="#4a6274", width=1)

        # Left wall hatching
        wx1, wy1 = tx(rx - wall_half), ty(ry - wall_half)
        wx2, wy2 = tx(rx + wall_half), ty(ry + rh + wall_half)
        for d in range(0, (wx2 - wx1) + (wy2 - wy1), step):
            lx1 = max(wx1, wx1 + d - (wy2 - wy1))
            ly1 = min(wy2, wy1 + max(0, d - (wx2 - wx1)))
            lx2 = min(wx2, wx1 + d)
            ly2 = max(wy1, wy1 + max(0, (wx2 - wx1) - d))
            if lx1 < lx2 and ly1 < ly2:
                draw.line([int(lx1), int(ly1), int(lx2), int(ly2)], fill="#4a6274", width=1)

        # Right wall hatching
        wx1, wy1 = tx(rx + rw - wall_half), ty(ry - wall_half)
        wx2, wy2 = tx(rx + rw + wall_half), ty(ry + rh + wall_half)
        for d in range(0, (wx2 - wx1) + (wy2 - wy1), step):
            lx1 = max(wx1, wx1 + d - (wy2 - wy1))
            ly1 = min(wy2, wy1 + max(0, d - (wx2 - wx1)))
            lx2 = min(wx2, wx1 + d)
            ly2 = max(wy1, wy1 + max(0, (wx2 - wx1) - d))
            if lx1 < lx2 and ly1 < ly2:
                draw.line([int(lx1), int(ly1), int(lx2), int(ly2)], fill="#4a6274", width=1)

    # ── Draw Door Symbols ────────────────────────────────────────────────────
    door_idx = 1
    for room in layout.rooms:
        rx, ry = room.x_cm, room.y_cm
        rw, rh = room.width_cm, room.height_cm

        # Place door on bottom wall (entrance side)
        door_x = rx + rw * 0.25
        door_y = ry + rh
        door_w_px = int(100 * scale)  # 100cm door

        # Door gap in wall
        gap_x1 = tx(door_x - 50)
        gap_x2 = tx(door_x + 50)
        gap_y1 = ty(door_y - wall_half)
        gap_y2 = ty(door_y + wall_half)
        draw.rectangle([gap_x1, gap_y1, gap_x2, gap_y2], fill="#FFFFFF", outline=None)

        # Door leaf line
        leaf_x1 = tx(door_x)
        leaf_y1 = ty(door_y)
        leaf_x2 = tx(door_x)
        leaf_y2 = ty(door_y + 90)
        draw.line([leaf_x1, leaf_y1, leaf_x2, leaf_y2], fill=BLACK, width=2)

        # Door swing arc (90 degrees)
        arc_r = int(90 * scale)
        arc_cx = tx(door_x)
        arc_cy = ty(door_y)
        draw.arc([arc_cx - arc_r, arc_cy, arc_cx + arc_r, arc_cy + arc_r * 2],
                 start=270, end=360, fill=BLACK, width=1)

        # Door label
        draw.text((tx(door_x), ty(door_y + 100)),
                   f"D{door_idx:02d}", font=font_door, fill=MED_GRAY, anchor="mt")
        door_idx += 1

    # ── Draw Window Symbols ──────────────────────────────────────────────────
    win_idx = 1
    for room in layout.rooms:
        rx, ry = room.x_cm, room.y_cm
        rw, rh = room.width_cm, room.height_cm

        # Place windows on exterior walls
        # Top wall window
        win_cx = rx + rw / 2
        win_w = min(120, rw * 0.4)
        px1 = tx(win_cx - win_w / 2)
        px2 = tx(win_cx + win_w / 2)
        py1 = ty(ry - wall_half)
        py2 = ty(ry + wall_half)

        # Clear wall area for window
        draw.rectangle([px1, py1, px2, py2], fill="#FFFFFF", outline=None)

        # Triple-line window symbol
        mid_y = (py1 + py2) // 2
        draw.line([px1, py1 + 2, px2, py1 + 2], fill=BLACK, width=2)
        draw.line([px1, mid_y, px2, mid_y], fill=BLACK, width=2)
        draw.line([px1, py2 - 2, px2, py2 - 2], fill=BLACK, width=2)

        # Window label
        draw.text((tx(win_cx), ty(ry) - int(wall_px * 1.5)),
                   f"W{win_idx:02d}", font=font_door, fill=MED_GRAY, anchor="mb")
        win_idx += 1

        # Right wall window (if room is on right edge)
        if rx + rw >= layout.total_width_cm - 50:
            win_cy = ry + rh / 2
            win_h = min(120, rh * 0.4)
            py1 = ty(win_cy - win_h / 2)
            py2 = ty(win_cy + win_h / 2)
            px1 = tx(rx + rw - wall_half)
            px2 = tx(rx + rw + wall_half)

            draw.rectangle([px1, py1, px2, py2], fill="#FFFFFF", outline=None)
            mid_x = (px1 + px2) // 2
            draw.line([px1 + 2, py1, px1 + 2, py2], fill=BLACK, width=2)
            draw.line([mid_x, py1, mid_x, py2], fill=BLACK, width=2)
            draw.line([px2 - 2, py1, px2 - 2, py2], fill=BLACK, width=2)

            draw.text((tx(rx + rw) + int(wall_px * 1.5), ty(win_cy)),
                       f"W{win_idx:02d}", font=font_door, fill=MED_GRAY, anchor="lm")
            win_idx += 1

    # ── Draw Room Labels ─────────────────────────────────────────────────────
    for room in layout.rooms:
        cx = tx(room.x_cm + room.width_cm / 2)
        cy = ty(room.y_cm + room.height_cm / 2)
        code = getattr(room, 'room_code', '') or ''
        area_m2 = (room.width_cm * room.height_cm) / 10000

        # White background for text
        bg_w = int(img_w_px * 0.13)
        bg_h = 70 if code else 45
        draw.rectangle([cx - bg_w // 2, cy - bg_h // 2,
                       cx + bg_w // 2, cy + bg_h // 2], fill="#FFFFFF")

        if code:
            draw.text((cx, cy - 20), code, font=font_code, fill=BLACK, anchor="mm")
            draw.text((cx, cy + 4), room.name, font=font_name, fill=DARK_GRAY, anchor="mm")
            draw.text((cx, cy + 24), f"{area_m2:.1f} m\u00b2", font=font_area, fill=MED_GRAY, anchor="mm")
        else:
            draw.text((cx, cy - 10), room.name, font=font_name, fill=BLACK, anchor="mm")
            draw.text((cx, cy + 12), f"{area_m2:.1f} m\u00b2", font=font_area, fill=MED_GRAY, anchor="mm")

    # ── Annotated Elements ───────────────────────────────────────────────────
    if annotated:
        min_x = min(r.x_cm for r in layout.rooms)
        max_x = max(r.x_cm + r.width_cm for r in layout.rooms)
        min_y = min(r.y_cm for r in layout.rooms)
        max_y = max(r.y_cm + r.height_cm for r in layout.rooms)
        total_w_m = (max_x - min_x) / 100
        total_h_m = (max_y - min_y) / 100

        # Collect room edges for dimension chain segments
        x_edges = sorted(set([min_x] + [r.x_cm for r in layout.rooms] +
                             [r.x_cm + r.width_cm for r in layout.rooms] + [max_x]))
        y_edges = sorted(set([min_y] + [r.y_cm for r in layout.rooms] +
                             [r.y_cm + r.height_cm for r in layout.rooms] + [max_y]))

        # ── Dimension Lines ──────────────────────────────────────────────────
        dim_offset = int(img_h_px * 0.06)

        # Bottom dimension chain
        py_bottom = ty(max_y) + dim_offset
        px_left = tx(min_x)
        px_right = tx(max_x)

        draw.line([px_left, py_bottom, px_right, py_bottom], fill=DIM_COLOR, width=2)
        draw.line([px_left, py_bottom - 12, px_left, py_bottom + 12], fill=DIM_COLOR, width=2)
        draw.line([px_right, py_bottom - 12, px_right, py_bottom + 12], fill=DIM_COLOR, width=2)

        # Extension lines
        draw.line([px_left, ty(max_y), px_left, py_bottom], fill=LIGHT_GRAY, width=1)
        draw.line([px_right, ty(max_y), px_right, py_bottom], fill=LIGHT_GRAY, width=1)

        # Segment measurements
        for i in range(len(x_edges) - 1):
            seg_x1 = x_edges[i]
            seg_x2 = x_edges[i + 1]
            if seg_x2 - seg_x1 < 50:
                continue
            seg_px1 = tx(seg_x1)
            seg_px2 = tx(seg_x2)
            seg_mid = (seg_px1 + seg_px2) // 2
            seg_m = (seg_x2 - seg_x1) / 100

            draw.line([seg_px1, py_bottom - 8, seg_px1, py_bottom + 8], fill=DIM_COLOR, width=1)
            draw.line([seg_px2, py_bottom - 8, seg_px2, py_bottom + 8], fill=DIM_COLOR, width=1)
            draw.text((seg_mid, py_bottom - 16), f"{seg_m:.2f}", font=font_dim, fill=DIM_COLOR, anchor="mb")

        draw.text(((px_left + px_right) // 2, py_bottom + 18),
                   f"{total_w_m:.2f} m", font=font_small, fill=DIM_COLOR, anchor="mt")

        # Top dimension chain
        py_top = ty(min_y) - dim_offset
        draw.line([px_left, py_top, px_right, py_top], fill=DIM_COLOR, width=2)
        draw.line([px_left, py_top - 12, px_left, py_top + 12], fill=DIM_COLOR, width=2)
        draw.line([px_right, py_top - 12, px_right, py_top + 12], fill=DIM_COLOR, width=2)
        draw.line([px_left, py_top, px_left, ty(min_y)], fill=LIGHT_GRAY, width=1)
        draw.line([px_right, py_top, px_right, ty(min_y)], fill=LIGHT_GRAY, width=1)

        for i in range(len(x_edges) - 1):
            seg_x1 = x_edges[i]
            seg_x2 = x_edges[i + 1]
            if seg_x2 - seg_x1 < 50:
                continue
            seg_px1 = tx(seg_x1)
            seg_px2 = tx(seg_x2)
            seg_mid = (seg_px1 + seg_px2) // 2
            seg_m = (seg_x2 - seg_x1) / 100

            draw.line([seg_px1, py_top - 8, seg_px1, py_top + 8], fill=DIM_COLOR, width=1)
            draw.line([seg_px2, py_top - 8, seg_px2, py_top + 8], fill=DIM_COLOR, width=1)
            draw.text((seg_mid, py_top - 16), f"{seg_m:.2f}", font=font_dim, fill=DIM_COLOR, anchor="mb")

        draw.text(((px_left + px_right) // 2, py_top - 18),
                   f"{total_w_m:.2f} m", font=font_small, fill=DIM_COLOR, anchor="mb")

        # Left dimension chain
        px_left_dim = tx(min_x) - int(img_w_px * 0.08)
        py_top_left = ty(min_y)
        py_bottom_left = ty(max_y)

        draw.line([px_left_dim, py_top_left, px_left_dim, py_bottom_left], fill=DIM_COLOR, width=2)
        draw.line([px_left_dim - 12, py_top_left, px_left_dim + 12, py_top_left], fill=DIM_COLOR, width=2)
        draw.line([px_left_dim - 12, py_bottom_left, px_left_dim + 12, py_bottom_left], fill=DIM_COLOR, width=2)
        draw.line([tx(min_x), py_top_left, px_left_dim, py_top_left], fill=LIGHT_GRAY, width=1)
        draw.line([tx(min_x), py_bottom_left, px_left_dim, py_bottom_left], fill=LIGHT_GRAY, width=1)

        for i in range(len(y_edges) - 1):
            seg_y1 = y_edges[i]
            seg_y2 = y_edges[i + 1]
            if seg_y2 - seg_y1 < 50:
                continue
            seg_py1 = ty(seg_y1)
            seg_py2 = ty(seg_y2)
            seg_mid = (seg_py1 + seg_py2) // 2
            seg_m = (seg_y2 - seg_y1) / 100

            draw.line([px_left_dim - 8, seg_py1, px_left_dim + 8, seg_py1], fill=DIM_COLOR, width=1)
            draw.line([px_left_dim - 8, seg_py2, px_left_dim + 8, seg_py2], fill=DIM_COLOR, width=1)
            draw.text((px_left_dim - 16, seg_mid), f"{seg_m:.2f}", font=font_dim, fill=DIM_COLOR, anchor="rm")

        draw.text((px_left_dim - 18, (py_top_left + py_bottom_left) // 2),
                   f"{total_h_m:.2f} m", font=font_small, fill=DIM_COLOR, anchor="rm")

        # Right dimension chain
        px_right_dim = tx(max_x) + int(img_w_px * 0.08)
        draw.line([px_right_dim, py_top_left, px_right_dim, py_bottom_left], fill=DIM_COLOR, width=2)
        draw.line([px_right_dim - 12, py_top_left, px_right_dim + 12, py_top_left], fill=DIM_COLOR, width=2)
        draw.line([px_right_dim - 12, py_bottom_left, px_right_dim + 12, py_bottom_left], fill=DIM_COLOR, width=2)
        draw.line([tx(max_x), py_top_left, px_right_dim, py_top_left], fill=LIGHT_GRAY, width=1)
        draw.line([tx(max_x), py_bottom_left, px_right_dim, py_bottom_left], fill=LIGHT_GRAY, width=1)

        for i in range(len(y_edges) - 1):
            seg_y1 = y_edges[i]
            seg_y2 = y_edges[i + 1]
            if seg_y2 - seg_y1 < 50:
                continue
            seg_py1 = ty(seg_y1)
            seg_py2 = ty(seg_y2)
            seg_mid = (seg_py1 + seg_py2) // 2
            seg_m = (seg_y2 - seg_y1) / 100

            draw.line([px_right_dim - 8, seg_py1, px_right_dim + 8, seg_py1], fill=DIM_COLOR, width=1)
            draw.line([px_right_dim - 8, seg_py2, px_right_dim + 8, seg_py2], fill=DIM_COLOR, width=1)
            draw.text((px_right_dim + 16, seg_mid), f"{seg_m:.2f}", font=font_dim, fill=DIM_COLOR, anchor="lm")

        draw.text((px_right_dim + 18, (py_top_left + py_bottom_left) // 2),
                   f"{total_h_m:.2f} m", font=font_small, fill=DIM_COLOR, anchor="lm")

        # ── Title Block (Bottom Right) ───────────────────────────────────────
        tb_w = int(img_w_px * 0.28)
        tb_h = int(img_h_px * 0.12)
        tb_x = img_w_px - tb_w - int(img_w_px * 0.03)
        tb_y = img_h_px - tb_h - int(img_h_px * 0.03)

        # Title block border
        draw.rectangle([tb_x, tb_y, tb_x + tb_w, tb_y + tb_h], outline=BLACK, width=2)
        draw.rectangle([tb_x + 2, tb_y + 2, tb_x + tb_w - 2, tb_y + tb_h - 2], outline=BLACK, width=1)

        # Horizontal dividers
        div1_y = tb_y + tb_h // 3
        div2_y = tb_y + (tb_h * 2) // 3
        draw.line([tb_x, div1_y, tb_x + tb_w, div1_y], fill=BLACK, width=1)
        draw.line([tb_x, div2_y, tb_x + tb_w, div2_y], fill=BLACK, width=1)

        # Vertical divider
        div_v_x = tb_x + tb_w * 2 // 3
        draw.line([div_v_x, tb_y, div_v_x, div2_y], fill=BLACK, width=1)

        # Title block content
        tb_margin = int(img_w_px * 0.006)
        draw.text((tb_x + tb_margin, tb_y + tb_margin),
                   "PROJECT:", font=font_small, fill=MED_GRAY)
        draw.text((tb_x + tb_margin, tb_y + tb_margin + font_small.size + 2),
                   "7G House", font=font_title, fill=BLACK)

        draw.text((tb_x + tb_margin, div1_y + tb_margin),
                   "DRAWING:", font=font_small, fill=MED_GRAY)
        draw.text((tb_x + tb_margin, div1_y + tb_margin + font_small.size + 2),
                   "ARCHITECTURAL", font=font_name, fill=BLACK)
        draw.text((tb_x + tb_margin, div1_y + tb_margin + font_small.size + font_name.size + 4),
                   "FLOOR PLAN", font=font_name, fill=BLACK)

        # Right column
        draw.text((div_v_x + tb_margin, tb_y + tb_margin),
                   "SCALE:", font=font_small, fill=MED_GRAY)
        draw.text((div_v_x + tb_margin, tb_y + tb_margin + font_small.size + 2),
                   "1:100", font=font_name, fill=BLACK)

        draw.text((div_v_x + tb_margin, div1_y + tb_margin),
                   "DATE:", font=font_small, fill=MED_GRAY)
        draw.text((div_v_x + tb_margin, div1_y + tb_margin + font_small.size + 2),
                   datetime.date.today().strftime("%d %b %Y"), font=font_name, fill=BLACK)

        draw.text((div_v_x + tb_margin, div2_y + tb_margin),
                   "JOB NO:", font=font_small, fill=MED_GRAY)
        draw.text((div_v_x + tb_margin, div2_y + tb_margin + font_small.size + 2),
                   "7G-001", font=font_name, fill=BLACK)

        # ── North Arrow ──────────────────────────────────────────────────────
        na_cx = img_w_px - int(img_w_px * 0.06)
        na_cy = int(img_h_px * 0.06)
        na_r = int(img_w_px * 0.018)

        draw.ellipse([na_cx - na_r, na_cy - na_r, na_cx + na_r, na_cy + na_r],
                     outline=BLACK, width=2)
        draw.polygon([
            (na_cx, na_cy - na_r - 5),
            (na_cx - na_r // 3, na_cy),
            (na_cx + na_r // 3, na_cy)
        ], fill=BLACK)
        draw.text((na_cx, na_cy - na_r - 12), "N", font=font_dim, fill=BLACK, anchor="mb")

        # ── Scale Bar ────────────────────────────────────────────────────────
        sb_x = int(img_w_px * 0.04)
        sb_y = img_h_px - int(img_h_px * 0.06)
        sb_length = int(img_w_px * 0.12)
        sb_height = 6

        for i in range(10):
            x1 = sb_x + (sb_length * i) // 10
            x2 = sb_x + (sb_length * (i + 1)) // 10
            color = BLACK if i % 2 == 0 else "#FFFFFF"
            draw.rectangle([x1, sb_y, x2, sb_y + sb_height], fill=color, outline=BLACK)

        draw.text((sb_x, sb_y - 10), "0", font=font_small, fill=BLACK, anchor="lb")
        draw.text((sb_x + sb_length // 2, sb_y - 10), "5m", font=font_small, fill=BLACK, anchor="mb")
        draw.text((sb_x + sb_length, sb_y - 10), "10m", font=font_small, fill=BLACK, anchor="rb")
        draw.text((sb_x, sb_y + sb_height + 4), "SCALE 1:100", font=font_small, fill=BLACK, anchor="lt")

        # ── Legend (Right side) ──────────────────────────────────────────────
        lg_x = img_w_px - int(img_w_px * 0.14)
        lg_y = int(img_h_px * 0.18)
        lg_w = int(img_w_px * 0.11)
        lg_h = int(img_h_px * 0.22)

        draw.rectangle([lg_x, lg_y, lg_x + lg_w, lg_y + lg_h], outline=BLACK, width=1)
        draw.text((lg_x + 8, lg_y + 6), "WALL TYPES:", font=font_dim, fill=BLACK)

        item_y = lg_y + 6 + font_dim.size + 10
        item_h = 24

        draw.rectangle([lg_x + 8, item_y, lg_x + 30, item_y + item_h], fill=BLACK)
        draw.text((lg_x + 36, item_y + 4), "Concrete", font=font_dim, fill=BLACK)
        item_y += item_h + 8

        draw.rectangle([lg_x + 8, item_y, lg_x + 30, item_y + item_h], fill=LIGHT_GRAY)
        draw.rectangle([lg_x + 8, item_y, lg_x + 30, item_y + item_h], outline=BLACK, width=1)
        draw.text((lg_x + 36, item_y + 4), "Blockwork", font=font_dim, fill=BLACK)
        item_y += item_h + 8

        for x in range(lg_x + 8, lg_x + 30, 4):
            draw.line([x, item_y, x, item_y + item_h], fill=BLACK, width=1)
        draw.text((lg_x + 36, item_y + 4), "Drywall", font=font_dim, fill=BLACK)

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

    # Build spatial arrangement description
    spatial_desc = _build_spatial_arrangement(layout)

    # Build opening labels for doors and windows
    door_labels = " ".join([f"D{i+1:02d}" for i in range(len(layout.rooms))])
    window_labels = " ".join([f"W{i+1:02d}" for i in range(len(layout.rooms) * 2)])

    return (
        "Generate a professional architectural 2D floor plan drawing for a single-story "
        "residential house. This is a technical CAD drawing, not an artistic rendering.\n\n"

        "=== VISUAL STYLE (CRITICAL - follow exactly) ===\n"
        "- Black ink lines on clean white background\n"
        "- Pure technical line drawing, NO colors, NO shading, NO gradients, NO 3D effects\n"
        "- Double-line walls with black fill between the lines\n"
        "- Exterior walls thicker (20cm) than interior walls (10cm)\n"
        "- Wall hatching: diagonal crosshatch pattern inside wall cavities\n"
        "- Door symbols: 90-degree arc swing with door leaf line\n"
        "- Window symbols: three parallel lines filling wall thickness\n"
        "- Clean sans-serif font for all text (like Arial or Helvetica)\n"
        "- All text must be BLACK on WHITE background\n"
        "- Drawing border: thin black rectangle around the entire floor plan\n\n"

        "=== BUILDING LAYOUT ===\n"
        f"Building dimensions: {total_w:.1f}m wide x {total_h:.1f}m deep "
        f"({total_area:.1f}m\u00b2)\n\n"

        f"ROOMS (all rooms must tile perfectly within the building rectangle with no gaps "
        f"or overlaps):\n{rooms_text}\n\n"

        f"SPATIAL ARRANGEMENT (room positions relative to each other):\n{spatial_desc}\n\n"

        "=== ARCHITECTURAL ELEMENTS ===\n"
        "WALLS:\n"
        "- Draw as double parallel lines with solid black fill between them\n"
        "- Exterior walls: 20cm thick (thicker lines)\n"
        "- Interior walls: 10cm thick (thinner lines)\n"
        "- Add diagonal crosshatch pattern inside all wall cavities\n\n"

        "DOORS:\n"
        "- Draw as gap in wall with 90-degree arc swing\n"
        "- Arc is thin dashed line, door leaf is solid line\n"
        "- Label each door: D01, D02, D03... in small text near the door\n"
        "- One door per room minimum\n\n"

        "WINDOWS:\n"
        "- Draw as three parallel thin lines filling the wall thickness\n"
        "- Label each window: W01, W02, W03... in small text outside the building\n"
        "- Windows only on exterior walls\n\n"

        "=== ROOM LABELS (CENTERED IN EACH ROOM) ===\n"
        "Format for each room (3 lines):\n"
        "Line 1: Room code in BOLD (e.g., LR1, MBR1, KIT1, BR1, BA1)\n"
        "Line 2: Room name in regular weight (e.g., Living Room, Master Bedroom)\n"
        "Line 3: Area in smaller text (e.g., 25.0 m\u00b2)\n\n"

        "=== DIMENSION LINES (AROUND EXTERIOR) ===\n"
        "- Draw dimension lines along all four exterior walls\n"
        "- Each dimension line has: extension lines, dimension line with arrows, measurement text\n"
        "- Measurements in meters with 2 decimal places (e.g., 5.00, 3.20)\n"
        "- Place dimension lines 15cm outside the building walls\n"
        "- Add tick marks at each end of dimension lines\n\n"

        "=== TITLE BLOCK (BOTTOM RIGHT) ===\n"
        "Rectangle with:\n"
        "- PROJECT: 7G House\n"
        "- DRAWING TITLE: ARCHITECTURAL FLOOR PLAN\n"
        "- SCALE: 1:100\n"
        "- DATE: [Current Date]\n"
        "- JOB NO: 7G-001\n\n"

        "=== OTHER ELEMENTS ===\n"
        "- North arrow indicator in top-right corner\n"
        "- Scale bar at bottom-left\n"
        "- Wall-type legend on right side (Concrete, Blockwork, Drywall)\n\n"

        "=== CRITICAL TEXT REQUIREMENTS ===\n"
        "- ALL text must be CLEARLY LEGIBLE and READABLE\n"
        "- Use consistent font size: larger for room codes, medium for names, small for areas\n"
        "- NO garbled, distorted, or unreadable text\n"
        "- NO overlapping text\n"
        "- Text must be crisp and sharp\n\n"

        "This is a professional architectural CAD drawing. The style should match technical "
        "drawings produced by AutoCAD, Revit, or similar software. Clean, precise, and readable."
    )


def _build_spatial_arrangement(layout: FloorPlanLayout) -> str:
    """Build a human-readable description of room positions."""
    lines = []
    rooms = layout.rooms

    for i, room in enumerate(rooms):
        cx = room.x_cm + room.width_cm / 2
        cy = room.y_cm + room.height_cm / 2
        code = getattr(room, 'room_code', '') or room.name

        neighbors = []
        for j, other in enumerate(rooms):
            if i == j:
                continue
            ocx = other.x_cm + other.width_cm / 2
            ocy = other.y_cm + other.height_cm / 2
            other_code = getattr(other, 'room_code', '') or other.name

            dx = ocx - cx
            dy = ocy - cy

            if abs(dx) > abs(dy):
                direction = "RIGHT" if dx > 0 else "LEFT"
            else:
                direction = "BELOW" if dy > 0 else "ABOVE"

            # Check if they share a wall (adjacent)
            shares_wall = False
            if abs(dx) > abs(dy):
                # Horizontal neighbors - check vertical alignment
                overlap_y = min(room.y_cm + room.height_cm, other.y_cm + other.height_cm) - max(room.y_cm, other.y_cm)
                if overlap_y > min(room.height_cm, other.height_cm) * 0.3:
                    shares_wall = True
            else:
                # Vertical neighbors - check horizontal alignment
                overlap_x = min(room.x_cm + room.width_cm, other.x_cm + other.width_cm) - max(room.x_cm, other.x_cm)
                if overlap_x > min(room.width_cm, other.width_cm) * 0.3:
                    shares_wall = True

            if shares_wall:
                neighbors.append(f"  {code} is adjacent to {other_code} on the {direction}")

        if neighbors:
            lines.extend(neighbors)

    return "\n".join(lines) if lines else "Standard rectangular arrangement."


# ── Post-Processing: Overlay Clean Text ─────────────────────────────────────

def _overlay_clean_labels(img_bytes: bytes, layout: FloorPlanLayout, annotated: bool = False) -> bytes:
    """
    Post-process AI-generated floor plan by overlaying clean, crisp text labels
    and architectural elements (dimensions, title block, legend).
    This replaces garbled AI text with proper rendered text using PIL.
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    img_w, img_h = img.size

    # Calculate scale factors from layout to image
    layout_w = layout.total_width_cm
    layout_h = layout.total_height_cm

    # Determine mapping: layout coordinates to image pixels
    # Reserve margins for dimensions, title block, and legend
    margin_top = img_h * 0.08
    margin_bottom = img_h * 0.18  # Extra space for title block
    margin_left = img_w * 0.08
    margin_right = img_w * 0.15  # Extra space for legend

    usable_w = img_w - margin_left - margin_right
    usable_h = img_h - margin_top - margin_bottom

    scale_x = usable_w / layout_w
    scale_y = usable_h / layout_h
    scale = min(scale_x, scale_y)

    def to_px(x_cm, y_cm):
        px = margin_left + x_cm * scale
        py = margin_top + y_cm * scale
        return int(px), int(py)

    # Load fonts
    font_code = font_name = font_area = font_dim = font_title = font_small = font_legend = None
    try:
        font_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "fonts", "NotoSans-Variable.ttf"
        )
        if os.path.exists(font_path):
            font_code = ImageFont.truetype(font_path, max(28, int(img_w * 0.028)))
            font_name = ImageFont.truetype(font_path, max(20, int(img_w * 0.020)))
            font_area = ImageFont.truetype(font_path, max(14, int(img_w * 0.014)))
            font_dim = ImageFont.truetype(font_path, max(16, int(img_w * 0.016)))
            font_title = ImageFont.truetype(font_path, max(22, int(img_w * 0.022)))
            font_small = ImageFont.truetype(font_path, max(12, int(img_w * 0.012)))
            font_legend = ImageFont.truetype(font_path, max(14, int(img_w * 0.014)))
    except (OSError, FileNotFoundError):
        pass

    if font_code is None:
        font_code = ImageFont.load_default()
        font_name = font_code
        font_area = font_code
        font_dim = font_code
        font_title = font_code
        font_small = font_code
        font_legend = font_code

    # Colors
    BLACK = (26, 26, 26, 255)
    DARK_GRAY = (51, 51, 51, 255)
    MED_GRAY = (102, 102, 102, 255)
    LIGHT_GRAY = (180, 180, 180, 255)
    WHITE_BG = (255, 255, 255, 220)
    DIM_COLOR = (80, 80, 80, 255)

    # ── Room Labels ──────────────────────────────────────────────────────────
    for room in layout.rooms:
        cx, cy = to_px(room.x_cm + room.width_cm / 2, room.y_cm + room.height_cm / 2)
        code = getattr(room, 'room_code', '') or ''
        area_m2 = (room.width_cm * room.height_cm) / 10000

        # Calculate text block height
        text_lines = []
        if code:
            text_lines = [
                (code, font_code, BLACK, 6),
                (room.name, font_name, DARK_GRAY, 3),
                (f"{area_m2:.1f} m\u00b2", font_area, MED_GRAY, 0),
            ]
        else:
            text_lines = [
                (room.name, font_name, DARK_GRAY, 4),
                (f"{area_m2:.1f} m\u00b2", font_area, MED_GRAY, 0),
            ]

        total_text_h = sum(font.size + gap for _, font, _, gap in text_lines)

        # Draw semi-transparent white background for readability
        bg_pad = int(img_w * 0.010)
        bg_w = int(img_w * 0.14)
        bg_h = total_text_h + bg_pad * 2
        bg_x = cx - bg_w // 2
        bg_y = cy - bg_h // 2
        draw.rounded_rectangle(
            [bg_x, bg_y, bg_x + bg_w, bg_y + bg_h],
            radius=4, fill=WHITE_BG
        )

        # Draw text lines
        text_y = bg_y + bg_pad
        for text, font, color, gap in text_lines:
            draw.text((cx, text_y), text, font=font, fill=color, anchor="mt")
            text_y += font.size + gap

    # ── Dimension Lines (around exterior) ────────────────────────────────────
    if annotated:
        min_x = min(r.x_cm for r in layout.rooms)
        max_x = max(r.x_cm + r.width_cm for r in layout.rooms)
        min_y = min(r.y_cm for r in layout.rooms)
        max_y = max(r.y_cm + r.height_cm for r in layout.rooms)

        total_w_m = (max_x - min_x) / 100
        total_h_m = (max_y - min_y) / 100

        # Collect room edges for dimension chain segments
        x_edges = sorted(set([min_x] + [r.x_cm for r in layout.rooms] +
                             [r.x_cm + r.width_cm for r in layout.rooms] + [max_x]))
        y_edges = sorted(set([min_y] + [r.y_cm for r in layout.rooms] +
                             [r.y_cm + r.height_cm for r in layout.rooms] + [max_y]))

        def draw_dimension_chain_h(y_pos, x_start, x_end, offset_y, draw_left=True, draw_right=True):
            """Draw horizontal dimension chain with segment measurements."""
            px_start = to_px(x_start, 0)[0]
            px_end = to_px(x_end, 0)[0]
            py = to_px(0, y_pos)[1] + offset_y

            # Main dimension line
            draw.line([px_start, py, px_end, py], fill=DIM_COLOR, width=2)

            # Tick marks at ends
            tick_h = 12
            draw.line([px_start, py - tick_h, px_start, py + tick_h], fill=DIM_COLOR, width=2)
            draw.line([px_end, py - tick_h, px_end, py + tick_h], fill=DIM_COLOR, width=2)

            # Extension lines from building to dimension line
            ext_start = to_px(x_start, 0)[0]
            ext_end = to_px(x_end, 0)[0]
            build_y = to_px(0, y_pos)[1]
            draw.line([ext_start, build_y, ext_start, py], fill=LIGHT_GRAY, width=1)
            draw.line([ext_end, build_y, ext_end, py], fill=LIGHT_GRAY, width=1)

            # Segment measurements
            for i in range(len(x_edges) - 1):
                seg_x1 = x_edges[i]
                seg_x2 = x_edges[i + 1]
                if seg_x2 - seg_x1 < 50:  # Skip tiny segments
                    continue
                seg_px1 = to_px(seg_x1, 0)[0]
                seg_px2 = to_px(seg_x2, 0)[0]
                seg_mid = (seg_px1 + seg_px2) // 2
                seg_m = (seg_x2 - seg_x1) / 100

                # Tick marks for segments
                draw.line([seg_px1, py - tick_h // 2, seg_px1, py + tick_h // 2], fill=DIM_COLOR, width=1)
                draw.line([seg_px2, py - tick_h // 2, seg_px2, py + tick_h // 2], fill=DIM_COLOR, width=1)

                # Measurement text
                draw.text((seg_mid, py - 16), f"{seg_m:.2f}", font=font_dim, fill=DIM_COLOR, anchor="mb")

            # Overall dimension
            overall_mid = (px_start + px_end) // 2
            draw.text((overall_mid, py + 18), f"{(x_end - x_start) / 100:.2f} m",
                       font=font_small, fill=DIM_COLOR, anchor="mt")

        def draw_dimension_chain_v(x_pos, y_start, y_end, offset_x, draw_top=True, draw_bottom=True):
            """Draw vertical dimension chain with segment measurements."""
            px = to_px(x_pos, 0)[0] + offset_x
            py_start = to_px(0, y_start)[1]
            py_end = to_px(0, y_end)[1]

            # Main dimension line
            draw.line([px, py_start, px, py_end], fill=DIM_COLOR, width=2)

            # Tick marks at ends
            tick_w = 12
            draw.line([px - tick_w, py_start, px + tick_w, py_start], fill=DIM_COLOR, width=2)
            draw.line([px - tick_w, py_end, px + tick_w, py_end], fill=DIM_COLOR, width=2)

            # Extension lines
            build_x = to_px(x_pos, 0)[0]
            draw.line([build_x, py_start, px, py_start], fill=LIGHT_GRAY, width=1)
            draw.line([build_x, py_end, px, py_end], fill=LIGHT_GRAY, width=1)

            # Segment measurements
            for i in range(len(y_edges) - 1):
                seg_y1 = y_edges[i]
                seg_y2 = y_edges[i + 1]
                if seg_y2 - seg_y1 < 50:  # Skip tiny segments
                    continue
                seg_py1 = to_px(0, seg_y1)[1]
                seg_py2 = to_px(0, seg_y2)[1]
                seg_mid = (seg_py1 + seg_py2) // 2
                seg_m = (seg_y2 - seg_y1) / 100

                # Tick marks for segments
                draw.line([px - tick_w // 2, seg_py1, px + tick_w // 2, seg_py1], fill=DIM_COLOR, width=1)
                draw.line([px - tick_w // 2, seg_py2, px + tick_w // 2, seg_py2], fill=DIM_COLOR, width=1)

                # Measurement text (rotated not supported, place to the side)
                draw.text((px + 18, seg_mid), f"{seg_m:.2f}", font=font_dim, fill=DIM_COLOR, anchor="lm")

            # Overall dimension
            overall_mid = (py_start + py_end) // 2
            draw.text((px - 18, overall_mid), f"{(y_end - y_start) / 100:.2f} m",
                       font=font_small, fill=DIM_COLOR, anchor="rm")

        # Bottom dimensions
        draw_dimension_chain_h(max_y, min_x, max_x, int(img_h * 0.08))
        # Top dimensions
        draw_dimension_chain_h(min_y, min_x, max_x, -int(img_h * 0.08))
        # Left dimensions
        draw_dimension_chain_v(min_x, min_y, max_y, -int(img_w * 0.10))
        # Right dimensions
        draw_dimension_chain_v(max_x, min_y, max_y, int(img_w * 0.10))

        # ── Title Block (Bottom Right) ───────────────────────────────────────
        tb_w = int(img_w * 0.30)
        tb_h = int(img_h * 0.14)
        tb_x = img_w - tb_w - int(img_w * 0.03)
        tb_y = img_h - tb_h - int(img_h * 0.03)

        # Title block border
        draw.rectangle([tb_x, tb_y, tb_x + tb_w, tb_y + tb_h], outline=BLACK, width=2)
        draw.rectangle([tb_x + 2, tb_y + 2, tb_x + tb_w - 2, tb_y + tb_h - 2], outline=BLACK, width=1)

        # Horizontal dividers
        div1_y = tb_y + tb_h // 3
        div2_y = tb_y + (tb_h * 2) // 3
        draw.line([tb_x, div1_y, tb_x + tb_w, div1_y], fill=BLACK, width=1)
        draw.line([tb_x, div2_y, tb_x + tb_w, div2_y], fill=BLACK, width=1)

        # Vertical divider
        div_v_x = tb_x + tb_w * 2 // 3
        draw.line([div_v_x, tb_y, div_v_x, div2_y], fill=BLACK, width=1)

        # Title block content
        tb_margin = int(img_w * 0.008)
        draw.text((tb_x + tb_margin, tb_y + tb_margin),
                   "PROJECT:", font=font_small, fill=MED_GRAY)
        draw.text((tb_x + tb_margin, tb_y + tb_margin + font_small.size + 2),
                   "7G House", font=font_title, fill=BLACK)

        draw.text((tb_x + tb_margin, div1_y + tb_margin),
                   "DRAWING:", font=font_small, fill=MED_GRAY)
        draw.text((tb_x + tb_margin, div1_y + tb_margin + font_small.size + 2),
                   "ARCHITECTURAL", font=font_name, fill=BLACK)
        draw.text((tb_x + tb_margin, div1_y + tb_margin + font_small.size + font_name.size + 4),
                   "FLOOR PLAN", font=font_name, fill=BLACK)

        # Right column
        draw.text((div_v_x + tb_margin, tb_y + tb_margin),
                   "SCALE:", font=font_small, fill=MED_GRAY)
        draw.text((div_v_x + tb_margin, tb_y + tb_margin + font_small.size + 2),
                   "1:100", font=font_name, fill=BLACK)

        draw.text((div_v_x + tb_margin, div1_y + tb_margin),
                   "DATE:", font=font_small, fill=MED_GRAY)
        draw.text((div_v_x + tb_margin, div1_y + tb_margin + font_small.size + 2),
                   datetime.date.today().strftime("%d %b %Y"), font=font_name, fill=BLACK)

        draw.text((div_v_x + tb_margin, div2_y + tb_margin),
                   "JOB NO:", font=font_small, fill=MED_GRAY)
        draw.text((div_v_x + tb_margin, div2_y + tb_margin + font_small.size + 2),
                   "7G-001", font=font_name, fill=BLACK)

        # ── North Arrow ──────────────────────────────────────────────────────
        na_cx = img_w - int(img_w * 0.06)
        na_cy = int(img_h * 0.06)
        na_r = int(img_w * 0.018)

        # Circle
        draw.ellipse([na_cx - na_r, na_cy - na_r, na_cx + na_r, na_cy + na_r],
                     outline=BLACK, width=2)
        # Arrow pointing up (North)
        draw.polygon([
            (na_cx, na_cy - na_r - 5),
            (na_cx - na_r // 3, na_cy),
            (na_cx + na_r // 3, na_cy)
        ], fill=BLACK)
        draw.text((na_cx, na_cy - na_r - 12), "N", font=font_dim, fill=BLACK, anchor="mb")

        # ── Scale Bar ────────────────────────────────────────────────────────
        sb_x = int(img_w * 0.04)
        sb_y = img_h - int(img_h * 0.06)
        sb_length = int(img_w * 0.12)
        sb_height = 6

        # Scale bar (10m)
        for i in range(10):
            x1 = sb_x + (sb_length * i) // 10
            x2 = sb_x + (sb_length * (i + 1)) // 10
            color = BLACK if i % 2 == 0 else WHITE_BG[:3] + (255,)
            draw.rectangle([x1, sb_y, x2, sb_y + sb_height], fill=color, outline=BLACK)

        # Scale labels
        draw.text((sb_x, sb_y - 10), "0", font=font_small, fill=BLACK, anchor="lb")
        draw.text((sb_x + sb_length // 2, sb_y - 10), "5m", font=font_small, fill=BLACK, anchor="mb")
        draw.text((sb_x + sb_length, sb_y - 10), "10m", font=font_small, fill=BLACK, anchor="rb")

        # Scale text
        draw.text((sb_x, sb_y + sb_height + 4), "SCALE 1:100", font=font_small, fill=BLACK, anchor="lt")

        # ── Legend (Right side) ──────────────────────────────────────────────
        lg_x = img_w - int(img_w * 0.14)
        lg_y = int(img_h * 0.18)
        lg_w = int(img_w * 0.11)
        lg_h = int(img_h * 0.22)

        # Legend border
        draw.rectangle([lg_x, lg_y, lg_x + lg_w, lg_y + lg_h], outline=BLACK, width=1)

        # Legend title
        draw.text((lg_x + 8, lg_y + 6), "WALL TYPES:", font=font_legend, fill=BLACK)

        # Legend items
        item_y = lg_y + 6 + font_legend.size + 10
        item_h = 24

        # Concrete wall
        draw.rectangle([lg_x + 8, item_y, lg_x + 30, item_y + item_h], fill=BLACK)
        draw.text((lg_x + 36, item_y + 4), "Concrete", font=font_legend, fill=BLACK)
        item_y += item_h + 8

        # Blockwork wall
        draw.rectangle([lg_x + 8, item_y, lg_x + 30, item_y + item_h], fill=LIGHT_GRAY)
        draw.rectangle([lg_x + 8, item_y, lg_x + 30, item_y + item_h], outline=BLACK, width=1)
        draw.text((lg_x + 36, item_y + 4), "Blockwork", font=font_legend, fill=BLACK)
        item_y += item_h + 8

        # Drywall
        for x in range(lg_x + 8, lg_x + 30, 4):
            draw.line([x, item_y, x, item_y + item_h], fill=BLACK, width=1)
        draw.text((lg_x + 36, item_y + 4), "Drywall", font=font_legend, fill=BLACK)

    # Composite
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


# ── Main Entry Point ────────────────────────────────────────────────────────

async def render_floor_plan_ai(
    layout: FloorPlanLayout,
    annotated: bool = False,
) -> Optional[bytes]:
    """
    Generate a floor plan image using deterministic PIL renderer.

    Floor plans require precision (exact room positions, walls, dimensions)
    that AI image generators cannot provide. Imagen produces artistic
    interpretations, not technical CAD drawings. Using PIL directly:
    - Renders in <1 second (vs 60-120s for Imagen)
    - 100% consistent output
    - Precise room positions matching the layout data
    - Professional architectural styling

    Returns:
        PNG image as bytes, or None on total failure.
    """
    print(f"[FloorPlanAI] Rendering deterministic floor plan (annotated={annotated})...")
    img_bytes = await asyncio.to_thread(_render_fallback, layout, annotated)
    print(f"[FloorPlanAI] Done: {len(img_bytes)} bytes")
    return img_bytes
