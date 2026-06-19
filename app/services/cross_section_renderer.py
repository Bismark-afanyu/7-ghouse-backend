import io
import math
import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle, Polygon as MplPolygon, Arc
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


def _find_cut_rooms(layout: FloorPlanLayout, cut_y_cm: float) -> list:
    cut_rooms = []
    for room in layout.rooms:
        if room.y_cm <= cut_y_cm <= room.y_cm + room.height_cm:
            cut_rooms.append(room)
    cut_rooms.sort(key=lambda r: r.x_cm)
    return cut_rooms


def _roof_rise(layout: FloorPlanLayout, span_cm: float) -> float:
    pitch_rad = math.radians(layout.roof_pitch_degrees)
    return (span_cm / 2.0) * math.tan(pitch_rad)


def _draw_section(ax, layout: FloorPlanLayout, cut_y_cm: float, title: str):
    wh = layout.wall_height_cm
    fdn_depth = 50.0
    slab_thick = 15.0
    wall_thick_display = 20.0
    margin = layout.total_width_cm * 0.04

    cut_rooms = _find_cut_rooms(layout, cut_y_cm)

    rise = _roof_rise(layout, layout.total_width_cm)
    max_y = wh + rise + margin
    min_y = -fdn_depth - margin

    ax.set_xlim(-margin, layout.total_width_cm + margin)
    ax.set_ylim(min_y, max_y)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.add_patch(Rectangle(
        (0, -fdn_depth), layout.total_width_cm, fdn_depth,
        facecolor="#d5d8dc", edgecolor="black", linewidth=1.5, hatch="..",
    ))
    ax.plot([0, layout.total_width_cm], [0, 0], color="black", linewidth=3)
    ax.plot([0, layout.total_width_cm], [-fdn_depth, -fdn_depth],
            color="black", linewidth=1, linestyle=":")

    ax.add_patch(Rectangle(
        (0, 0), layout.total_width_cm, slab_thick,
        facecolor="#bdc3c7", edgecolor="black", linewidth=1.5,
    ))

    prev_x = 0.0
    for room in cut_rooms:
        rx0 = room.x_cm
        rx1 = room.x_cm + room.width_cm

        if rx0 > prev_x:
            gap = rx0 - prev_x

        left_wall_x = rx0
        right_wall_x = rx1

        ax.add_patch(Rectangle(
            (left_wall_x, slab_thick), wall_thick_display, wh - slab_thick,
            facecolor="#e0e0e0", edgecolor="black", linewidth=1.5, hatch="///",
        ))

        ax.add_patch(Rectangle(
            (right_wall_x - wall_thick_display, slab_thick),
            wall_thick_display, wh - slab_thick,
            facecolor="#e0e0e0", edgecolor="black", linewidth=1.5, hatch="///",
        ))

        room_interior_x0 = left_wall_x + wall_thick_display
        room_interior_x1 = right_wall_x - wall_thick_display

        if room_interior_x1 > room_interior_x0:
            ax.add_patch(Rectangle(
                (room_interior_x0, slab_thick),
                room_interior_x1 - room_interior_x0, wh - slab_thick,
                facecolor="#f8f9fa", edgecolor="black", linewidth=0.5, linestyle="--",
            ))

        cx = (left_wall_x + right_wall_x) / 2
        label = room.name
        if room.room_type == "kitchen" and "Open" in label:
            label = "Kitchen"
        ax.text(
            cx, wh * 0.5, label,
            fontproperties=_load_font(8), ha="center", va="center",
            color="#1a1a1a",
            bbox=dict(boxstyle="round,pad=0.1", facecolor="white", edgecolor="none", alpha=0.85),
        )

        for win in (room.windows or []):
            if win.wall_side in ("top", "bottom"):
                continue
            xw = left_wall_x + win.center_cm / room.width_cm * room.width_cm
            ax.plot([xw, xw], [win.sill_height_cm, win.sill_height_cm + win.height_cm],
                    color="#2980b9", linewidth=1.5, linestyle="-")
            ax.plot([xw - wall_thick_display * 0.3, xw + wall_thick_display * 0.3],
                    [win.sill_height_cm + win.height_cm * 0.5] * 2,
                    color="#2980b9", linewidth=0.8, linestyle="-")

        prev_x = rx1

    if layout.roof_type != "flat":
        pitch_rad = math.radians(layout.roof_pitch_degrees)
        ridge_y = wh + rise

        roof_x = [layout.total_width_cm, layout.total_width_cm / 2, 0]
        roof_y = [wh, ridge_y, wh]
        overhang = layout.total_width_cm * 0.03
        roof_vertices = [
            (-overhang, wh),
            (layout.total_width_cm / 2, ridge_y + overhang * 0.5),
            (layout.total_width_cm + overhang, wh),
            (layout.total_width_cm, wh),
            (layout.total_width_cm / 2, ridge_y),
            (0, wh),
            (-overhang, wh),
        ]
        ax.add_patch(MplPolygon(
            roof_vertices,
            facecolor="#e74c3c" if layout.roof_type == "gable" else "#e67e22",
            edgecolor="black", linewidth=2, alpha=0.85,
        ))

        ridge_x = layout.total_width_cm / 2
        ax.plot([ridge_x, ridge_x], [wh, ridge_y],
                color="black", linewidth=1.5, linestyle="--")

        ax.plot([0, layout.total_width_cm], [wh, wh],
                color="black", linewidth=1.5, linestyle="--")

        ax.text(layout.total_width_cm * 0.75, wh + rise * 0.3,
                f"{layout.roof_pitch_degrees}\u00b0 PITCH",
                fontproperties=_load_font(8), color="#333333", style="italic")

        ax.text(layout.total_width_cm * 0.25, wh + rise * 0.3,
                f"RISE {rise / 100:.1f}m",
                fontproperties=_load_font(7), color="#666666", style="italic")
    else:
        parapet = 15.0
        overhang = layout.total_width_cm * 0.02
        ax.add_patch(Rectangle(
            (-overhang, wh), layout.total_width_cm + 2 * overhang, parapet,
            facecolor="#bdc3c7", edgecolor="black", linewidth=1.5,
        ))
        ax.text(layout.total_width_cm / 2, wh + parapet * 0.5,
                "FLAT ROOF", fontproperties=_load_font(8),
                ha="center", va="center", color="#666666", style="italic")

    dim_font = _load_font(7)
    ax.text(
        layout.total_width_cm / 2, -fdn_depth - margin * 0.5,
        f"SPAN {layout.total_width_cm / 100:.1f}m",
        fontproperties=dim_font, ha="center", va="top", color="#444488",
    )
    ax.plot(
        [0, layout.total_width_cm],
        [-fdn_depth - margin * 0.2, -fdn_depth - margin * 0.2],
        color="#444488", linewidth=0.8,
    )
    ax.plot([0, 0], [-fdn_depth, -fdn_depth - margin * 0.2], color="#444488", linewidth=0.8)
    ax.plot(
        [layout.total_width_cm, layout.total_width_cm],
        [-fdn_depth, -fdn_depth - margin * 0.2], color="#444488", linewidth=0.8,
    )

    ax.plot(
        [-margin * 0.3, -margin * 0.3], [0, wh],
        color="#444488", linewidth=0.8,
    )
    ax.text(
        -margin * 0.35, wh * 0.5,
        f"CEILING HT {wh / 100:.1f}m",
        fontproperties=_load_font(7), ha="right", va="center", color="#444488",
    )

    cut_font = _load_font(7)
    ax.text(
        layout.total_width_cm + margin * 0.3, wh * 0.5,
        "SECTION CUT\n(diagrammatic)",
        fontproperties=cut_font, ha="left", va="center",
        color="#999999", style="italic",
    )

    title_font = _load_font(10)
    ax.text(
        layout.total_width_cm / 2, max_y - margin * 0.2,
        title,
        fontproperties=title_font, ha="center", va="top",
        color="#333333", fontweight="bold",
    )


def render_cross_section(layout: FloorPlanLayout) -> bytes:
    cut_y_cm = layout.total_height_cm / 2.0

    fig, ax = plt.subplots(1, 1, figsize=(16, 9))

    _draw_section(ax, layout, cut_y_cm,
                  f"CROSS-SECTION A-A  (cut at {cut_y_cm / 100:.1f}m depth)")

    fig.patch.set_facecolor("white")
    plt.tight_layout(pad=1.0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    return buf.getvalue()
