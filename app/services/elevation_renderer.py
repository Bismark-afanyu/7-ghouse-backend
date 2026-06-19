import io
import math
import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle, Arc, FancyBboxPatch
from matplotlib.path import Path

from app.services.floor_plan_layout import FloorPlanLayout

FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "fonts",
)
FONT_NAME = "NotoSans-Variable.ttf"
FONT_FILE = os.path.join(FONT_PATH, FONT_NAME)

if os.path.exists(FONT_FILE):
    fm.fontManager.addfont(FONT_FILE)
    _FONT_PROPS = FontProperties(fname=FONT_FILE)
else:
    _FONT_PROPS = FontProperties()


def _load_font(size: int = 9) -> FontProperties:
    fp = _FONT_PROPS.copy()
    fp.set_size(size)
    return fp


def _roof_rise(layout: FloorPlanLayout, span_cm: float) -> float:
    pitch_rad = math.radians(layout.roof_pitch_degrees)
    return (span_cm / 2.0) * math.tan(pitch_rad)


def _draw_foundation(ax, total_width_cm: float, depth_cm: float):
    y0 = -depth_cm
    ax.add_patch(Rectangle(
        (0, y0), total_width_cm, depth_cm,
        facecolor="#d5d8dc", edgecolor="black", linewidth=1.5, hatch="///",
    ))
    ax.plot([0, total_width_cm], [0, 0], color="black", linewidth=3)
    ax.text(
        total_width_cm / 2, y0 / 2, "FOUNDATION",
        fontproperties=_load_font(7), ha="center", va="center",
        color="#666666", style="italic",
    )


def _draw_window_elevation(ax, room_x_cm: float, wall_side: str,
                           center_cm: float, width_cm: float, height_cm: float,
                           sill_cm: float):
    x0 = room_x_cm + center_cm - width_cm / 2
    x1 = x0 + width_cm
    y0 = sill_cm
    y1 = sill_cm + height_cm

    ax.add_patch(Rectangle(
        (x0, y0), width_cm, height_cm,
        facecolor="#d4e6f1", edgecolor="#2980b9", linewidth=1.5,
    ))
    mid_x = (x0 + x1) / 2
    mid_y = (y0 + y1) / 2
    ax.plot([x0, x1], [mid_y, mid_y], color="#2980b9", linewidth=0.8)
    ax.plot([mid_x, mid_x], [y0, y1], color="#2980b9", linewidth=0.8)


def _draw_door_elevation(ax, room_x_cm: float, wall_side: str,
                         center_cm: float, width_cm: float, height_cm: float):
    x0 = room_x_cm + center_cm - width_cm / 2
    y0 = 0
    rect = Rectangle(
        (x0, y0), width_cm, height_cm,
        facecolor="#d5d8dc", edgecolor="black", linewidth=1.5,
    )
    ax.add_patch(rect)
    mid_x = (x0 + x0 + width_cm) / 2
    ax.plot([x0, x0 + width_cm], [height_cm * 0.6, height_cm * 0.6],
            color="#999999", linewidth=0.5, linestyle="--")
    ax.plot([mid_x, mid_x], [0, height_cm * 0.6],
            color="#999999", linewidth=0.5, linestyle="--")
    ax.plot(x0 + width_cm * 0.1, height_cm * 0.5, "o", color="#888888", markersize=2)


def _gable_roof_front(ax, layout: FloorPlanLayout, total_width_cm: float):
    wh = layout.wall_height_cm
    rise = _roof_rise(layout, total_width_cm)
    ridge_y = wh + rise
    mid_x = total_width_cm / 2
    overhang = total_width_cm * 0.03

    roof_path = Path([
        (-overhang, wh),
        (mid_x, ridge_y + overhang * 0.5),
        (total_width_cm + overhang, wh),
        (total_width_cm, wh),
        (mid_x, ridge_y),
        (0, wh),
        (-overhang, wh),
    ])
    ax.add_patch(plt.Polygon(
        roof_path.vertices,
        facecolor="#e74c3c", edgecolor="black", linewidth=1.5, alpha=0.85,
    ))
    ax.plot([mid_x, mid_x], [wh, ridge_y], color="black", linewidth=1.5, linestyle="--")
    ax.text(mid_x + total_width_cm * 0.02, ridge_y * 0.5,
            f"{layout.roof_pitch_degrees:.0f}°",
            fontproperties=_load_font(7), color="#333333")


