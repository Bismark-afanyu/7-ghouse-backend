import io
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.schemas.labels import get_label_config, get_default_legend_labels, LabelItem

FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "fonts",
)
FONT_NAME = "NotoSans-Variable.ttf"
FONT_BOLD_NAME = "NotoSans-Variable.ttf"

_TITLE_BANNER_HEIGHT_RATIO = 0.06
_LEGEND_WIDTH_RATIO = 0.28
_LEGEND_MAX_HEIGHT_RATIO = 0.40
_PADDING_RATIO = 0.010


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_PATH, FONT_NAME)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _load_font_bold(size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_PATH, FONT_BOLD_NAME)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return _load_font(size)


def _get_text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    x1: int, y1: int, x2: int, y2: int,
    radius: int, fill: tuple[int, int, int, int],
):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


def _overlay_label(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    label: LabelItem,
    w: int, h: int,
    language: str,
):
    label_font_size = max(13, int(h * label.font_size_ratio))
    font = _load_font(label_font_size)

    if language == "en":
        display_text = label.en
    elif language == "fr":
        display_text = label.fr
    else:
        display_text = f"{label.en} / {label.fr}"

    text_w, text_h = _get_text_size(draw, display_text, font)
    pad = int(w * _PADDING_RATIO)

    if label.anchor == "lt":
        bx1 = int(w * label.x_ratio)
        by1 = int(h * label.y_ratio)
    elif label.anchor == "rt":
        bx1 = int(w * label.x_ratio) - text_w - pad * 2
        by1 = int(h * label.y_ratio)
    elif label.anchor == "ct":
        bx1 = int(w * label.x_ratio) - (text_w + pad * 2) // 2
        by1 = int(h * label.y_ratio)
    elif label.anchor == "cb":
        bx1 = int(w * label.x_ratio) - (text_w + pad * 2) // 2
        by1 = int(h * label.y_ratio) - text_h - pad * 2
    else:
        bx1 = int(w * label.x_ratio)
        by1 = int(h * label.y_ratio)

    bx2 = bx1 + text_w + pad * 2
    by2 = by1 + text_h + pad * 2

    _draw_rounded_rect(draw, bx1, by1, bx2, by2, radius=6, fill=(0, 0, 0, 120))
    draw.text((bx1 + pad, by1 + pad), display_text, font=font, fill=(255, 255, 255, 230))


def _draw_title_banner(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    config,
    w: int, h: int,
    language: str,
):
    banner_height = int(h * _TITLE_BANNER_HEIGHT_RATIO)
    banner = Image.new("RGBA", (w, banner_height), (0, 0, 0, 0))
    banner_draw = ImageDraw.Draw(banner)
    banner_draw.rounded_rectangle(
        [0, 0, w - 1, banner_height - 1],
        radius=0, fill=(0, 0, 0, 100),
    )

    title = config.title_en if language == "en" else config.title_fr
    if language == "bilingual":
        title = f"{config.title_en} / {config.title_fr}"

    font_size = max(14, int(h * 0.028))
    font = _load_font(font_size)
    tw, th = _get_text_size(banner_draw, title, font)
    tx = (w - tw) // 2
    ty = (banner_height - th) // 2
    banner_draw.text((tx, ty), title, font=font, fill=(255, 255, 255, 200))

    img.paste(banner, (0, 0), banner)


