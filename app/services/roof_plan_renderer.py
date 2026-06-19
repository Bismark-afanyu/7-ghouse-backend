import io
import math
import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle, Polygon as MplPolygon, Arc
from matplotlib.lines import Line2D

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


def _draw_gable_roof(ax, w: float, d: float, overhang: float, pitch_deg: float):
    ow = w + 2 * overhang
    od = d + 2 * overhang
    ridge_x = w / 2

    ax.add_patch(Rectangle(
        (0 - overhang, 0 - overhang), ow, od,
        facecolor="#fdebd0", edgecolor="#c0392b", linewidth=2,
        linestyle="-",
    ))

    ridge_segments = [
        ([ridge_x, ridge_x], [0 - overhang, d + overhang], "#c0392b"),
        ([ridge_x, ridge_x], [0, d], "#922b21"),
    ]
    for xs, ys, c in ridge_segments:
        ax.plot(xs, ys, color=c, linewidth=2.5, linestyle="--")
        ax.plot(xs, ys, color=c, linewidth=1.5, linestyle="-")

    ax.annotate(
        f"RIDGE\n{pitch_deg}\u00b0 PITCH",
        xy=(ridge_x, d / 2), ha="left", va="center",
        fontproperties=_load_font(7),
        color="#c0392b", style="italic",
        xytext=(ridge_x + overhang * 0.5, d / 2),
        arrowprops=dict(arrowstyle="->", color="#c0392b", lw=0.8),
    )

    overhang_label_x = w + overhang / 2
    ax.plot([w, w + overhang], [d + overhang * 0.3, d + overhang * 0.3],
            color="#666666", linewidth=0.8)
    ax.text(overhang_label_x, d + overhang * 0.35,
            f"OH {overhang / 100:.1f}m",
            fontproperties=_load_font(6), ha="center", va="bottom", color="#666666")


def _draw_hip_roof(ax, w: float, d: float, overhang: float, pitch_deg: float):
    ow = w + 2 * overhang
    od = d + 2 * overhang
    ridge_length = w * 0.5
    ridge_start = (w - ridge_length) / 2
    ridge_end = ridge_start + ridge_length
    hip_offset = overhang * 0.6

    ax.add_patch(Rectangle(
        (0 - overhang, 0 - overhang), ow, od,
        facecolor="#fef5e7", edgecolor="#d35400", linewidth=2,
        linestyle="-",
    ))

    ax.plot([ridge_start, ridge_end], [d / 2, d / 2],
            color="#d35400", linewidth=3, linestyle="-")
    ax.plot([ridge_start, ridge_end], [d / 2, d / 2],
            color="#d35400", linewidth=1.5, linestyle="--")

    hip_endpoints = [
        (0 - overhang, 0 - overhang),
        (w + overhang, 0 - overhang),
        (w + overhang, d + overhang),
        (0 - overhang, d + overhang),
    ]
    ridge_pts = [(ridge_start, d / 2), (ridge_end, d / 2)]

    for he in hip_endpoints:
        closer = min(ridge_pts,
                     key=lambda rp: math.hypot(rp[0] - he[0], rp[1] - he[1]))
        ax.plot([closer[0], he[0]], [closer[1], he[1]],
                color="#d35400", linewidth=1.5, linestyle="-.")

    for he in hip_endpoints:
        cx = (he[0] + ridge_start + ridge_end) / 3
        cy = (he[1] + d / 2) / 2
        ax.text(cx, cy, f"HIP\n{pitch_deg}\u00b0",
                fontproperties=_load_font(6), ha="center", va="center",
                color="#d35400", style="italic", alpha=0.7)


def _draw_flat_roof(ax, w: float, d: float, overhang: float, pitch_deg: float):
    parapet = 20.0
    ow = w + 2 * (overhang + parapet)
    od = d + 2 * (overhang + parapet)

    ax.add_patch(Rectangle(
        (0 - overhang - parapet, 0 - overhang - parapet), ow, od,
        facecolor="#f0f3f4", edgecolor="#2c3e50", linewidth=2,
        linestyle="-",
    ))

    ax.add_patch(Rectangle(
        (0 - overhang, 0 - overhang), w + 2 * overhang, d + 2 * overhang,
        facecolor="#d5dbdb", edgecolor="#7f8c8d", linewidth=1,
        linestyle="--",
    ))

    roof_center = (w / 2, d / 2)
    ax.plot(*roof_center, marker="o", color="#2c3e50", markersize=4)
    ax.text(roof_center[0] + 20, roof_center[1] + 20,
            f"FLAT ROOF\nSLOPE 1:80",
            fontproperties=_load_font(7), ha="left", va="bottom",
            color="#7f8c8d", style="italic")