def _gable_roof_side(ax, layout: FloorPlanLayout, total_depth_cm: float):
    wh = layout.wall_height_cm
    rise = _roof_rise(layout, layout.total_width_cm)
    overhang = total_depth_cm * 0.03

    roof_path = plt.Polygon(
        [
            (-overhang, wh),
            (total_depth_cm + overhang, wh),
            (total_depth_cm + overhang, wh + rise),
            (-overhang, wh + rise),
        ],
        facecolor="#e74c3c", edgecolor="black", linewidth=1.5, alpha=0.85,
    )
    ax.add_patch(roof_path)
    ax.plot([0, total_depth_cm], [wh, wh], color="black", linewidth=1.5, linestyle="--")
    ax.text(total_depth_cm * 0.5, wh - rise * 0.15,
            f"{layout.roof_type.upper()} ROOF",
            fontproperties=_load_font(7), ha="center", va="top",
            color="#333333", style="italic")


def _flat_roof(ax, layout: FloorPlanLayout, total_width_cm: float):
    wh = layout.wall_height_cm
    parapet = 15.0
    overhang = total_width_cm * 0.02

    ax.add_patch(Rectangle(
        (-overhang, wh), total_width_cm + 2 * overhang, parapet,
        facecolor="#d5d8dc", edgecolor="black", linewidth=1.5,
    ))
    ax.text(total_width_cm / 2, wh + parapet * 0.5,
            "FLAT ROOF", fontproperties=_load_font(7),
            ha="center", va="center", color="#666666", style="italic")


def _hip_roof_front(ax, layout: FloorPlanLayout, total_width_cm: float):
    wh = layout.wall_height_cm
    rise = _roof_rise(layout, total_width_cm)
    overhang = total_width_cm * 0.03

    inset = total_width_cm * 0.15
    top_width = total_width_cm - 2 * inset

    ax.add_patch(plt.Polygon(
        [
            (-overhang, wh),
            (inset, wh + rise),
            (inset + top_width, wh + rise),
            (total_width_cm + overhang, wh),
            (total_width_cm, wh),
            (inset + top_width, wh + rise * 0.7),
            (inset, wh + rise * 0.7),
            (0, wh),
        ],
        facecolor="#e67e22", edgecolor="black", linewidth=1.5, alpha=0.85,
    ))


def _hip_roof_side(ax, layout: FloorPlanLayout, total_depth_cm: float):
    _gable_roof_side(ax, layout, total_depth_cm)


def _draw_roof(ax, layout: FloorPlanLayout, wall_side: str, total_span_cm: float):
    roof_type = layout.roof_type.lower()

    is_front_or_rear = wall_side in ("bottom", "top")

    if roof_type == "gable":
        if is_front_or_rear:
            _gable_roof_front(ax, layout, total_span_cm)
        else:
            _gable_roof_side(ax, layout, total_span_cm)
    elif roof_type == "hip":
        if is_front_or_rear:
            _hip_roof_front(ax, layout, total_span_cm)
        else:
            _hip_roof_side(ax, layout, total_span_cm)
    elif roof_type == "flat":
        _flat_roof(ax, layout, total_span_cm)
    elif roof_type == "pitched":
        if is_front_or_rear:
            _gable_roof_front(ax, layout, total_span_cm)
        else:
            _gable_roof_side(ax, layout, total_span_cm)
    else:
        _flat_roof(ax, layout, total_span_cm)