def _draw_legend(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    legend_entries: list[tuple[str, str]],
    w: int, h: int,
    language: str,
):
    font_size = max(11, int(h * 0.018))
    font = _load_font(font_size)
    pad = int(w * _PADDING_RATIO)

    line_height = font_size + int(pad * 1.5)
    title_height = font_size + pad * 3
    entry_count = len(legend_entries)
    legend_height = title_height + entry_count * line_height + pad * 2
    legend_width = int(w * _LEGEND_WIDTH_RATIO)
    max_legend_height = int(h * _LEGEND_MAX_HEIGHT_RATIO)

    if legend_height > max_legend_height:
        font_size = max(9, int(h * 0.015))
        font = _load_font(font_size)
        line_height = font_size + int(pad * 1.5)
        title_height = font_size + pad * 3
        legend_height = title_height + entry_count * line_height + pad * 2

    lx = w - legend_width - pad
    ly = h - legend_height - pad

    _draw_rounded_rect(draw, lx, ly, lx + legend_width, ly + legend_height, radius=8, fill=(0, 0, 0, 130))

    header = "Rooms" if language == "en" else "Pièces"
    if language == "bilingual":
        header = "Rooms / Pièces"
    hw, _ = _get_text_size(draw, header, font)
    draw.text((lx + (legend_width - hw) // 2, ly + pad), header, font=font, fill=(255, 255, 255, 200))

    color_palette = [
        (255, 200, 100, 220),
        (100, 200, 255, 220),
        (150, 255, 150, 220),
        (255, 150, 150, 220),
        (200, 150, 255, 220),
        (255, 255, 150, 220),
        (255, 180, 100, 220),
        (180, 255, 200, 220),
    ]

    for i, (en_name, fr_name) in enumerate(legend_entries):
        y = ly + title_height + i * line_height
        color = color_palette[i % len(color_palette)]
        dot_size = max(6, font_size - 2)
        dot_x = lx + pad * 2
        dot_y = y + (line_height - dot_size) // 2
        draw.rounded_rectangle(
            [dot_x, dot_y, dot_x + dot_size, dot_y + dot_size],
            radius=2, fill=color,
        )

        label = en_name if language == "en" else fr_name
        label_x = dot_x + dot_size + pad
        label_y = y
        if language == "bilingual":
            font_small = _load_font(max(9, font_size - 2))
            draw.text((label_x, label_y), en_name, font=font_small, fill=(255, 255, 255, 220))
            draw.text((label_x, label_y + font_size - 1), fr_name, font=font_small, fill=(200, 200, 200, 200))
        else:
            draw.text((label_x, label_y + (line_height - font_size) // 2), label, font=font, fill=(255, 255, 255, 220))


def overlay_labels(
    image_bytes: bytes,
    view_type: str,
    language: str = "en",
    num_bedrooms: int = 3,
    num_bathrooms: int = 2,
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = img.size

    config = get_label_config(view_type)

    if config.show_title_banner and config.title_en:
        _draw_title_banner(img, draw, config, w, h, language)

    for label in config.labels:
        _overlay_label(img, draw, label, w, h, language)

    if config.show_legend:
        legend_entries = get_default_legend_labels(
            num_bedrooms=num_bedrooms,
            num_bathrooms=num_bathrooms,
            kitchen_type=kitchen_type,
            key_rooms=key_rooms,
            outdoor_spaces=outdoor_spaces,
        )
        if legend_entries:
            _draw_legend(img, draw, legend_entries, w, h, language)

    if config.legend_labels:
        _draw_legend(img, draw, config.legend_labels, w, h, language)

    _draw_watermark(img, w, h)

    img.paste(overlay, (0, 0), overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_watermark(img: Image.Image, w: int, h: int):
    """Draw a semi-transparent '7G House' text + logo watermark at bottom-right."""
    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "app", "assets", "logo.jpeg"
    )
    try:
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo_w = int(w * 0.06)
            logo_h = int(logo.height * (logo_w / logo.width))
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            logo_r, logo_g, logo_b, logo_a = logo.split()
            logo_a = logo_a.point(lambda a: int(a * 0.35))
            logo = Image.merge("RGBA", (logo_r, logo_g, logo_b, logo_a))
        else:
            logo = None
    except Exception:
        logo = None

    watermark = Image.new("RGBA", img.size, (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(watermark)

    font_size = max(12, int(h * 0.018))
    font = _load_font(font_size)
    text = "7G House"
    tw, th = _get_text_size(wm_draw, text, font)
    pad = int(w * 0.01)

    total_w = (logo_w if logo else 0) + (pad if logo else 0) + tw + pad * 2
    total_h = max((logo_h if logo else 0), th) + pad * 2
    bx = w - total_w - pad
    by = h - total_h - pad

    _draw_rounded_rect(wm_draw, bx, by, bx + total_w, by + total_h, radius=6, fill=(0, 0, 0, 100))

    cx = bx + pad
    if logo:
        logo_y = by + (total_h - logo_h) // 2
        watermark.paste(logo, (cx, logo_y), logo)
        cx += logo_w + pad

    text_y = by + (total_h - th) // 2
    wm_draw.text((cx, text_y), text, font=font, fill=(255, 255, 255, 180))

    img.paste(watermark, (0, 0), watermark)


def overlay_room_labels(
    image_bytes: bytes,
    rooms: list,
    total_width_cm: float,
    total_height_cm: float,
    language: str = "en",
) -> bytes:
    """
    Overlay clean room labels on a top-down 3D view image.
    Uses layout data to position labels at the center of each room.
    """
    ROOM_NAMES_FR = {
        "living": "Salon",
        "living/dining": "Salon/Salle à manger",
        "dining": "Salle à manger",
        "kitchen": "Cuisine",
        "master_bedroom": "Chambre principale",
        "bedroom": "Chambre",
        "bathroom": "Salle de bain",
        "hallway": "Couloir",
        "hall": "Hall",
        "corridor": "Couloir",
        "utility": "Buanderie",
        "laundry": "Buanderie",
        "storage": "Rangement",
        "pantry": "Garde-manger",
        "garage": "Garage",
        "office": "Bureau",
        "study": "Bureau d'étude",
        "other": "Autre",
    }

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = img.size

    margin_ratio = 0.08
    usable_w = w * (1 - 2 * margin_ratio)
    usable_h = h * (1 - 2 * margin_ratio)
    margin_x = w * margin_ratio
    margin_y = h * margin_ratio

    scale_x = usable_w / total_width_cm
    scale_y = usable_h / total_height_cm
    scale = min(scale_x, scale_y)

    def to_px(x_cm, y_cm):
        px = margin_x + x_cm * scale
        py = margin_y + y_cm * scale
        return int(px), int(py)

    font_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "fonts", "NotoSans-Variable.ttf"
    )

    try:
        if os.path.exists(font_path):
            font_code = ImageFont.truetype(font_path, max(12, int(w * 0.013)))
            font_name = ImageFont.truetype(font_path, max(10, int(w * 0.010)))
        else:
            raise FileNotFoundError
    except (OSError, FileNotFoundError):
        font_code = ImageFont.load_default()
        font_name = font_code

    for room in rooms:
        cx, cy = to_px(
            room.x_cm + room.width_cm / 2,
            room.y_cm + room.height_cm / 2,
        )
        code = getattr(room, "room_code", "") or ""

        rt = (room.room_type or "").lower()
        if language == "fr":
            name = ROOM_NAMES_FR.get(rt, room.name)
        else:
            name = room.name

        bg_pad = int(w * 0.003)
        text_w_code = draw.textlength(code, font=font_code) if code else 0
        text_w_name = draw.textlength(name, font=font_name)
        text_block_w = int(max(text_w_code, text_w_name) + bg_pad * 3)
        text_block_h = (font_code.size + 2 + font_name.size + bg_pad * 2) if code else (font_name.size + bg_pad * 2)

        bg_x = cx - text_block_w // 2
        bg_y = cy - text_block_h // 2

        draw.rounded_rectangle(
            [bg_x, bg_y, bg_x + text_block_w, bg_y + text_block_h],
            radius=3, fill=(0, 0, 0, 140),
        )

        text_y = bg_y + bg_pad
        if code:
            draw.text(
                (cx, text_y), code, font=font_code,
                fill=(255, 255, 255, 230), anchor="mt",
            )
            text_y += font_code.size + 2
            draw.text(
                (cx, text_y), name, font=font_name,
                fill=(200, 200, 200, 220), anchor="mt",
            )
        else:
            draw.text(
                (cx, text_y), name, font=font_name,
                fill=(255, 255, 255, 230), anchor="mt",
            )

    _draw_watermark(img, w, h)

    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
