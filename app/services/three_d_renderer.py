import io
import math
import os

import matplotlib
matplotlib.use("Agg")

from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties

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


_ROOF_COLORS = {
    "gable": "#c0392b",
    "hip": "#d35400",
    "pitched": "#884ea0",
    "flat": "#95a5a6",
}

_WALL_COLOR = "#d5d8dc"
_WALL_EDGE = "#2c3e50"
_FLOOR_COLOR = "#bdc3c7"
_FOUNDATION_COLOR = "#7f8c8d"
_ROOM_FLOOR_COLORS = {
    "living": "#f9e79f",
    "dining": "#f9e79f",
    "living/dining": "#f7dc6f",
    "kitchen": "#f1948a",
    "bedroom": "#aed6f1",
    "master": "#a9dfbf",
    "bathroom": "#85c1e9",
    "toilet": "#85c1e9",
    "laundry": "#d2b4de",
    "pantry": "#f0b27a",
    "storeroom": "#f0b27a",
    "corridor": "#abb2b9",
    "hall": "#abb2b9",
    "garage": "#fad7a0",
}


def _room_floor_color(name: str) -> str:
    name_lower = name.lower()
    for key, color in _ROOM_FLOOR_COLORS.items():
        if key in name_lower:
            return color
    return "#f5f5f5"


def _draw_room_3d(
    ax,
    x: float, y: float, w: float, d: float,
    height: float,
    room_name: str,
):
    x = float(x)
    y = float(y)
    w = float(w)
    d = float(d)

    floor_color = _room_floor_color(room_name)
    verts = [
        [[x, y, 0], [x + w, y, 0], [x + w, y + d, 0], [x, y + d, 0]],
    ]
    ax.add_collection3d(Poly3DCollection(
        verts, facecolors=floor_color, edgecolors="none", alpha=0.6,
    ))

    wall_z = [
        [0, 0],
        [height, height],
    ]
    wall_x = [[x, x], [x, x]]
    wall_y = [[y, y + d], [y, y + d]]
    ax.plot_wireframe(
        np.array([[x, x], [x, x]]),
        np.array([[y, y + d], [y, y + d]]),
        np.array([[0, 0], [height, height]]),
        color=_WALL_EDGE, linewidth=0.6, alpha=0.5,
    )


