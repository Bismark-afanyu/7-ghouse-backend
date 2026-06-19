"""
pdf_service.py — Server-side PDF generation for 7G House.

Builds a branded A4 PDF (landscape-safe) using Pillow + ImageDraw:
  • Page 1: Cover page with project specs
  • Pages 2…N: One project image per page, full-bleed, with label caption

No browser CORS issues — images are fetched directly by the backend.
"""

import io
import os
import logging
import textwrap
import asyncio
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── A4 at 150 dpi ─────────────────────────────────────────────────────────────
A4_W = 1240
A4_H = 1754

# ── Colour palette ─────────────────────────────────────────────────────────────
CLR_PRIMARY = (26, 82, 118)       # #1a5276
CLR_ACCENT  = (46, 134, 193)      # #2e86c1
CLR_BG      = (248, 249, 250)     # #f8f9fa
CLR_WHITE   = (255, 255, 255)
CLR_DARK    = (26, 26, 46)        # #1a1a2e
CLR_MUTED   = (102, 102, 102)     # #666666
CLR_BORDER  = (208, 208, 208)     # #d0d0d0

# ── Font paths ─────────────────────────────────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_FONT_REGULAR = os.path.join(_BACKEND_DIR, "fonts", "NotoSans-Variable.ttf")
_FONT_BOLD    = _FONT_REGULAR   # variable font covers bold weights


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        if bold:
            return ImageFont.truetype(_FONT_BOLD, size)
        return ImageFont.truetype(_FONT_REGULAR, size)
    except Exception:
        return ImageFont.load_default()


