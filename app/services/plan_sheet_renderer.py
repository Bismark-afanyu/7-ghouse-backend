"""Professional architectural plan-sheet renderer.

Renders a real-geometry floor plan (FloorPlanLayout) as a presentation-grade
architectural sheet — solid wall poché, door swings, window symbols, dimension
chains, furniture, title block, north arrow, scale bar — in two styles:

  style="bw"    pure black-and-white CAD sheet (technical deliverable)
  style="color" color-zoned concept plan (client presentation)

All text is drawn deterministically from layout data (never AI-generated), and
the same module renders the room-schedule table. PNG only; the DXF twin lives
in autocad_drafter.
"""
import io
import os
from datetime import date
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.services.floor_plan_layout import FloorPlanLayout, RoomLayout, _build_wall_segments, _wall_length

FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fonts", "NotoSans-Variable.ttf"
)

# ── Palette ──────────────────────────────────────────────────────────────────
INK = "#1f2328"
INK_SOFT = "#5a5f66"
INK_FAINT = "#9aa0a8"
WALL_FILL = "#26292e"
PAPER = "#FFFFFF"

ROOM_FILLS = {
    "living": "#F3E7D3",
    "dining": "#F3E7D3",
    "kitchen": "#EAD9C2",
    "bedroom": "#DDE6F0",
    "bathroom": "#D5E3DF",
    "wc": "#D5E3DF",
    "stairs": "#EDEDED",
    "corridor": "#F0EEEA",
    "other": "#F1EFE9",
}

SHEET_W_PX = 2480
MARGIN_CM_X = 620.0   # room for two dimension chains each side
MARGIN_CM_Y = 700.0

WALL_EXT_CM = 20.0
WALL_INT_CM = 12.0


def _font(size: int, bold: bool = False):
    try:
        f = ImageFont.truetype(FONT_PATH, size)
        try:
            f.set_variation_by_name("Bold" if bold else "Regular")
        except Exception:
            pass
        return f
    except (OSError, FileNotFoundError):
        return ImageFont.load_default()


def _norm_type(room: RoomLayout) -> str:
    """Normalize room_type/name to a furniture/fill category."""
    rt = (room.room_type or "").lower()
    name = (room.name or "").lower()
    if "master" in rt or "master" in name:
        return "bedroom"
    if "bedroom" in rt or "chambre" in name:
        return "bedroom"
    if "bath" in rt or "wc" in rt or "bain" in name or "toilet" in rt:
        return "bathroom"
    if "kitchen" in rt or "cuisine" in name:
        return "kitchen"
    if "dining" in rt or "salle" in name:
        return "dining"
    if "living" in rt or "salon" in name or "séjour" in name:
        return "living"
    if "stair" in rt or "escalier" in name or "stair" in name:
        return "stairs"
    if "hall" in rt or "corridor" in rt or "couloir" in name:
        return "corridor"
    return "other"


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _envelope(layout: FloorPlanLayout):
    xs = [r.x_cm for r in layout.rooms] + [r.x_cm + r.width_cm for r in layout.rooms]
    ys = [r.y_cm for r in layout.rooms] + [r.y_cm + r.height_cm for r in layout.rooms]
    return min(xs), min(ys), max(xs), max(ys)


def _classify_exterior_edges(layout: FloorPlanLayout) -> set:
    """Return a set of (room_id, side) for edges on the building exterior."""
    walls = _build_wall_segments(layout)
    ext = set()
    for w in walls:
        if w["shared"] or _wall_length(w) < 1:
            continue
        for room in w["rooms"]:
            ext.add((id(room), w["side"]))
    return ext


def _wall_thickness(layout, ext_edges, room: RoomLayout, side: str) -> float:
    return WALL_EXT_CM if (id(room), side) in ext_edges else WALL_INT_CM


# ── Furniture primitives (thin-line architectural symbols) ───────────────────

def _draw_bed(d, x1, y1, x2, y2, double: bool, line, lw=2):
    d.rectangle([x1, y1, x2, y2], outline=line, width=lw)
    head = (y2 - y1) * 0.14
    d.line([x1, y1 + head, x2, y1 + head], fill=line, width=lw)  # headboard
    pw = (x2 - x1) * (0.38 if double else 0.72)
    n = 2 if double else 1
    for i in range(n):
        px1 = x1 + (x2 - x1) * (0.08 + i * 0.48) if double else x1 + (x2 - x1) * 0.14
        d.rounded_rectangle([px1, y1 + head * 0.2, px1 + pw, y1 + head * 0.95],
                            radius=5, outline=line, width=1)
    fold = y1 + (y2 - y1) * 0.62
    d.line([x1, fold, x2, fold], fill=line, width=1)  # blanket fold
    d.line([x1, fold + (y2 - y1) * 0.06, x2, fold + (y2 - y1) * 0.06], fill=line, width=1)