def _render_3d_view(layout: FloorPlanLayout, isometric: bool = True):
    wh = layout.wall_height_cm
    fdn_depth = 30.0
    roof_rise = _roof_rise(layout, layout.total_width_cm)

    fig = plt.figure(figsize=(16, 9), facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")

    scene_height = wh + roof_rise + 50
    scene_width = layout.total_width_cm * 1.1
    scene_depth = layout.total_height_cm * 1.1

    ax.set_xlim(-layout.total_width_cm * 0.05, scene_width)
    ax.set_ylim(-layout.total_height_cm * 0.05, scene_depth)
    ax.set_zlim(-fdn_depth, scene_height)

    ax.grid(False)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor("none")
    ax.yaxis.pane.set_edgecolor("none")
    ax.zaxis.pane.set_edgecolor("none")
    ax.set_axis_off()

    x_cen = layout.total_width_cm / 2
    y_cen = layout.total_height_cm / 2
    ax.view_init(elev=25, azim=-35)

    walls_data = []
    for room in layout.rooms:
        rx0 = float(room.x_cm)
        ry0 = float(room.y_cm)
        rx1 = rx0 + float(room.width_cm)
        ry1 = ry0 + float(room.height_cm)

        walls_data.append((rx0, ry0, rx1, ry0))
        walls_data.append((rx1, ry0, rx1, ry1))
        walls_data.append((rx1, ry1, rx0, ry1))
        walls_data.append((rx0, ry1, rx0, ry0))

    seen = set()
    unique_walls = []
    for w in walls_data:
        a = (round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1))
        b = (a[2], a[3], a[0], a[1])
        if a not in seen and b not in seen:
            seen.add(a)
            unique_walls.append(w)

    for wx0, wy0, wx1, wy1 in unique_walls:
        dx = wx1 - wx0
        dy = wy1 - wy0
        length = math.hypot(dx, dy)
        if length < 5:
            continue
        nx = -dy / length * 3.0
        ny = dx / length * 3.0

        wall_corners = np.array([
            [wx0 + nx, wy0 + ny, 0],
            [wx1 + nx, wy1 + ny, 0],
            [wx1 + nx, wy1 + ny, wh],
            [wx0 + nx, wy0 + ny, wh],
            [wx0 - nx, wy0 - ny, wh],
            [wx1 - nx, wy1 - ny, wh],
            [wx1 - nx, wy1 - ny, 0],
            [wx0 - nx, wy0 - ny, 0],
        ])

        outer = [
            [wx0 - nx, wy0 - ny, 0],
            [wx1 - nx, wy1 - ny, 0],
            [wx1 - nx, wy1 - ny, wh],
            [wx0 - nx, wy0 - ny, wh],
        ]
        inner = [
            [wx0 + nx, wy0 + ny, 0],
            [wx1 + nx, wy1 + ny, 0],
            [wx1 + nx, wy1 + ny, wh],
            [wx0 + nx, wy0 + ny, wh],
        ]
        top = [
            [wx0 - nx, wy0 - ny, wh],
            [wx1 - nx, wy1 - ny, wh],
            [wx1 + nx, wy1 + ny, wh],
            [wx0 + nx, wy0 + ny, wh],
        ]
        end1 = [
            [wx0 - nx, wy0 - ny, 0],
            [wx0 + nx, wy0 + ny, 0],
            [wx0 + nx, wy0 + ny, wh],
            [wx0 - nx, wy0 - ny, wh],
        ]
        end2 = [
            [wx1 - nx, wy1 - ny, 0],
            [wx1 + nx, wy1 + ny, 0],
            [wx1 + nx, wy1 + ny, wh],
            [wx1 - nx, wy1 - ny, wh],
        ]

        for face in (outer, inner, top, end1, end2):
            ax.add_collection3d(Poly3DCollection(
                [face], facecolors=_WALL_COLOR, edgecolors=_WALL_EDGE,
                linewidths=0.4, alpha=0.85,
            ))

    fdn_verts = [
        [0, 0, -fdn_depth],
        [layout.total_width_cm, 0, -fdn_depth],
        [layout.total_width_cm, layout.total_height_cm, -fdn_depth],
        [0, layout.total_height_cm, -fdn_depth],
        [0, 0, 0],
        [layout.total_width_cm, 0, 0],
        [layout.total_width_cm, layout.total_height_cm, 0],
        [0, layout.total_height_cm, 0],
    ]
    fdn_faces = [
        [fdn_verts[0], fdn_verts[1], fdn_verts[2], fdn_verts[3]],
        [fdn_verts[4], fdn_verts[5], fdn_verts[6], fdn_verts[7]],
        [fdn_verts[0], fdn_verts[1], fdn_verts[5], fdn_verts[4]],
        [fdn_verts[1], fdn_verts[2], fdn_verts[6], fdn_verts[5]],
        [fdn_verts[2], fdn_verts[3], fdn_verts[7], fdn_verts[6]],
        [fdn_verts[3], fdn_verts[0], fdn_verts[4], fdn_verts[7]],
    ]
    ax.add_collection3d(Poly3DCollection(
        fdn_faces, facecolors=_FOUNDATION_COLOR, edgecolors="#34495e",
        linewidths=0.6, alpha=0.7,
    ))

    if not layout.roof_type.startswith("flat"):
        rise = _roof_rise(layout, layout.total_width_cm)
        ridge_x = layout.total_width_cm / 2

        roof_front = [
            [0, 0, wh],
            [ridge_x, 0, wh + rise],
            [layout.total_width_cm, 0, wh],
        ]
        roof_back = [
            [0, layout.total_height_cm, wh],
            [ridge_x, layout.total_height_cm, wh + rise],
            [layout.total_width_cm, layout.total_height_cm, wh],
        ]
        roof_left = [
            [0, 0, wh],
            [ridge_x, 0, wh + rise],
            [ridge_x, layout.total_height_cm, wh + rise],
            [0, layout.total_height_cm, wh],
        ]
        roof_right = [
            [layout.total_width_cm, 0, wh],
            [ridge_x, 0, wh + rise],
            [ridge_x, layout.total_height_cm, wh + rise],
            [layout.total_width_cm, layout.total_height_cm, wh],
        ]

        roof_color = _ROOF_COLORS.get(layout.roof_type, "#c0392b")

        for face in (roof_left, roof_right):
            ax.add_collection3d(Poly3DCollection(
                [face], facecolors=roof_color, edgecolors=_WALL_EDGE,
                linewidths=0.8, alpha=0.7,
            ))
        for face in (roof_front, roof_back):
            ax.add_collection3d(Poly3DCollection(
                [face], facecolors=roof_color, edgecolors=_WALL_EDGE,
                linewidths=0.6, alpha=0.3,
            ))
    else:
        roof_verts = [
            [0, 0, wh],
            [layout.total_width_cm, 0, wh],
            [layout.total_width_cm, layout.total_height_cm, wh],
            [0, layout.total_height_cm, wh],
        ]
        ax.add_collection3d(Poly3DCollection(
            [roof_verts], facecolors=_ROOF_COLORS["flat"], edgecolors=_WALL_EDGE,
            linewidths=0.6, alpha=0.5,
        ))

    fig.patch.set_facecolor("white")
    ax.set_box_aspect([1, layout.total_height_cm / layout.total_width_cm, scene_height / layout.total_width_cm])

    return fig, ax


def _roof_rise(layout: FloorPlanLayout, span_cm: float) -> float:
    pitch_rad = math.radians(layout.roof_pitch_degrees)
    return (span_cm / 2.0) * math.tan(pitch_rad)


def render_3d_wireframe(layout: FloorPlanLayout) -> bytes:
    fig, ax = _render_3d_view(layout)

    fig.patch.set_facecolor("white")
    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return buf.getvalue()