def _draw_roof_plan(ax, layout: FloorPlanLayout, title: str):
    w = layout.total_width_cm
    d = layout.total_height_cm
    overhang = w * 0.04
    pitch = layout.roof_pitch_degrees
    margin = w * 0.06

    ax.set_xlim(-margin - overhang, w + margin + overhang)
    ax.set_ylim(-margin - overhang, d + margin + overhang)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.add_patch(Rectangle(
        (0, 0), w, d,
        facecolor="#f8f9fa", edgecolor="#2c3e50", linewidth=1.5,
        linestyle="--", alpha=0.7,
    ))

    roof_type_lower = layout.roof_type.lower()
    if roof_type_lower == "gable":
        _draw_gable_roof(ax, w, d, overhang, pitch)
    elif roof_type_lower == "hip":
        _draw_hip_roof(ax, w, d, overhang, pitch)
    else:
        _draw_flat_roof(ax, w, d, overhang, pitch)

    dim_font = _load_font(7)
    ax.text(w / 2, -overhang - margin * 0.3,
            f"WIDTH {w / 100:.1f}m",
            fontproperties=dim_font, ha="center", va="top", color="#444488")
    ax.plot([0, w], [-overhang - margin * 0.15, -overhang - margin * 0.15],
            color="#444488", linewidth=0.8)
    ax.plot([0, 0], [-overhang, -overhang - margin * 0.15],
            color="#444488", linewidth=0.8)
    ax.plot([w, w], [-overhang, -overhang - margin * 0.15],
            color="#444488", linewidth=0.8)

    ax.text(w + overhang + margin * 0.2, d / 2,
            f"DEPTH {d / 100:.1f}m",
            fontproperties=dim_font, ha="left", va="center", color="#444488",
            rotation=90)
    ax.plot([w + overhang, w + overhang], [0, d],
            color="#444488", linewidth=0.8)
    ax.plot([w + overhang, w + overhang + margin * 0.15], [0, 0],
            color="#444488", linewidth=0.8)
    ax.plot([w + overhang, w + overhang + margin * 0.15], [d, d],
            color="#444488", linewidth=0.8)

    north_x = -margin * 0.2
    north_y = d + margin * 0.3
    ax.annotate(
        "", xy=(north_x, north_y + overhang),
        xytext=(north_x, north_y),
        arrowprops=dict(arrowstyle="->", color="#2c3e50", lw=2),
    )
    ax.text(north_x - 15, north_y + overhang / 2, "N",
            fontproperties=_load_font(9), ha="center", va="center",
            color="#2c3e50", fontweight="bold")

    title_font = _load_font(10)
    ax.text(
        w / 2, d + margin + overhang * 0.5,
        title,
        fontproperties=title_font, ha="center", va="bottom",
        color="#333333", fontweight="bold",
    )

    legend_x = w + overhang + margin * 0.5
    legend_y = d - margin
    legend_items = [
        ("- - -", "Ridge Line", "#c0392b"),
        ("-.-.-", "Hip Line", "#d35400"),
        ("-----", "Roof Outline", "#2c3e50"),
    ]
    for i, (pat, desc, col) in enumerate(legend_items):
        ly = legend_y - i * 20
        ax.plot([legend_x, legend_x + 30], [ly, ly],
                color=col, linewidth=1.5, linestyle="-")
        ax.text(legend_x + 35, ly, desc,
                fontproperties=_load_font(6), va="center", color="#444444")


def render_roof_plan(layout: FloorPlanLayout) -> bytes:
    fig, ax = plt.subplots(1, 1, figsize=(16, 9))

    _draw_roof_plan(ax, layout,
                    f"{layout.roof_type.capitalize()} Roof Plan  —  {layout.total_area_m2:.0f}m\u00b2 Footprint")

    fig.patch.set_facecolor("white")
    plt.tight_layout(pad=1.0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    return buf.getvalue()