def _draw_wardrobe(d, x1, y1, x2, y2, line, vertical: bool = False, lw=2):
    d.rectangle([x1, y1, x2, y2], outline=line, width=lw)
    if vertical:
        mid = (x1 + x2) / 2
        d.line([mid, y1, mid, y2], fill=line, width=1)
    else:
        mid = (y1 + y2) / 2
        d.line([x1, mid, x2, mid], fill=line, width=1)
        # hanging rail ticks
        for xx in range(int(x1) + 8, int(x2) - 8, 14):
            d.line([xx, mid + 2, xx, y2 - 3], fill=line, width=1)


def _draw_sofa(d, x1, y1, x2, y2, line, lw=2, vertical: bool = False):
    d.rounded_rectangle([x1, y1, x2, y2], radius=8, outline=line, width=lw)
    if not vertical:
        back = (y2 - y1) * 0.24
        d.line([x1, y1 + back, x2, y1 + back], fill=line, width=lw)
        for i in (1, 2):
            d.line([x1 + (x2 - x1) * i / 3, y1 + back, x1 + (x2 - x1) * i / 3, y2], fill=line, width=1)
    else:
        back = (x2 - x1) * 0.24
        d.line([x1 + back, y1, x1 + back, y2], fill=line, width=lw)
        for i in (1, 2):
            d.line([x1 + back, y1 + (y2 - y1) * i / 3, x2, y1 + (y2 - y1) * i / 3], fill=line, width=1)


def _draw_table(d, cx, cy, w, h, chairs: int, line, lw=2):
    import math
    d.rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], outline=line, width=lw)
    ch = min(w, h) * 0.2
    for i in range(chairs):
        ang = i * (360 / max(chairs, 1))
        rx, ry = (w / 2 + ch * 1.25), (h / 2 + ch * 1.25)
        px = cx + rx * math.cos(math.radians(ang))
        py = cy + ry * math.sin(math.radians(ang))
        d.rectangle([px - ch / 2, py - ch / 2, px + ch / 2, py + ch / 2], outline=line, width=1)