def _draw_watermark(page: Image.Image, w: int, h: int) -> None:
    """Tile a faint diagonal '7G HOUSE' watermark across the page."""
    try:
        wm_font = _font(120, bold=True)
    except Exception:
        return
    text = "7G HOUSE"
    step_x, step_y = 400, 350
    for row in range(-1, h // step_y + 2):
        for col in range(-1, w // step_x + 2):
            x = col * step_x + (row % 2) * (step_x // 2) - 60
            y = row * step_y - 40
            try:
                tmp = Image.new("RGBA", (500, 160), (0, 0, 0, 0))
                tmp_d = ImageDraw.Draw(tmp)
                tmp_d.text((10, 10), text, font=wm_font, fill=(80, 80, 80, 18))
                tmp = tmp.rotate(35, expand=True)
                page.paste(tmp, (x, y), tmp)
            except Exception:
                pass


def _draw_header(draw: ImageDraw.ImageDraw, w: int) -> None:
    """Top dark header band with logo text + report title."""
    draw.rectangle([0, 0, w, 90], fill=CLR_PRIMARY)
    draw.text((36, 18), "7G HOUSE", font=_font(32, bold=True), fill=CLR_WHITE)
    subtitle = "CONSTRUCTION INTELLIGENCE REPORT"
    draw.text((36, 56), subtitle, font=_font(14), fill=(180, 210, 240))
    # Right-side accent bar
    draw.rectangle([w - 8, 0, w, 90], fill=CLR_ACCENT)


def _draw_footer(draw: ImageDraw.ImageDraw, w: int, h: int, page_num: int) -> None:
    """Bottom footer with border, tagline and page number."""
    fy = h - 60
    draw.line([(36, fy), (w - 36, fy)], fill=CLR_BORDER, width=1)
    draw.text(
        (36, fy + 10),
        "7G House Cameroon — Architectural Intelligence",
        font=_font(14),
        fill=CLR_MUTED,
    )
    pn = f"Page {page_num}"
    draw.text((w - 120, fy + 10), pn, font=_font(14), fill=CLR_MUTED)


def _build_cover_page(generation_data: dict, page_num: int = 1) -> Image.Image:
    """Build the cover/spec page."""
    img = Image.new("RGB", (A4_W, A4_H), CLR_BG)
    draw = ImageDraw.Draw(img)

    # Watermark
    _draw_watermark(img, A4_W, A4_H)
    # Header
    _draw_header(draw, A4_W)

    # ── Title block ───────────────────────────────────────────────────────────
    ty = 130
    gen_type = generation_data.get("generation_type", "house_plan")
    spec = generation_data.get("floor_plan_spec") or {}

    # Main title
    if gen_type == "floor_plan":
        bedrooms = spec.get("num_bedrooms", 0)
        title = f"Floor Plan — {bedrooms}-Bedroom Project"
    else:
        style = generation_data.get("house_style") or "Residential"
        title = f"{style} House Design"

    draw.text((A4_W // 2, ty), "PROJECT REPORT", font=_font(48, bold=True),
              fill=CLR_PRIMARY, anchor="mt")

    # Accent divider
    div_w = 100
    draw.rectangle([(A4_W // 2 - div_w // 2, ty + 72),
                    (A4_W // 2 + div_w // 2, ty + 78)], fill=CLR_ACCENT)

    draw.text((A4_W // 2, ty + 96), title, font=_font(28),
              fill=CLR_DARK, anchor="mt")

    # Client name if present
    client = generation_data.get("client_name")
    if client:
        draw.text((A4_W // 2, ty + 140), f"Prepared for: {client}",
                  font=_font(20), fill=CLR_MUTED, anchor="mt")

    # ── Spec table ────────────────────────────────────────────────────────────
    table_top = ty + 200
    draw.rectangle([80, table_top, A4_W - 80, table_top + 2], fill=CLR_BORDER)

    rows: list[tuple[str, str]] = []

    if gen_type == "floor_plan":
        rows = [
            ("Region",   spec.get("region", "—")),
            ("Division", spec.get("division", "—")),
            ("Bedrooms", str(spec.get("num_bedrooms", "—"))),
            ("Bathrooms", str(spec.get("num_bathrooms", "—"))),
            ("Gross Area", f"{spec.get('gross_area', '—')} m²"),
            ("Kitchen",  str(spec.get("kitchen_type", "—")).capitalize()),
        ]
        if extras := spec.get("extras"):
            rows.append(("Extras", ", ".join(extras)))
    else:
        rows = [
            ("Style",      generation_data.get("house_style", "—")),
            ("Region",     generation_data.get("region", "—")),
            ("Division",   generation_data.get("division", "—")),
            ("Bedrooms",   str(generation_data.get("num_bedrooms", "—"))),
            ("Bathrooms",  str(generation_data.get("num_bathrooms", "—"))),
            ("Gross Area", f"{generation_data.get('gross_area', '—')} m²"),
            ("Roof",       generation_data.get("roof_type", "—")),
            ("Foundation", generation_data.get("foundation", "—")),
        ]
        if ks := generation_data.get("key_rooms"):
            rows.append(("Key Rooms", ", ".join(ks)))
        if os_ := generation_data.get("outdoor_spaces"):
            rows.append(("Outdoor", ", ".join(os_)))

    row_h = 58
    for i, (label, value) in enumerate(rows):
        ry = table_top + 16 + i * row_h
        bg_col = CLR_WHITE if i % 2 == 0 else CLR_BG
        draw.rectangle([80, ry, A4_W - 80, ry + row_h - 4], fill=bg_col)
        draw.text((100, ry + 10), label.upper(), font=_font(14, bold=True),
                  fill=CLR_MUTED)
        # Wrap long values
        wrapped = textwrap.fill(value, width=50)
        draw.text((480, ry + 10), wrapped, font=_font(18, bold=True),
                  fill=CLR_PRIMARY)

    # ── Description blurb ─────────────────────────────────────────────────────
    desc_y = table_top + 30 + len(rows) * row_h + 20
    desc = (
        "This document contains the architectural visualisation report for the "
        "specified property, including floor plans, elevations, exterior renders, "
        "cross-sections, and structural views generated by the 7G House AI platform."
    )
    for i, line in enumerate(textwrap.wrap(desc, width=90)):
        draw.text((A4_W // 2, desc_y + i * 28), line,
                  font=_font(16), fill=CLR_MUTED, anchor="mt")

    # Footer
    _draw_footer(draw, A4_W, A4_H, page_num)

    return img


def _fit_image_to_page(src: Image.Image) -> Image.Image:
    """Scale src to fit within the A4 image area (keeping aspect ratio)."""
    area_w = A4_W - 80
    area_h = A4_H - 200   # leave room for header (90) + footer (60) + caption
    ratio = min(area_w / src.width, area_h / src.height)
    new_w = int(src.width * ratio)
    new_h = int(src.height * ratio)
    return src.resize((new_w, new_h), Image.LANCZOS)


def _build_image_page(
    img_data: bytes,
    label: str,
    page_num: int,
) -> Optional[Image.Image]:
    """Build a single A4 page containing one project image + label."""
    try:
        src = Image.open(io.BytesIO(img_data)).convert("RGB")
    except Exception as e:
        logger.warning(f"pdf_service: cannot open image for page {page_num}: {e}")
        return None

    page = Image.new("RGB", (A4_W, A4_H), CLR_BG)
    draw = ImageDraw.Draw(page)

    _draw_watermark(page, A4_W, A4_H)
    _draw_header(draw, A4_W)

    # Fit and centre the image
    fitted = _fit_image_to_page(src)
    x = (A4_W - fitted.width) // 2
    y = 100 + (A4_H - 200 - fitted.height) // 2
    page.paste(fitted, (x, y))

    # Caption
    if label:
        cap_y = y + fitted.height + 16
        draw.text((A4_W // 2, cap_y), label.upper(),
                  font=_font(18, bold=True), fill=CLR_MUTED, anchor="mt")

    _draw_footer(draw, A4_W, A4_H, page_num)
    return page


async def build_project_pdf(generation_data: dict) -> Optional[io.BytesIO]:
    """
    Build a branded multi-page PDF from a generation document.
    Returns a BytesIO buffer with name set to 'Project_Report.pdf',
    or None on failure.
    """
    images: list[dict] = generation_data.get("images", [])
    headers = {"User-Agent": "7G-House-PDF/1.0"}

    pages: list[Image.Image] = []

    # ── Page 1: Cover ─────────────────────────────────────────────────────────
    try:
        cover = _build_cover_page(generation_data, page_num=1)
        pages.append(cover)
    except Exception as e:
        logger.error(f"pdf_service: cover page failed: {e}")

    # ── Pages 2…N: Project images ─────────────────────────────────────────────
    page_num = 2
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for img_meta in images:
            url = img_meta.get("url", "")
            label = img_meta.get("label", "") or f"View {page_num - 1}"
            if not url:
                continue
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                img_bytes = resp.content
            except Exception as e:
                logger.warning(f"pdf_service: failed to download image '{url[:60]}': {e}")
                continue

            page = _build_image_page(img_bytes, label, page_num)
            if page:
                pages.append(page)
                page_num += 1

    if not pages:
        logger.error("pdf_service: no pages generated")
        return None

    # ── Assemble PDF ───────────────────────────────────────────────────────────
    def _assemble_pdf():
        buf = io.BytesIO()
        first = pages[0]
        rest  = pages[1:] if len(pages) > 1 else []
        first.save(
            buf,
            format="PDF",
            save_all=True,
            append_images=rest,
            resolution=150,
            title="7G House Construction Intelligence Report",
            author="7G House",
            subject="Architectural Visualisation Report",
        )
        buf.seek(0)
        buf.name = "Project_Report.pdf"
        return buf

    try:
        buf = await asyncio.to_thread(_assemble_pdf)
    except Exception as e:
        logger.error(f"pdf_service: failed to save PDF: {e}")
        return None

    logger.info(
        f"pdf_service: built PDF with {len(pages)} pages "
        f"({len(buf.getvalue())} bytes)"
    )
    return buf


async def upload_pdf_to_storage(pdf_buf: io.BytesIO, generation_id: str) -> Optional[str]:
    """
    Upload the PDF buffer to Firebase Storage and return the public URL.
    Uses the same bucket as storage_service.
    """
    from app.db.firebase import bucket
    import uuid

    if bucket is None:
        logger.error("pdf_service: Firebase Storage bucket not initialised")
        return None

    try:
        blob_path = f"telegram_pdfs/{generation_id}/{uuid.uuid4().hex}.pdf"
        blob = bucket.blob(blob_path)
        pdf_buf.seek(0)
        blob.upload_from_file(pdf_buf, content_type="application/pdf")
        blob.make_public()
        url = blob.public_url
        logger.info(f"pdf_service: uploaded PDF → {url}")
        return url
    except Exception as e:
        logger.error(f"pdf_service: upload failed: {e}")
        return None


async def delete_pdf_from_storage(pdf_url: str) -> bool:
    """Delete a PDF file from Firebase Storage given its public URL."""
    from app.db.firebase import bucket

    if bucket is None:
        logger.error("pdf_service: Firebase Storage bucket not initialised")
        return False

    if not pdf_url:
        return False

    try:
        from urllib.parse import urlparse
        parsed = urlparse(pdf_url)
        blob_path = parsed.path.lstrip("/")
        if blob_path.startswith(f"{bucket.name}/"):
            blob_path = blob_path[len(bucket.name) + 1:]
        blob = bucket.blob(blob_path)
        if blob.exists():
            blob.delete()
            logger.info(f"pdf_service: deleted PDF from storage → {blob_path}")
            return True
        else:
            logger.warning(f"pdf_service: PDF blob not found → {blob_path}")
            return False
    except Exception as e:
        logger.error(f"pdf_service: delete failed: {e}")
        return False