def _draw_elevation(ax, layout: FloorPlanLayout, wall_side: str, title: str,
                    hide_title: bool = False):
    is_horizontal = wall_side in ("bottom", "top")
    total_span = layout.total_width_cm if is_horizontal else layout.total_height_cm
    wh = layout.wall_height_cm
    foundation_depth = 50.0
    margin_ratio = 0.04
    margin = total_span * margin_ratio

    visible_rooms = []
    for room in layout.rooms:
        if is_horizontal:
            if room.x_cm <= layout.total_width_cm and room.x_cm + room.width_cm >= 0:
                visible_rooms.append(room)
        else:
            if room.y_cm <= layout.total_height_cm and room.y_cm + room.height_cm >= 0:
                visible_rooms.append(room)

    if is_horizontal:
        visible_rooms.sort(key=lambda r: r.x_cm)
    else:
        visible_rooms.sort(key=lambda r: r.y_cm)

    rise = _roof_rise(layout, total_span)
    max_y = wh + rise + margin
    min_y = -foundation_depth - margin

    ax.set_xlim(-margin, total_span + margin)
    ax.set_ylim(min_y, max_y)
    ax.set_aspect("equal")
    ax.axis("off")

    _draw_foundation(ax, total_span, foundation_depth)

    for room in visible_rooms:
        if is_horizontal:
            seg_start = room.x_cm
            seg_end = room.x_cm + room.width_cm
        else:
            seg_start = room.y_cm
            seg_end = room.y_cm + room.height_cm

        if seg_end <= 0 or seg_start >= total_span:
            continue

        clip_start = max(seg_start, 0)
        clip_end = min(seg_end, total_span)

        ax.add_patch(Rectangle(
            (clip_start, 0), clip_end - clip_start, wh,
            facecolor="#f8f9fa", edgecolor="black", linewidth=1.2,
        ))

        for win in (room.windows or []):
            if win.wall_side == wall_side:
                _draw_window_elevation(
                    ax, seg_start, wall_side,
                    win.center_cm, win.width_cm, win.height_cm, win.sill_height_cm,
                )

        for door in (room.doors or []):
            if door.wall_side == wall_side:
                _draw_door_elevation(
                    ax, seg_start, wall_side,
                    door.center_cm, door.width_cm, door.height_cm,
                )

        label = room.name
        if room.room_type == "kitchen" and "Open" in label:
            label = "Kitchen"
        cx = (clip_start + clip_end) / 2
        ax.text(
            cx, wh / 2, label,
            fontproperties=_load_font(8), ha="center", va="center",
            color="#1a1a1a",
            bbox=dict(boxstyle="round,pad=0.1", facecolor="white", edgecolor="none", alpha=0.85),
        )

    _draw_roof(ax, layout, wall_side, total_span)

    dim_font = _load_font(7)
    ax.text(
        total_span / 2, -foundation_depth - margin * 0.4,
        f"{total_span / 100:.1f}m",
        fontproperties=dim_font, ha="center", va="top", color="#666699",
    )
    ax.text(
        -margin * 0.3, wh / 2,
        f"{wh / 100:.1f}m",
        fontproperties=dim_font, ha="right", va="center", color="#666699",
    )

    title_font = _load_font(9)
    ax.text(total_span / 2, max_y - margin * 0.3, title,
            fontproperties=title_font, ha="center", va="top",
            color="#333333", fontweight="bold")


def render_elevations(layout: FloorPlanLayout) -> bytes:
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))

    views = [
        ("bottom", "FRONT ELEVATION", axes[0, 0]),
        ("top", "REAR ELEVATION", axes[0, 1]),
        ("left", "LEFT ELEVATION", axes[1, 0]),
        ("right", "RIGHT ELEVATION", axes[1, 1]),
    ]

    for wall_side, title, ax in views:
        _draw_elevation(ax, layout, wall_side, title)

    fig.patch.set_facecolor("white")
    plt.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    return buf.getvalue()