def _draw_kitchen(d, room, s, tx, ty, line, lw=2):
    x1, y1 = tx(room.x_cm), ty(room.y_cm)
    x2, y2 = tx(room.x_cm + room.width_cm), ty(room.y_cm + room.height_cm)
    depth = int(60 * s)
    d.rectangle([x1 + 4, y1 + 4, x2 - 4, y1 + 4 + depth], outline=line, width=lw)
    sw = int(50 * s)
    sx = x1 + int((x2 - x1) * 0.25)
    sy = y1 + 4 + depth // 2
    d.rectangle([sx - sw, sy - sw // 2, sx, sy + sw // 2], outline=line, width=1)
    d.rectangle([sx, sy - sw // 2, sx + sw, sy + sw // 2], outline=line, width=1)
    d.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], outline=line, width=1)
    hx = x2 - int((x2 - x1) * 0.18)
    r = int(13 * s)
    for dx in (-int(17 * s), int(17 * s)):
        for dy in (-int(17 * s), int(17 * s)):
            d.ellipse([hx + dx - r, sy + dy - r, hx + dx + r, sy + dy + r], outline=line, width=1)


def _draw_wc(d, x1, y1, x2, y2, line, lw=2):
    cx = (x1 + x2) / 2
    tw = min((x2 - x1), (y2 - y1)) * 0.6
    d.rectangle([cx - tw / 2, y1 + 2, cx + tw / 2, y1 + (y2 - y1) * 0.2], outline=line, width=lw)
    d.ellipse([cx - tw * 0.36, y1 + (y2 - y1) * 0.22, cx + tw * 0.36, y1 + (y2 - y1) * 0.85], outline=line, width=lw)


def _draw_shower(d, x1, y1, x2, y2, line, lw=2):
    d.rectangle([x1, y1, x2, y2], outline=line, width=lw)
    d.line([x1, y1, x2, y2], fill=line, width=1)
    d.line([x2, y1, x1, y2], fill=line, width=1)
    r = min(x2 - x1, y2 - y1) * 0.1
    d.ellipse([(x1 + x2) / 2 - r, (y1 + y2) / 2 - r, (x1 + x2) / 2 + r, (y1 + y2) / 2 + r], outline=line, width=1)


def _draw_bath(d, x1, y1, x2, y2, line, lw=2):
    d.rectangle([x1, y1, x2, y2], outline=line, width=lw)
    inset_x = (x2 - x1) * 0.14
    inset_y = (y2 - y1) * 0.18
    d.rounded_rectangle([x1 + inset_x, y1 + inset_y, x2 - inset_x, y2 - inset_y],
                        radius=int((y2 - y1) * 0.16), outline=line, width=1)
    d.ellipse([x2 - inset_x * 1.7 - 4, (y1 + y2) / 2 - 4, x2 - inset_x * 1.7 + 4, (y1 + y2) / 2 + 4], outline=line, width=1)


def _draw_basin(d, x1, y1, x2, y2, line, lw=2):
    d.ellipse([x1, y1, x2, y2], outline=line, width=lw)
    d.ellipse([(x1 + x2) / 2 - 3, (y1 + y2) / 2 - 3, (x1 + x2) / 2 + 3, (y1 + y2) / 2 + 3], outline=line, width=1)


def _draw_stairs(d, room, s, tx, ty, line, font_small):
    x1, y1 = tx(room.x_cm), ty(room.y_cm)
    x2, y2 = tx(room.x_cm + room.width_cm), ty(room.y_cm + room.height_cm)
    n = 8
    for i in range(1, n):
        yy = y1 + (y2 - y1) * i / n
        d.line([x1, yy, x2, yy], fill=line, width=1)
    d.line([x1, y1, x1, y2], fill=line, width=2)
    mid_x = (x1 + x2) / 2
    d.line([mid_x, y2 - 6, mid_x, y1 + 6], fill=line, width=1)
    d.polygon([(mid_x - 6, y1 + 16), (mid_x + 6, y1 + 16), (mid_x, y1 + 4)], fill=line)
    d.text((mid_x, (y1 + y2) / 2), "UP", font=font_small, fill=line, anchor="mm")


def _draw_furniture(d, layout: FloorPlanLayout, s, tx, ty, line, font_small):
    lw = 2
    for room in layout.rooms:
        rt = _norm_type(room)
        pad = 10 * s
        x1, y1 = tx(room.x_cm) + pad, ty(room.y_cm) + pad
        x2, y2 = tx(room.x_cm + room.width_cm) - pad, ty(room.y_cm + room.height_cm) - pad
        rw_cm, rh_cm = room.width_cm, room.height_cm
        w_px, h_px = x2 - x1, y2 - y1
        if w_px < 26 * s or h_px < 26 * s:
            continue

        if rt == "bedroom":
            # Bed centred on the top wall, 150×200cm (double) or 100×200 (single)
            double = (rw_cm * rh_cm) >= 100000
            bed_w_cm = min(150 if double else 100, rw_cm - 70)
            bed_h_cm = min(200, rh_cm - 80)
            bx1 = tx(room.x_cm + (rw_cm - bed_w_cm) / 2)
            bx2 = bx1 + bed_w_cm * s
            by1, by2 = ty(room.y_cm) + 8, ty(room.y_cm) + 8 + bed_h_cm * s
            _draw_bed(d, bx1, by1, bx2, by2, double=double, line=line, lw=lw)
            # Wardrobe along the bottom wall, right side
            wr_w = min(60, rw_cm * 0.25) * s
            wr_h = min(180, rh_cm - 90) * s
            _draw_wardrobe(d, x2 - wr_w, y2 - wr_h, x2, y2, line, vertical=False, lw=lw)
            # Nightstand beside bed
            ns = 40 * s
            d.rectangle([bx1 - ns - 6, by1, bx1 - 6, by1 + ns], outline=line, width=1)
            d.rectangle([bx2 + 6, by1, bx2 + 6 + ns, by1 + ns], outline=line, width=1)

        elif rt == "bathroom":
            if (x2 - x1) >= (y2 - y1):
                third = x1 + w_px * 0.34
                _draw_wc(d, x1, y1, third - 6, y1 + h_px * 0.42, line, lw)
                _draw_shower(d, x1, y1 + h_px * 0.52, third - 6, y2, line, lw)
                _draw_bath(d, third + 6, y1, x2, y1 + h_px * 0.48, line, lw)
                bs = min(46 * s, h_px * 0.3)
                _draw_basin(d, third + 20, y2 - bs, third + 20 + bs * 1.2, y2, line, lw)
            else:
                half = y1 + h_px * 0.45
                _draw_wc(d, x1, y1, x1 + w_px * 0.48, half - 6, line, lw)
                _draw_shower(d, x1, half + 6, x1 + w_px * 0.48, y2, line, lw)
                _draw_bath(d, x1 + w_px * 0.55, y1, x2, y1 + h_px * 0.5, line, lw)
                bs = min(44 * s, w_px * 0.3)
                _draw_basin(d, x1 + w_px * 0.55, y1 + h_px * 0.58, x1 + w_px * 0.55 + bs, y1 + h_px * 0.58 + bs, line, lw)

        elif rt == "kitchen":
            _draw_kitchen(d, room, s, tx, ty, line, lw)
            if rw_cm > 300 and rh_cm > 260:
                _draw_table(d, (x1 + x2) / 2, y2 - (y2 - y1) * 0.22,
                            min(150 * s, w_px * 0.4), min(90 * s, h_px * 0.2), 4, line, lw)

        elif rt == "living":
            # Sofa along bottom wall + TV line on top wall + coffee table
            sofa_h = min(85 * s, h_px * 0.28)
            _draw_sofa(d, x1 + w_px * 0.05, y2 - sofa_h, x1 + w_px * 0.55, y2, line, lw)
            _draw_sofa(d, x2 - min(70 * s, w_px * 0.14), y2 - min(220 * s, h_px * 0.7),
                       x2, y2, line, lw, vertical=True)
            ct_w = min(110 * s, w_px * 0.24)
            ct_h = min(60 * s, h_px * 0.16)
            ccx, ccy = x1 + w_px * 0.3, y2 - sofa_h - ct_h
            d.rectangle([ccx - ct_w / 2, ccy - ct_h / 2, ccx + ct_w / 2, ccy + ct_h / 2],
                        outline=line, width=lw)
            tv_w = w_px * 0.34
            d.line([ccx - tv_w / 2, y1 + 6, ccx + tv_w / 2, y1 + 6], fill=line, width=3)

        elif rt in ("dining",):
            _draw_table(d, (x1 + x2) / 2, (y1 + y2) / 2,
                        min(200 * s, w_px * 0.55), min(100 * s, h_px * 0.42), 6, line, lw)

        elif "stair" in rt or "stair" in room.name.lower() or "escalier" in room.name.lower():
            _draw_stairs(d, room, s, tx, ty, line, font_small)


# ── Sheet furniture ──────────────────────────────────────────────────────────

def _draw_dimension_chain(d, p1, p2, offset_pt, get_seg_text, font_dim, color, tick=10, side="h"):
    """One dimension chain between two points, offset perpendicular.

    side='h': horizontal chain, offset_pt = (y, direction); side='v': vertical.
    """
    (x1, y1), (x2, y2) = p1, p2
    if side == "h":
        yo = offset_pt[0]
        d.line([x1, yo, x2, yo], fill=color, width=2)
        d.line([x1, y1, x1, yo + (12 if yo > y1 else -12)], fill=INK_FAINT, width=1)
        d.line([x2, y2, x2, yo + (12 if yo > y2 else -12)], fill=INK_FAINT, width=1)
        for (sx, ex, text) in get_seg_text():
            sxp, exp = sx, ex
            d.line([sxp, yo - tick, sxp, yo + tick], fill=color, width=1)
            d.line([exp, yo - tick, exp, yo + tick], fill=color, width=1)
            # architectural tick: short 45° slash
            d.line([sxp - 6, yo + 6, sxp + 6, yo - 6], fill=color, width=2)
            d.line([exp - 6, yo + 6, exp + 6, yo - 6], fill=color, width=2)
            mid = (sxp + exp) / 2
            d.text((mid, yo - 10), text, font=font_dim, fill=color, anchor="mb")
    else:
        xo = offset_pt[0]
        d.line([xo, y1, xo, y2], fill=color, width=2)
        d.line([x1, y1, xo + (12 if xo > x1 else -12), y1], fill=INK_FAINT, width=1)
        d.line([x2, y2, xo + (12 if xo > x2 else -12), y2], fill=INK_FAINT, width=1)
        for (sy, ey, text) in get_seg_text():
            syp, eyp = sy, ey
            d.line([xo - tick, syp, xo + tick, syp], fill=color, width=1)
            d.line([xo - tick, eyp, xo + tick, eyp], fill=color, width=1)
            d.line([xo - 6, syp + 6, xo + 6, syp - 6], fill=color, width=2)
            d.line([xo - 6, eyp + 6, xo + 6, eyp - 6], fill=color, width=2)
            mid = (syp + eyp) / 2
            d.text((xo - 10, mid), text, font=font_dim, fill=color, anchor="rm")


def _draw_title_block(d, img_w, img_h, project, drawing_title, sheet_no, lang):
    labels = {
        "en": ("PROJECT", "DRAWING TITLE", "SCALE", "DATE", "SHEET", "DRAWN BY"),
        "fr": ("PROJET", "TITRE DU DESSIN", "ÉCHELLE", "DATE", "FEUILLE", "DESSINÉ PAR"),
    }[lang]
    rows = [
        (labels[0], project or "7G House Residence"),
        (labels[1], drawing_title),
        (labels[2], "1:100 @ A3"),
        (labels[3], date.today().strftime("%d.%m.%Y")),
        (labels[4], sheet_no),
        (labels[5], "7G House AI"),
    ]
    tw, rh = 560, 46
    x1, y1 = img_w - tw - 24, img_h - rh * len(rows) - 24
    font_lbl = _font(20, bold=True)
    font_val = _font(22)
    for i, (lbl, val) in enumerate(rows):
        ry = y1 + i * rh
        d.rectangle([x1, ry, x1 + tw, ry + rh], outline=INK, width=1)
        d.text((x1 + 12, ry + rh / 2), lbl, font=font_lbl, fill=INK_SOFT, anchor="lm")
        d.text((x1 + 250, ry + rh / 2), str(val), font=font_val, fill=INK, anchor="lm")
    # Brand row on top
    d.rectangle([x1, y1 - 54, x1 + tw, y1], fill=WALL_FILL)
    d.text((x1 + 12, y1 - 27), "7G HOUSE", font=_font(30, bold=True), fill="#FFFFFF", anchor="lm")
    d.text((x1 + tw - 12, y1 - 27), "AI DESIGN STUDIO", font=_font(18), fill="#BBBBBB", anchor="rm")


def _draw_north_arrow(d, cx, cy, r):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=3)
    d.polygon([(cx, cy - r), (cx - r * 0.28, cy + r * 0.35), (cx, cy + r * 0.12)], fill=INK)
    d.polygon([(cx, cy - r), (cx + r * 0.28, cy + r * 0.35), (cx, cy + r * 0.12)], outline=INK, width=2)
    d.text((cx, cy - r - 14), "N", font=_font(30, bold=True), fill=INK, anchor="mb")


def _draw_scale_bar(d, x, y, s, lang):
    seg = 100 * s  # 1 m per segment
    n = 6
    for i in range(n):
        d.rectangle([x + i * seg, y, x + (i + 1) * seg, y + 10],
                    fill=INK if i % 2 == 0 else "#FFFFFF", outline=INK, width=1)
    font_small = _font(22)
    for i in range(n + 1):
        d.text((x + i * seg, y - 8), f"{i}", font=font_small, fill=INK, anchor="mb")
    d.text((x + n * seg + 30, y + 5), "m" if lang == "en" else "m", font=font_small, fill=INK, anchor="lm")
    d.text((x, y + 22), "SCALE 1:100" if lang == "en" else "ÉCHELLE 1:100", font=font_small, fill=INK_SOFT, anchor="lt")


# ── Main sheet renderer ──────────────────────────────────────────────────────

def render_plan_sheet(
    layout: FloorPlanLayout,
    style: str = "bw",
    lang: str = "en",
    project: str = "",
    drawing_title: Optional[str] = None,
    sheet_no: str = "A-101",
) -> bytes:
    style = "color" if style == "color" else "bw"
    ext_edges = _classify_exterior_edges(layout)
    min_x, min_y, max_x, max_y = _envelope(layout)

    env_w = (max_x - min_x) + MARGIN_CM_X * 2
    env_h = (max_y - min_y) + MARGIN_CM_Y * 2
    img_w = SHEET_W_PX
    img_h = int(img_w * env_h / env_w)
    s = img_w / env_w

    img = Image.new("RGB", (img_w, img_h), PAPER)
    d = ImageDraw.Draw(img)

    def tx(x_cm): return int((x_cm - min_x + MARGIN_CM_X) * s)
    def ty(y_cm): return int((y_cm - min_y + MARGIN_CM_Y) * s)

    font_name = _font(max(22, int(30 * s * 2.2)), bold=True)
    font_area = _font(max(16, int(22 * s * 2.0)))
    font_dim = _font(max(16, int(20 * s * 2.0)))
    font_small = _font(max(14, int(18 * s * 2.0)))
    font_title = _font(56, bold=True)

    # ── Sheet border ─────────────────────────────────────────────────────────
    d.rectangle([18, 18, img_w - 18, img_h - 18], outline=INK, width=3)
    d.rectangle([30, 30, img_w - 30, img_h - 30], outline=INK, width=1)

    # ── Title ────────────────────────────────────────────────────────────────
    title = drawing_title or ("GROUND FLOOR PLAN" if layout.num_stories <= 1 else "GROUND FLOOR PLAN")
    d.text((img_w / 2, 92), title.upper(), font=font_title, fill=INK, anchor="mm")
    d.line([img_w / 2 - 260, 132, img_w / 2 + 260, 132], fill=INK, width=2)

    # ── Room fills (color style) ─────────────────────────────────────────────
    if style == "color":
        for room in layout.rooms:
            fill = ROOM_FILLS.get(_norm_type(room), ROOM_FILLS["other"])
            d.rectangle([tx(room.x_cm), ty(room.y_cm),
                         tx(room.x_cm + room.width_cm), ty(room.y_cm + room.height_cm)], fill=fill)

    # ── Furniture (under walls) ──────────────────────────────────────────────
    furn_line = "#6b7076" if style == "color" else INK_SOFT
    _draw_furniture(d, layout, s, tx, ty, furn_line, font_small)

    # ── Walls with opening gaps ──────────────────────────────────────────────
    wall_bands = []  # (x1,y1,x2,y2, thickness_cm)
    for room in layout.rooms:
        for side in ("top", "bottom", "left", "right"):
            t = _wall_thickness(layout, ext_edges, room, side)
            fixed, start, end = _room_wall_extent_pv(room, side)
            if side == "top":
                band = (room.x_cm - WALL_INT_CM / 2, fixed - t, room.x_cm + room.width_cm + WALL_INT_CM / 2, fixed)
            elif side == "bottom":
                band = (room.x_cm - WALL_INT_CM / 2, fixed, room.x_cm + room.width_cm + WALL_INT_CM / 2, fixed + t)
            elif side == "left":
                band = (fixed - t, room.y_cm - WALL_INT_CM / 2, fixed, room.y_cm + room.height_cm + WALL_INT_CM / 2)
            else:
                band = (fixed, room.y_cm - WALL_INT_CM / 2, fixed + t, room.y_cm + room.height_cm + WALL_INT_CM / 2)
            wall_bands.append(band)

    # Draw walls: fill first, then punch opening gaps, then symbols
    for (bx1, by1, bx2, by2) in wall_bands:
        d.rectangle([tx(bx1), ty(by1), tx(bx2), ty(by2)], fill=WALL_FILL)

    def punch_gap(band, side, center_abs, width_cm):
        bx1, by1, bx2, by2 = band
        if side in ("top", "bottom"):
            gx1, gx2 = tx(center_abs - width_cm / 2), tx(center_abs + width_cm / 2)
            d.rectangle([gx1, ty(by1), gx2, ty(by2)], fill=PAPER if style == "bw" else "#FFFFFF")
            return (gx1, ty(by1), gx2, ty(by2))
        gy1, gy2 = ty(center_abs - width_cm / 2), ty(center_abs + width_cm / 2)
        d.rectangle([tx(bx1), gy1, tx(bx2), gy2], fill="#FFFFFF")
        return (tx(bx1), gy1, tx(bx2), gy2)

    # Collect all openings per room; punch + draw symbols
    for room in layout.rooms:
        for side in ("top", "bottom", "left", "right"):
            t = _wall_thickness(layout, ext_edges, room, side)
            fixed, start, end = _room_wall_extent_pv(room, side)
            band = _band_for(room, side, fixed, t)

            for door in (room.doors or []):
                if door.wall_side != side:
                    continue
                center_abs = start + door.center_cm
                gap = punch_gap(band, side, center_abs, door.width_cm)
                _draw_door_symbol(d, gap, side, door.width_cm * s, style)

            for win in (room.windows or []):
                if win.wall_side != side:
                    continue
                center_abs = start + win.center_cm
                gap = punch_gap(band, side, center_abs, win.width_cm)
                _draw_window_symbol(d, gap, side)

    # ── Room labels (auto-fit to room width, wrap if narrow) ─────────────────
    for room in layout.rooms:
        cx = tx(room.x_cm + room.width_cm / 2)
        cy = ty(room.y_cm + room.height_cm / 2)
        area = (room.width_cm * room.height_cm) / 10000
        room_w_px = room.width_cm * s
        name = room.name.upper()

        # Shrink-to-fit: try full name on one line, then two lines, then smaller
        size = max(20, int(26 * s * 2.2))
        parts = [name]
        for _ in range(8):
            f = _font(size, bold=True)
            wide = max(d.textlength(p, font=f) for p in parts)
            if wide <= room_w_px * 0.88:
                break
            if len(parts) == 1 and " " in name:
                words = name.split(" ")
                parts = [" ".join(words[:len(words) // 2 + len(words) % 2]),
                         " ".join(words[len(words) // 2 + len(words) % 2:])]
                continue
            size = int(size * 0.88)
        f = _font(size, bold=True)
        line_h = size + 6
        total_h = line_h * len(parts) + 30
        y_start = cy - total_h / 2
        for i, p in enumerate(parts):
            d.text((cx, y_start + line_h * (i + 0.5)), p, font=f, fill=INK, anchor="mm")
        d.text((cx, y_start + total_h - 4), f"{area:.1f} m²",
               font=_font(max(15, int(size * 0.72))), fill=INK_SOFT, anchor="mm")

    # ── Dimension chains (two levels, like the reference sheets) ─────────────
    x_edges = sorted({min_x, max_x} | {r.x_cm for r in layout.rooms} | {r.x_cm + r.width_cm for r in layout.rooms})
    y_edges = sorted({min_y, max_y} | {r.y_cm for r in layout.rooms} | {r.y_cm + r.height_cm for r in layout.rooms})

    def h_chain(edges):
        segs = []
        for a, b in zip(edges, edges[1:]):
            if (b - a) >= 60:
                segs.append((tx(a), tx(b), f"{(b - a) / 100:.2f}"))
        return segs

    def v_chain(edges):
        segs = []
        for a, b in zip(edges, edges[1:]):
            if (b - a) >= 60:
                segs.append((ty(a), ty(b), f"{(b - a) / 100:.2f}"))
        return segs

    y_bottom = ty(max_y)
    y_top = ty(min_y)
    x_left = tx(min_x)
    x_right = tx(max_x)

    # Outer chains: overall + big segments; inner chains: room edges
    _draw_dimension_chain(d, (x_left, y_bottom), (x_right, y_bottom),
                          (y_bottom + int(150 * s * 2.2), 1),
                          lambda: h_chain([min_x, max_x]), font_dim, INK, side="h")
    _draw_dimension_chain(d, (x_left, y_bottom), (x_right, y_bottom),
                          (y_bottom + int(80 * s * 2.2), 1),
                          lambda: h_chain(x_edges), font_dim, INK, side="h")

    _draw_dimension_chain(d, (x_left, y_top), (x_right, y_top),
                          (y_top - int(150 * s * 2.2), -1),
                          lambda: h_chain([min_x, max_x]), font_dim, INK, side="h")

    _draw_dimension_chain(d, (x_left, y_top), (x_left, y_bottom),
                          (x_left - int(150 * s * 2.2), -1),
                          lambda: v_chain([min_y, max_y]), font_dim, INK, side="v")
    _draw_dimension_chain(d, (x_left, y_top), (x_left, y_bottom),
                          (x_left - int(80 * s * 2.2), -1),
                          lambda: v_chain(y_edges), font_dim, INK, side="v")

    _draw_dimension_chain(d, (x_right, y_top), (x_right, y_bottom),
                          (x_right + int(150 * s * 2.2), 1),
                          lambda: v_chain([min_y, max_y]), font_dim, INK, side="v")

    # ── North arrow, scale bar, title block ──────────────────────────────────
    _draw_north_arrow(d, img_w - 150, 190, 52)
    _draw_scale_bar(d, 70, img_h - 130, s, lang)
    _draw_title_block(d, img_w, img_h, project, title.title(), sheet_no, lang)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


# ── helpers kept out of the main flow ────────────────────────────────────────

def _room_wall_extent_pv(room: RoomLayout, side: str):
    if side == "top":
        return (room.y_cm, room.x_cm, room.x_cm + room.width_cm)
    if side == "bottom":
        return (room.y_cm + room.height_cm, room.x_cm, room.x_cm + room.width_cm)
    if side == "left":
        return (room.x_cm, room.y_cm, room.y_cm + room.height_cm)
    return (room.x_cm + room.width_cm, room.y_cm, room.y_cm + room.height_cm)


def _band_for(room: RoomLayout, side: str, fixed: float, t: float):
    if side == "top":
        return (room.x_cm - WALL_INT_CM / 2, fixed - t, room.x_cm + room.width_cm + WALL_INT_CM / 2, fixed)
    if side == "bottom":
        return (room.x_cm - WALL_INT_CM / 2, fixed, room.x_cm + room.width_cm + WALL_INT_CM / 2, fixed + t)
    if side == "left":
        return (fixed - t, room.y_cm - WALL_INT_CM / 2, fixed, room.y_cm + room.height_cm + WALL_INT_CM / 2)
    return (fixed, room.y_cm - WALL_INT_CM / 2, fixed + t, room.y_cm + room.height_cm + WALL_INT_CM / 2)


def _draw_door_symbol(d, gap, side: str, leaf_len_px: float, style: str):
    gx1, gy1, gx2, gy2 = gap
    line = INK
    if side in ("top", "bottom"):
        leaf = min(leaf_len_px, gx2 - gx1)
        hinge_x = gx1
        cy = gy1 if side == "top" else gy2
        swing_dir = 1 if side == "top" else -1
        d.line([hinge_x, cy, hinge_x, cy + swing_dir * leaf], fill=line, width=2)
        bbox_r = leaf * 2
        if swing_dir == 1:
            box = [hinge_x - bbox_r / 2, cy, hinge_x + bbox_r / 2, cy + bbox_r]
            start, end = 180, 270
        else:
            box = [hinge_x - bbox_r / 2, cy - bbox_r, hinge_x + bbox_r / 2, cy]
            start, end = 90, 180
        d.arc(box, start=start, end=end, fill=line, width=1)
    else:
        leaf = min(leaf_len_px, gy2 - gy1)
        hinge_y = gy1
        cx = gx1 if side == "left" else gx2
        swing_dir = 1 if side == "left" else -1
        d.line([cx, hinge_y, cx + swing_dir * leaf, hinge_y], fill=line, width=2)
        bbox_r = leaf * 2
        if swing_dir == 1:
            box = [cx, hinge_y - bbox_r / 2, cx + bbox_r, hinge_y + bbox_r / 2]
            start, end = 270, 360
        else:
            box = [cx - bbox_r, hinge_y - bbox_r / 2, cx, hinge_y + bbox_r / 2]
            start, end = 0, 90
        d.arc(box, start=start, end=end, fill=line, width=1)


def _draw_window_symbol(d, gap, side: str):
    gx1, gy1, gx2, gy2 = gap
    if side in ("top", "bottom"):
        mid = (gy1 + gy2) // 2
        d.line([gx1, gy1 + 1, gx2, gy1 + 1], fill=INK, width=1)
        d.line([gx1, mid, gx2, mid], fill=INK, width=2)
        d.line([gx1, gy2 - 1, gx2, gy2 - 1], fill=INK, width=1)
    else:
        mid = (gx1 + gx2) // 2
        d.line([gx1 + 1, gy1, gx1 + 1, gy2], fill=INK, width=1)
        d.line([mid, gy1, mid, gy2], fill=INK, width=2)
        d.line([gx2 - 1, gy1, gx2 - 1, gy2], fill=INK, width=1)


# ── Room schedule table ──────────────────────────────────────────────────────

_SCHEDULE_LABELS = {
    "en": {"title": "ROOM SCHEDULE", "code": "CODE", "room": "ROOM", "dims": "DIMENSIONS (m)",
           "area": "AREA (m²)", "floor": "FLOOR", "total": "TOTAL LIVING AREA",
           "ground": "Ground", "upper": "Upper"},
    "fr": {"title": "TABLEAU DES PIÈCES", "code": "CODE", "room": "PIÈCE", "dims": "DIMENSIONS (m)",
           "area": "SURFACE (m²)", "floor": "NIVEAU", "total": "SURFACE HABITABLE TOTALE",
           "ground": "RDC", "upper": "Étage"},
}


def render_room_schedule(layout: FloorPlanLayout, lang: str = "en", project: str = "") -> bytes:
    L = _SCHEDULE_LABELS.get(lang, _SCHEDULE_LABELS["en"])
    img_w, img_h = 2000, 1400
    img = Image.new("RGB", (img_w, img_h), PAPER)
    d = ImageDraw.Draw(img)

    d.rectangle([18, 18, img_w - 18, img_h - 18], outline=INK, width=3)
    d.text((img_w / 2, 110), L["title"], font=_font(64, bold=True), fill=INK, anchor="mm")

    cols = [180, 640, 480, 320]
    x0 = 140
    y0 = 220
    row_h = 74

    headers = [L["code"], L["room"], L["dims"], L["area"]]
    font_h = _font(30, bold=True)
    font_cell = _font(30)
    font_dim_cell = _font(30)

    # Header band
    d.rectangle([x0, y0, x0 + sum(cols), y0 + row_h], fill=WALL_FILL)
    cx = x0
    for w, htxt in zip(cols, headers):
        d.text((cx + w / 2, y0 + row_h / 2), htxt, font=font_h, fill="#FFFFFF", anchor="mm")
        cx += w

    total = 0.0
    rr = y0 + row_h
    for i, room in enumerate(layout.rooms):
        area = (room.width_cm * room.height_cm) / 10000
        total += area
        if i % 2 == 1:
            d.rectangle([x0, rr, x0 + sum(cols), rr + row_h], fill="#F2F2F0")
        dims = f"{room.width_cm / 100:.2f} × {room.height_cm / 100:.2f}"
        cells = [room.room_code or "—", room.name.title(), dims, f"{area:.1f}"]
        cx = x0
        for w, cell in zip(cols, cells):
            anchor_x = cx + 24 if cell != cells[3] else cx + w - 24
            anchor = "lm" if cell != cells[3] else "rm"
            d.text((anchor_x, rr + row_h / 2), cell, font=font_cell, fill=INK, anchor=anchor)
            cx += w
        d.line([x0, rr + row_h, x0 + sum(cols), rr + row_h], fill=INK_FAINT, width=1)
        rr += row_h

    # Total row
    d.rectangle([x0, rr, x0 + sum(cols), rr + row_h], fill="#E4E7EA")
    d.text((x0 + 24, rr + row_h / 2), L["total"], font=font_h, fill=INK, anchor="lm")
    d.text((x0 + sum(cols) - 24, rr + row_h / 2), f"{total:.1f} m²", font=font_h, fill=INK, anchor="rm")
    rr += row_h + 40

    d.text((x0, rr), (project or "7G House"), font=_font(28, bold=True), fill=INK_SOFT, anchor="lm")
    d.text((x0 + sum(cols), rr), date.today().strftime("%d.%m.%Y"), font=font_cell, fill=INK_SOFT, anchor="rm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()
