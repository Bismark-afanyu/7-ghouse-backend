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

    img.paste(overlay, (0, 0), overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
