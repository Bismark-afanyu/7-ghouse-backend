import httpx
import base64
import asyncio
import urllib.parse
import logging
import time
from google.genai import types
from typing import Optional
from app.services.genai_client import get_genai_client
from app.services.label_service import overlay_labels, overlay_room_labels

logger = logging.getLogger(__name__)

MAX_VIEW_RETRIES = 3
RETRY_BASE_DELAY = 2.0
GEMINI_CALL_TIMEOUT = 180  # seconds per Gemini API call attempt


def get_views_to_generate(property_type: str, multi_story: bool = False, num_stories: int = 1) -> list[str]:
    views = [
        "floor_plans_composite",
        "elevations_composite",
        "exterior_3d_composite",
        "interior_living_composite",
        "master_suite_composite",
        "topdown_3d_view",
    ]
    if multi_story and num_stories >= 2:
        views.append("topdown_3d_ground_floor")
        views.append("topdown_3d_upper_floor")
    views.append("measurements_table")
    return views


def get_view_labels() -> dict[str, str]:
    return {
        "floor_plans_composite": "Floor Plans",
        "elevations_composite": "Elevations",
        "exterior_3d_composite": "3D Exterior",
        "interior_living_composite": "Living & Kitchen",
        "master_suite_composite": "Master Suite",
        "topdown_3d_view": "3D Top-Down View",
        "topdown_3d_ground_floor": "Ground Floor (Top-Down)",
        "topdown_3d_upper_floor": "Upper Floor (Top-Down)",
        "measurements_table": "Room Measurements",
    }


QUALITY_SUFFIX = (
    "ULTRA-HIGH QUALITY: 4K resolution, 8K quality rendering, sharp focus, crystal clear details, "
    "photorealistic quality, architectural visualization industry standard, "
    "no blur, no artifacts, no compression, perfect lighting and color accuracy. "
    "Do NOT render any text, labels, or annotations inside the image."
)


def build_prompt(
    property_type: str,
    num_rooms: int,
    num_bathrooms: int = 2,
    land_size: str = "",
    architectural_style: str = "",
    view_type: str = "3d_exterior",
    additional_preferences: Optional[str] = None,
    num_stories: int = 1,
    roof_type: str = "Flat",
    reference_analysis: Optional[str] = None,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
    building_type: str = "single_family",
) -> str:
    wabi_sabi_style = (
        "warm wabi-sabi style. Use light natural wood, textured plaster or limewash walls, soft stone surfaces, linen fabrics, "
        "and earthy tones like beige, sand, taupe, and muted brown. Keep furniture minimal, low-profile, and organic in shape. "
        "Add subtle imperfections, handmade decor, ceramics, and light greenery for a lived-in natural feel. "
        "Ensure the layout feels calm, uncluttered, and balanced. Use soft natural lighting, as if daylight is coming through the windows. "
        "Maintain a clean, premium interior design look with photorealistic materials and textures, high detail, interior design visualization quality, no text, no UI elements."
    )

    roof_lower = roof_type.lower()
    if roof_lower.startswith("flat"):
        roof_desc = "flat-roofed"
    else:
        roof_desc = f"{roof_lower}-roofed"

    story_text = f"{num_stories}-story" if num_stories > 1 else "single-story"
    architectural_dna = (
        f"This specific {property_type} has a distinctive {story_text} geometry: "
        f"A {roof_desc} structure. "
        f"The facade is well-composed with high-quality materials consistent with {architectural_style} style, "
        "clean lines, and appropriately sized windows and doors. "
        "The landscaping is tasteful and appropriate for the setting."
    )

    master_seed = (
        f"A cohesive {architectural_style} {property_type}. "
        f"{architectural_dna} "
        "Every view must show the EXACT SAME building materials, colors, and structural geometry. "
        "Consistency is mandatory."
    )

    base_info = f"{architectural_style} style {property_type} with {num_rooms} rooms, {num_kitchens} kitchen{'s' if num_kitchens > 1 else ''}, and {num_living_rooms} living room{'s' if num_living_rooms > 1 else ''} on a {land_size} plot."

    story_info = ""
    if num_stories > 1:
        story_info = f"This is a {num_stories}-story building with stairs connecting all floors."
    else:
        story_info = "This is a single-story building."

    if num_stories > 1:
        floor_plans_prompt = (
            f"A professional architectural 2D floor plan drawing sheet for a {base_info}. "
            "Composite sheet layout showing all floor plans in one clean, elegant architectural document. "
            "Include GROUND FLOOR and UPPER FLOOR plans arranged vertically, with a staircase clearly shown connecting both levels. "
            "Each room MUST be clearly labeled with its room name in clean uppercase text inside the room boundary. "
        )
    else:
        floor_plans_prompt = (
            f"A professional architectural 2D floor plan drawing sheet for a {base_info}. "
            "A single clean floor plan showing the complete single-story layout in one sheet. "
            "Each room MUST be clearly labeled with its room name in clean uppercase text inside the room boundary. "
        )

    # Build dynamic room label list based on actual counts
    room_labels = ["MASTER BEDROOM"]
    for i in range(max(0, num_rooms - 1)):
        room_labels.append(f"BEDROOM {i + 2}")
    for i in range(num_bathrooms):
        room_labels.append(f"BATHROOM" if num_bathrooms == 1 else f"BATHROOM {i + 1}")
    for i in range(num_kitchens):
        room_labels.append(f"KITCHEN" if num_kitchens == 1 else f"KITCHEN {i + 1}")
    for i in range(num_living_rooms):
        room_labels.append(f"LIVING ROOM" if num_living_rooms == 1 else f"LIVING ROOM {i + 1}")
    room_labels.append("DINING ROOM")
    room_labels.append("HALLWAY")
    room_labels_str = ", ".join(room_labels)

    floor_plans_prompt += (
        f"Label every room: {room_labels_str}, etc. "
        "Room labels must be legible, centered inside each room, and use a consistent architectural font style. "
        "Style: Clean fine black vector-style linework on a solid, pure white background. "
        "Zero color, zero gray fills, zero realistic rendering, zero shading or shadow gradients, zero paper textures, and zero blue grids. "
        "Precise thin black line drawings of rooms, wall thicknesses, door swing symbols, window cutouts"
    )
    if num_stories > 1:
        floor_plans_prompt += ", staircases, and simple furniture shapes. "
    else:
        floor_plans_prompt += ", and simple furniture shapes. "
    floor_plans_prompt += (
        "Professional architectural CAD/Revit export quality, minimal, high-contrast, clean blueprint lines. "
        "ULTRA-HIGH QUALITY: 4K resolution, sharp focus, crystal clear readable text, no blur, no artifacts."
    )

    if num_stories > 1:
        section_detail = (
            "Clearly show: floor-to-floor heights with dimension annotations, "
            "the staircase in full section with each step visible, room layouts on each level, "
            "window and door openings in section, roof structure, foundation depth, and ceiling heights. "
        )
    else:
        section_detail = (
            "Clearly show: the roof structure with pitch, ceiling height, wall section with insulation, "
            "window and door openings in section, slab-on-grade or raised foundation, and interior room layout. "
            "Since this is a single-story home, there are no stairs. The section focuses on the clean single-level layout. "
        )

    flat_detail = ""
    if roof_type.lower().startswith("flat") and "buildable" in roof_type.lower():
        flat_detail = (
            "The flat roof is a reinforced concrete slab designed to support future construction above, "
            "show visible column rebar stubs extending above the slab for future column continuity. "
        )
    elif roof_type.lower().startswith("flat") and "non-buildable" in roof_type.lower():
        flat_detail = (
            "The flat roof is a standard waterproofed terrace slab, no structural provisions for future upward expansion. "
        )

    cross_section_prompt = (
        f"A professional architectural cross-section rendering through a {story_text} {property_type.lower()} "
        f"with a {roof_type.lower()} roof on a {land_size} plot. "
        f"{story_info} "
        f"The building has a {roof_type.lower()} roof structure clearly visible in the section cut. "
        f"{flat_detail}"
        "The section cut passes through the building showing interior spaces from the side, "
        "revealing the vertical organization of rooms. "
        f"{section_detail}"
        "Photorealistic materials: concrete slabs in grey, wooden roof structures, "
        "painted drywall walls, glass windows, tiled bathroom finishes. "
        "Professional architectural section standard, clean composition, white or light background. "
        f"{QUALITY_SUFFIX}"
    )

    prompts = {
        "floor_plans_composite": floor_plans_prompt,
        "elevations_composite": (
            f"A professional architectural elevation sheet showing exterior elevations of a {base_info}. "
            "It is a composite layout consisting of exactly four orthographic flat 2D elevation drawings: "
            "FRONT ELEVATION (top-left), REAR ELEVATION (top-right), "
            "LEFT ELEVATION (bottom-left), RIGHT ELEVATION (bottom-right). "
            "Layout structure: Organized in a 2x2 grid divided by thin grey vertical and horizontal divider lines on a solid pure white background. "
            "Style: Pure black-and-white clean vector-style technical line-art drawing. "
            "CRITICAL: Zero color, zero gray fills, zero shading, zero shadows, zero rendering gradients, zero paper textures, and zero blue grids. "
            "Every line is a fine, clean, high-contrast crisp black outline stroke (Revit/CAD export style). "
            "Do NOT render any text or labels. "
            "Show structural details purely as clean line-drawing patterns: vertical lines for vertical board-and-batten siding, "
            "parallel horizontal lines for horizontal lap siding, clean fine outlines for brick/stone veneer patterns, and parallel rows for roof shingles. "
            "No landscape elements, no sky, no trees, no grass, no people, and no background shadows. Pure crisp line-drawing only."
        ),
        "exterior_3d_composite": (
            f"A premium photorealistic 3D exterior rendering composite of a {base_info}. "
            f"{story_info} "
            f"The building has a {roof_type.lower()} roof. "
            "Split-screen layout. LEFT HALF: FRONT exterior view of the house — eye-level perspective showing the main entrance, "
            "landscaped front yard, facade details, and entrance. "
            "RIGHT HALF: REAR exterior view — showing the back patio, terrace, garden, and rear facade. "
            f"{master_seed} Professional architectural visualization, dramatic golden hour lighting, "
            "vibrant greens, blue sky, ultra-detailed materials and textures. "
            f"{QUALITY_SUFFIX}"
        ),
        "interior_living_composite": (
            f"Split-screen interior rendering composite of a {base_info}. "
            "LEFT HALF: LIVING ROOM — eye-level view showing the main seating area, large windows, "
            "coffee table, and natural light flooding the space. "
            "RIGHT HALF: KITCHEN & DINING — wide-angle view showing the kitchen island, cabinetry, "
            f"dining table, and adjacent breakfast area. "
            f"Style: {wabi_sabi_style} Both halves must show the exact same material palette and design language. "
            f"{QUALITY_SUFFIX}"
        ),
        "master_suite_composite": (
            f"Split-screen interior rendering composite of a {base_info}. "
            "LEFT HALF: MASTER BEDROOM — eye-level view showing the bed, bedside tables, large windows, "
            "walk-in closet entrance, and soft natural lighting. "
            "RIGHT HALF: LUXURY BATHROOM — showing the double vanity, freestanding bathtub, "
            f"glass shower, and premium tilework. "
            f"Style: {wabi_sabi_style} Spa-like atmosphere. Both halves must feel like the same cohesive suite. "
            f"{QUALITY_SUFFIX}"
        ),
        "topdown_3d_view": (
            f"A photorealistic 3D top-down bird's eye view of the complete {base_info}. "
            f"{story_info} "
            "The camera looks straight down from above showing the entire floor layout in stunning 3D detail. "
            "Every room is clearly visible with color-coded flooring: warm wood in living areas, "
            "cool tile in kitchens and bathrooms, carpet in bedrooms. "
            "Fully furnished: sofas, coffee tables, dining sets, beds, kitchen islands, bathroom fixtures, "
            "wardrobes, and decor items all visible from above. "
            "Wall lines are crisp and well-defined with consistent thickness. "
            "Do NOT render any text, labels, or annotations inside the image. "
            "Show windows as glass panels, doors as open or closed panels, and stairs as clearly defined steps. "
            "The view should feel like a high-end real estate architectural flythrough screenshot. "
            f"{QUALITY_SUFFIX}"
        ),
        "topdown_3d_ground_floor": (
            f"A photorealistic 3D top-down bird's eye view of only the GROUND FLOOR of the {base_info}. "
            "The camera looks straight down showing just the ground floor layout in stunning 3D detail. "
            "Color-coded flooring: warm wood in living areas, cool tile in kitchens and bathrooms. "
            "Fully furnished with all ground floor furniture: sofas, coffee table, dining table, chairs, "
            "kitchen island with stools, bathroom fixtures, entryway furniture. "
            "Crisp wall lines, glass windows, door panels. "
            "Do NOT render any text, labels, or annotations inside the image. "
            "Show the staircase opening as a clear void with stair treads visible. "
            "High-end architectural presentation quality. "
            f"{QUALITY_SUFFIX}"
        ),
        "topdown_3d_upper_floor": (
            f"A photorealistic 3D top-down bird's eye view of only the UPPER FLOOR(S) of the {base_info}. "
            "The camera looks straight down showing the upper level layout in stunning 3D detail. "
            "Color-coded flooring: warm wood or carpet in bedrooms, cool tile in bathrooms. "
            "Fully furnished: beds with bedding, nightstands, dressers, wardrobes, bathroom vanities, "
            "bathtubs, showers, and any loft or study area furniture. "
            "Crisp wall lines, glass windows, door panels. "
            "Do NOT render any text, labels, or annotations inside the image. "
            "Show the staircase as a clearly defined void with railing. "
            "High-end architectural presentation quality. "
            f"{QUALITY_SUFFIX}"
        ),
        "measurements_table": (
            f"A professional architectural room measurements table (room schedule) for a {base_info}. "
            f"{story_info} "
            "Generate a clean, professionally formatted table with the following columns: "
            "ROOM NAME, DIMENSIONS (Width x Length in meters), AREA (m²), FLOOR LEVEL (Ground/Upper). "
            "The table must include entries for ALL rooms in the house: "
            "Living/Dining Room, Kitchen, Master Bedroom, additional bedrooms, bathrooms, "
            "and any special rooms (home office, media room, etc.). "
            "Style: Clean architectural schedule format with thin grid lines, "
            "a header row in dark gray with white text, alternating light gray and white rows, "
            "and professional sans-serif fonts. "
            "The header should read 'ROOM SCHEDULE — ROOM MEASUREMENTS' in bold centered text. "
            "White background, professional architectural presentation quality. "
            "Dimensions and areas must be realistic and proportional for a house of this size. "
            "Do NOT add any text outside the table."
        ),
    }

    prompt = prompts.get(view_type, prompts["exterior_3d_composite"])
    if additional_preferences:
        prompt += f" Special user requirements to integrate: {additional_preferences}."
    if reference_analysis:
        prompt += f"\n\nReference floor plan analysis — use these insights to improve the design: {reference_analysis}"

    return prompt


async def generate_images(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str] = None,
    num_images: int = 1,
    is_multi_story: bool = False,
    num_stories: int = 1,
    overlay_language: str = "en",
    num_bathrooms: int = 2,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
) -> tuple[str, list[bytes]]:
    views_to_generate = get_views_to_generate(property_type, multi_story=is_multi_story, num_stories=num_stories)
    labels = get_view_labels()
    client = get_genai_client()

    async def generate_gemini_image(prompt_text: str) -> Optional[bytes]:
        try:
            def call():
                return client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=prompt_text,
                    config=types.GenerateContentConfig(response_modalities=["Image", "Text"])
                )
            response = await asyncio.to_thread(call)
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    return part.inline_data.data
            return None
        except Exception as e:
            print(f"Gemini Error: {e}")
            return None

    all_images = []
    master_prompt = ""
    for i, view in enumerate(views_to_generate):
        prompt = build_prompt(
            property_type, num_rooms, num_bathrooms, land_size, architectural_style, view,
            additional_preferences, num_stories=num_stories,
            num_kitchens=num_kitchens, num_living_rooms=num_living_rooms,
        )
        if i == 0: master_prompt = prompt
        print(f"Generating {view} via Gemini (gemini-2.5-flash-image)...")
        img_bytes = await generate_gemini_image(prompt)
        if img_bytes:
            labeled_bytes = overlay_labels(
                img_bytes, view,
                language=overlay_language,
                num_bedrooms=num_rooms,
                num_bathrooms=num_bathrooms,
                kitchen_type=kitchen_type,
                key_rooms=key_rooms,
                outdoor_spaces=outdoor_spaces,
            )
            all_images.append((labels[view], labeled_bytes))
            print(f"{view} completed!")
        else:
            print(f"Gemini failed to generate {view}.")
    return master_prompt, all_images


async def generate_images_stream(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str] = None,
    is_multi_story: bool = False,
    num_stories: int = 1,
    roof_type: str = "Flat",
    cancel_event: Optional[asyncio.Event] = None,
    overlay_language: str = "en",
    num_bathrooms: int = 2,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
    building_type: str = "single_family",
    layout=None,
    layout_task=None,
    reference_image_bytes: Optional[bytes] = None,
    reference_mime_type: str = "image/jpeg",
    reference_analysis: Optional[str] = None,
):
    if cancel_event and cancel_event.is_set():
        yield {"type": "cancelled"}
        return

    views_to_generate = get_views_to_generate(property_type, multi_story=is_multi_story, num_stories=num_stories)
    labels = get_view_labels()

    view_list = [{"key": v, "label": labels[v]} for v in views_to_generate]
    yield {"type": "view_list", "views": view_list}

    try:
        client = get_genai_client()
    except Exception as e:
        yield {"type": "error", "message": f"Failed to initialize AI client: {str(e)}"}
        return

    async def generate_gemini_image(
        prompt_text: str,
        ref_image: Optional[bytes] = None,
        ref_mime_type: str = "image/jpeg",
        view_label: str = "",
    ) -> Optional[bytes]:
        contents_parts = [types.Part(text=prompt_text)]
        if ref_image:
            contents_parts.append(
                types.Part(inline_data=types.Blob(mime_type=ref_mime_type, data=ref_image))
            )

        last_error = None
        for attempt in range(1 + MAX_VIEW_RETRIES):
            try:
                def call():
                    return client.models.generate_content(
                        model="gemini-2.5-flash-image",
                        contents=types.Content(parts=contents_parts, role="user"),
                        config=types.GenerateContentConfig(response_modalities=["Image", "Text"])
                    )
                t0 = time.monotonic()
                try:
                    response = await asyncio.wait_for(asyncio.to_thread(call), timeout=GEMINI_CALL_TIMEOUT)
                except asyncio.TimeoutError:
                    elapsed = time.monotonic() - t0
                    logger.warning(
                        "[Gemini] %s: call timed out after %.1fs (attempt %d/%d)",
                        view_label, elapsed, attempt + 1, 1 + MAX_VIEW_RETRIES,
                    )
                    last_error = f"timeout_{GEMINI_CALL_TIMEOUT}s"
                    if attempt < MAX_VIEW_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    return None
                elapsed = time.monotonic() - t0

                candidates = getattr(response, "candidates", None) or []
                if not candidates:
                    logger.warning(
                        "[Gemini] %s: no candidates returned (attempt %d/%d, %.1fs)",
                        view_label, attempt + 1, 1 + MAX_VIEW_RETRIES, elapsed,
                    )
                    last_error = "no_candidates"
                    if attempt < MAX_VIEW_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info("[Gemini] %s: retrying in %.1fs...", view_label, delay)
                        await asyncio.sleep(delay)
                        continue
                    return None

                candidate = candidates[0]
                parts = getattr(getattr(candidate, "content", None), "parts", None) or []
                for part in parts:
                    if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                        logger.info(
                            "[Gemini] %s: image generated (%.1fs, attempt %d)",
                            view_label, elapsed, attempt + 1,
                        )
                        return part.inline_data.data

                text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]
                logger.warning(
                    "[Gemini] %s: no image in response (attempt %d/%d, %.1fs). Text: %s",
                    view_label, attempt + 1, 1 + MAX_VIEW_RETRIES, elapsed,
                    text_parts[:2] if text_parts else "(none)",
                )
                last_error = "no_image_in_response"
                if attempt < MAX_VIEW_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.info("[Gemini] %s: retrying in %.1fs...", view_label, delay)
                    await asyncio.sleep(delay)

            except Exception as e:
                elapsed = time.monotonic() - t0 if 't0' in dir() else 0
                error_type = type(e).__name__
                error_str = str(e)
                is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                logger.error(
                    "[Gemini] %s: exception (attempt %d/%d, %.1fs): %s: %s",
                    view_label, attempt + 1, 1 + MAX_VIEW_RETRIES, elapsed,
                    error_type, e,
                )
                last_error = f"{error_type}: {e}"
                if attempt < MAX_VIEW_RETRIES:
                    if is_rate_limit:
                        delay = 15.0 * (3 ** attempt)  # 15s, 45s for 429s
                    else:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)  # 2s, 4s for other errors
                    logger.info("[Gemini] %s: retrying in %.1fs (%s)...", view_label, delay, "rate_limit" if is_rate_limit else "error")
                    await asyncio.sleep(delay)

        logger.error("[Gemini] %s: all %d attempts exhausted. Last error: %s", view_label, 1 + MAX_VIEW_RETRIES, last_error)
        return None

    layout_resolved = False
    resolved_layout = None
    for i, view in enumerate(views_to_generate):
        try:
            if cancel_event and cancel_event.is_set():
                yield {"type": "cancelled"}
                return

            # Small delay between views to avoid hitting rate limits
            if i > 0:
                await asyncio.sleep(2)

            prompt = build_prompt(
                property_type, num_rooms, num_bathrooms, land_size, architectural_style, view,
                additional_preferences, num_stories=num_stories, roof_type=roof_type,
                reference_analysis=reference_analysis,
                num_kitchens=num_kitchens, num_living_rooms=num_living_rooms,
                building_type=building_type,
            )
            if i == 0:
                yield {"type": "master_prompt", "prompt": prompt}

            yield {"type": "view_start", "view_key": view, "label": labels[view]}
            yield {"type": "progress", "progress_type": "generating", "label": labels[view]}

            img_bytes = await generate_gemini_image(prompt, ref_image=reference_image_bytes, ref_mime_type=reference_mime_type, view_label=labels[view])

            if cancel_event and cancel_event.is_set():
                yield {"type": "cancelled"}
                return

            if img_bytes:
                try:
                    labeled_bytes = overlay_labels(
                        img_bytes, view,
                        language=overlay_language,
                        num_bedrooms=num_rooms,
                        num_bathrooms=num_bathrooms,
                        kitchen_type=kitchen_type,
                        key_rooms=key_rooms,
                        outdoor_spaces=outdoor_spaces,
                    )

                    needs_room_labels = view in ("topdown_3d_view", "topdown_3d_ground_floor", "topdown_3d_upper_floor")
                    if needs_room_labels and layout:
                        labeled_bytes = await asyncio.to_thread(
                            overlay_room_labels,
                            labeled_bytes,
                            layout.rooms,
                            layout.total_width_cm,
                            layout.total_height_cm,
                            overlay_language,
                        )
                    elif needs_room_labels and layout_task and not layout_resolved:
                        try:
                            resolved_layout = await asyncio.wait_for(layout_task, timeout=30)
                            layout_resolved = True
                            if resolved_layout:
                                labeled_bytes = await asyncio.to_thread(
                                    overlay_room_labels,
                                    labeled_bytes,
                                    resolved_layout.rooms,
                                    resolved_layout.total_width_cm,
                                    resolved_layout.total_height_cm,
                                    overlay_language,
                                )
                        except (asyncio.TimeoutError, Exception) as e:
                            print(f"[FloorPlan] Could not resolve layout for labels: {e}")
                    elif needs_room_labels and layout_resolved and resolved_layout:
                        labeled_bytes = await asyncio.to_thread(
                            overlay_room_labels,
                            labeled_bytes,
                            resolved_layout.rooms,
                            resolved_layout.total_width_cm,
                            resolved_layout.total_height_cm,
                            overlay_language,
                        )
                except Exception as e:
                    print(f"[Overlay] Error overlaying labels for {view}: {e}")
                    labeled_bytes = img_bytes

                yield {"type": "view_complete", "view_key": view, "label": labels[view]}
                yield {"type": "image", "label": labels[view], "bytes": labeled_bytes}
            else:
                yield {"type": "view_error", "view_key": view, "label": labels[view]}
                yield {"type": "progress", "message": f"Failed to generate {labels[view]}."}
        except Exception as e:
            print(f"[Stream] Unexpected error generating {view}: {e}")
            yield {"type": "view_error", "view_key": view, "label": labels[view], "error": str(e)}
            yield {"type": "progress", "message": f"Error generating {labels[view]}: {str(e)}"}



async def generate_single_view(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    view_type: str,
    additional_preferences: Optional[str] = None,
    num_stories: int = 1,
    roof_type: str = "Flat",
    overlay_language: str = "en",
    num_bathrooms: int = 2,
    num_kitchens: int = 1,
    num_living_rooms: int = 1,
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
) -> Optional[bytes]:
    client = get_genai_client()

    prompt = build_prompt(
        property_type, num_rooms, num_bathrooms, land_size, architectural_style, view_type,
        additional_preferences, num_stories=num_stories, roof_type=roof_type,
        num_kitchens=num_kitchens, num_living_rooms=num_living_rooms,
    )

    try:
        def call():
            return client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["Image", "Text"])
            )

        print(f"Regenerating {view_type} via Gemini (gemini-2.5-flash-image)...")
        response = await asyncio.to_thread(call)

        img_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                img_bytes = part.inline_data.data
                break

        if img_bytes:
            return overlay_labels(
                img_bytes, view_type,
                language=overlay_language,
                num_bedrooms=num_rooms,
                num_bathrooms=num_bathrooms,
                kitchen_type=kitchen_type,
                key_rooms=key_rooms,
                outdoor_spaces=outdoor_spaces,
            )

        return None
    except Exception as e:
        print(f"Gemini Error regenerating {view_type}: {e}")
        return None


async def _generate_placeholder_images(num_images: int) -> list[bytes]:
    placeholders = [
        "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800&q=80",
        "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=80",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&q=80",
    ]
    images: list[bytes] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(num_images):
            url = placeholders[i % len(placeholders)]
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                images.append(resp.content)
            except Exception:
                images.append(_minimal_png())
    return images


def _minimal_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


async def analyze_floor_plan_pdf(pdf_bytes: bytes, lang: str = "en") -> dict:
    """Convert PDF pages to images, then send to Gemini for comprehensive analysis.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        lang: Language for the AI response ("en" or "fr")
    """
    import json
    import fitz

    client = get_genai_client()

    is_fr = lang == "fr"

    if is_fr:
        prompt = (
            "Tu es un expert en analyse de plans d'architecture. Analyse ces images de plan d'étage.\n\n"
            "Réponds UNIQUEMENT en français. Les noms des pièces doivent rester dans leur langue "
            "originale présente sur le plan (ex: 'Chambre', 'Sejour', 'Cuisine') — ne les traduis PAS.\n\n"
            "Retourne ton analyse sous forme d'objet JSON avec ces clés :\n"
            "1. \"rooms\": une liste d'objets, chacun avec \"name\" (string, ex: \"Chambre\"), "
            "\"dimensions\" (string, ex: \"5m x 4m\" si visible, ou \"non spécifié\"), "
            "et \"floor\" (string, ex: \"Rez-de-chaussée\" ou \"Étage\"). "
            "Identifie UNIQUEMENT les 5 pièces les plus importantes du plan.\n"
            "2. \"layout_issues\": une liste de maximum 5 chaînes décrivant les principaux problèmes "
            "du plan (ex: \"Cuisine trop éloignée du salon\", \"Couloir trop étroit\"). "
            "Sois concis et pratique.\n"
            "3. \"suggestions\": une liste de maximum 5 chaînes avec des suggestions d'amélioration "
            "actionnables (ex: \"Rapprocher la cuisine du salon pour une meilleure circulation\"). "
            "Sois concis.\n"
            "4. \"summary\": une seule phrase donnant un aperçu simple du bâtiment "
            "(ex: \"Bâtiment de 3 étages avec 6 appartements, surface totale environ 350 m².\")\n"
            "5. \"inferred_fields\": un objet avec les champs déduits du plan :\n"
            "   - \"bedrooms\": int (nombre total de chambres)\n"
            "   - \"bathrooms\": float (nombre total de salles de bain/WC)\n"
            "   - \"gross_area\": string (surface totale en m², ex: \"474\")\n"
            "   - \"kitchen_type\": string (\"Ouverte\" ou \"Fermée\")\n"
            "   - \"is_multi_story\": bool (true si plusieurs étages)\n"
            "   - \"num_stories\": int ou null (nombre d'étages)\n"
            "   - \"roof_type\": string ou null (\"Toit en pente\", \"Toit terrasse\", etc.)\n\n"
            "IMPORTANT : Retourne UNIQUEMENT du JSON valide. Pas de markdown, pas de guillemets, pas de texte supplémentaire."
        )
    else:
        prompt = (
            "You are an expert architectural floor plan analyst. Analyze these floor plan images.\n\n"
            "Return your analysis as a JSON object with these keys:\n"
            "1. \"rooms\": a list of objects, each with \"name\" (string — keep the original room name from the plan, "
            "do NOT translate it, e.g. if the plan says 'Chambre' keep 'Chambre'), "
            "\"dimensions\" (string, e.g. \"5m x 4m\" if visible, or \"not specified\"), "
            "and \"floor\" (string, e.g. \"Ground\" or \"Upper\"). "
            "Identify ONLY the 5 most important rooms on the plan.\n"
            "2. \"layout_issues\": a list of up to 5 strings describing the main problems with the layout. "
            "Be concise and practical (e.g. \"Kitchen too far from living room\").\n"
            "3. \"suggestions\": a list of up to 5 strings with actionable improvement suggestions. "
            "Be concise (e.g. \"Move kitchen closer to living area for better flow\").\n"
            "4. \"summary\": a single sentence giving a plain-language overview of the building "
            "(e.g. \"3-story building with 6 apartments, total area approx 350 m².\")\n"
            "5. \"inferred_fields\": an object with form fields inferred from the plan:\n"
            "   - \"bedrooms\": int (total count of bedrooms across all floors)\n"
            "   - \"bathrooms\": float (total count of bathrooms/toilets across all floors)\n"
            "   - \"gross_area\": string (total gross floor area in m², e.g. \"474\")\n"
            "   - \"kitchen_type\": string (\"Open\" or \"Closed\")\n"
            "   - \"is_multi_story\": bool (whether the plan has stairs or multiple floors)\n"
            "   - \"num_stories\": int or null (number of floors above ground)\n"
            "   - \"roof_type\": string or null (\"Gable\", \"Hip\", \"Flat\", \"Pitched\", or null if not visible)\n\n"
            "CRITICAL: Return ONLY valid JSON. No markdown, no code fences, no extra text."
        )

    try:
        # Convert PDF pages to images
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        logger.info(f"[analyze_floor_plan_pdf] PDF has {total_pages} page(s)")

        max_pages = min(total_pages, 8)
        images = []

        for i in range(max_pages):
            page = doc[i]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")

            # Skip blank or tiny pages
            if len(img_bytes) < 5000:
                continue

            images.append(img_bytes)

            # Stop at 6 images — enough for most architectural sets
            if len(images) >= 6:
                break

        doc.close()

        if not images:
            logger.warning("[analyze_floor_plan_pdf] No image data extracted from PDF")
            return {
                "rooms": [],
                "layout_issues": ["Could not extract any readable pages from the PDF."],
                "suggestions": [],
                "summary": "PDF analysis failed. The file may be empty or corrupted.",
                "inferred_fields": {},
            }

        logger.info(f"[analyze_floor_plan_pdf] Extracted {len(images)} page image(s) from {total_pages} total page(s)")

        # Send images to Gemini
        def call():
            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(role="user", parts=[
                        types.Part(text=prompt),
                        *[
                            types.Part(inline_data=types.Blob(mime_type="image/png", data=img))
                            for img in images
                        ],
                    ])
                ],
            )

        response = await asyncio.to_thread(call)
        text = response.candidates[0].content.parts[0].text

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("\n", 1)[0]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        if not isinstance(result, dict):
            logger.warning(f"[analyze_floor_plan_pdf] Gemini returned a {type(result).__name__} instead of dict: {result}")
            result = {}

        # Warn if we got very few results despite many pages
        room_count = len(result.get("rooms", []))
        logger.info(f"[analyze_floor_plan_pdf] Analysis complete: {room_count} rooms identified")

        return {
            "rooms": result.get("rooms", []),
            "layout_issues": result.get("layout_issues", []),
            "suggestions": result.get("suggestions", []),
            "summary": result.get("summary", ""),
            "inferred_fields": result.get("inferred_fields", {}),
        }
    except Exception as e:
        import traceback
        error_detail = f"[analyze_floor_plan_pdf] Error: {type(e).__name__}: {e}"
        logger.error(error_detail)
        logger.error(traceback.format_exc())
        # Also print to stderr so Cloud Run definitely captures it
        print(f"PDF_ANALYSIS_ERROR: {error_detail}", flush=True)
        print(traceback.format_exc(), flush=True)
        return {
            "rooms": [],
            "layout_issues": [f"Could not fully analyze the PDF. Error: {type(e).__name__}: {str(e)}"],
            "suggestions": [],
            "summary": f"PDF analysis failed: {type(e).__name__}: {str(e)}",
            "inferred_fields": {},
        }


async def generate_floor_plan_image(
    prompt: str,
    view_type: str = "floor_plan_main",
    overlay_language: str = "en",
) -> Optional[bytes]:
    client = get_genai_client()

    try:
        def call():
            return client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["Image", "Text"]),
            )
        response = await asyncio.to_thread(call)
        img_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                img_bytes = part.inline_data.data
                break
        if img_bytes:
            return overlay_labels(img_bytes, view_type, language=overlay_language)
        return None
    except Exception as e:
        print(f"Floor plan generation error: {e}")
        try:
            fallback_prompt = f"Professional architectural floor plan: {prompt[:200]}"
            def call_fallback():
                return client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=fallback_prompt,
                    config=types.GenerateContentConfig(response_modalities=["Image", "Text"]),
                )
            response = await asyncio.to_thread(call_fallback)
            img_bytes = None
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    img_bytes = part.inline_data.data
                    break
            if img_bytes:
                return overlay_labels(img_bytes, view_type, language=overlay_language)
        except Exception as e2:
            print(f"Floor plan fallback also failed: {e2}")
        return None


async def analyze_plot_image(image_bytes: bytes, lang: str = "en") -> dict:
    """Analyze a plot/land image using Gemini and return structured plot information.

    Args:
        image_bytes: Raw image bytes (JPEG, PNG, etc.)
        lang: Language for the AI response ("en" or "fr")
    """
    import json

    client = get_genai_client()

    is_fr = lang == "fr"

    if is_fr:
        prompt = (
            "Tu es un expert en documents cadastraux camerounais, en analyse de terrains "
            "et en planification immobilière. Analyse cette image.\n\n"
            "Réponds UNIQUEMENT en français pour les champs texte.\n\n"
            "Retourne ton analyse sous forme d'objet JSON avec ces clés :\n\n"
            '1. "image_type": classe l\'image comme UN parmi : "cadastral_plan", "satellite", '
            '"architectural_plan", "hand_drawn", "floor_plan", "other"\n\n'
            '2. "plot_description": description générale du document ou du terrain (une phrase).\n\n'
            '3. "admin_info": (objet, si trouvé) métadonnées administratives du document cadastral :\n'
            '   - "country", "region", "department", "subdivision", "neighborhood", "locality"\n'
            '   - "block", "lot", "tf_number"\n'
            '   - "beneficiary", "applicant", "surveyor", "surveyor_company"\n'
            '   - "scale", "situation_plan_scale"\n'
            '   - "ministry", "delegation", "service"\n\n'
            '4. "dimensions": (objet) dimensions du terrain :\n'
            '   - "area_m2": surface en mètres carrés (nombre)\n'
            '   - "length_m": côté le plus long en mètres (nombre)\n'
            '   - "width_m": côté le plus court en mètres (nombre)\n'
            '   - "boundary_dimensions": tableau de {from, to, length_m} pour chaque segment de frontière\n\n'
            '5. "extracted_boundary": tableau de paires de coordonnées [x, y] pour chaque point '
            'limite (B1, B2, B3, B4) tel qu\'affiché dans le tableau de coordonnées du document.\n\n'
            '6. "extracted_gps": (objet) coordonnées GPS si visibles sur l\'image : {lat, lng}\n\n'
            '7. "terrain_type": "plat", "en pente", "fortement en pente", "accidenté", ou "" si non déterminable.\n\n'
            '8. "terrain_notes": notes détaillées sur le terrain (une phrase).\n\n'
            '9. "orientation_notes": orientation du terrain si visible.\n\n'
            '10. "constraints": tableau de contraintes observées.\n\n'
            '11. "suggested_dimensions": objet avec "length_m" et "width_m" — dimensions suggérées en mètres.\n\n'
            '12. "suggested_building_footprint": objet avec "length_m" et "width_m" — surface de construction suggérée.\n\n'
            '13. "setback_suggestions": objet avec "front", "rear", "left", "right" (nombres) — retraits suggérés en mètres.\n\n'
            '14. "access_info": (objet) {type: "servitude"|"route"|"autre", description: "..."}\n\n'
            '15. "nearby_references": tableau de numéros de titres fonciers à proximité (ex: "TF-32626/W")\n\n'
            "IMPORTANT : Retourne UNIQUEMENT du JSON valide. Pas de markdown, pas de code fences, pas de texte supplémentaire. "
            "Les valeurs numériques doivent être des nombres, pas des chaînes. "
            "Si un champ n'est pas trouvé, utilise null ou tableau vide."
        )
    else:
        prompt = (
            "You are an expert in Cameroonian cadastral survey documents, land plot analysis, "
            "and real estate planning. Analyze this image.\n\n"
            "Return your analysis as a JSON object with these keys:\n\n"
            '1. "image_type": classify the image as ONE of: "cadastral_plan", "satellite", '
            '"architectural_plan", "hand_drawn", "floor_plan", "other"\n\n'
            '2. "plot_description": general description of the document or plot (one sentence).\n\n'
            '3. "admin_info": (object, if found) administrative metadata from the cadastral/survey document:\n'
            '   - "country", "region", "department", "subdivision", "neighborhood", "locality"\n'
            '   - "block", "lot", "tf_number"\n'
            '   - "beneficiary", "applicant", "surveyor", "surveyor_company"\n'
            '   - "scale", "situation_plan_scale"\n'
            '   - "ministry", "delegation", "service"\n\n'
            '4. "dimensions": (object) land dimensions:\n'
            '   - "area_m2": surface area in square meters (number)\n'
            '   - "length_m": longest side in meters (number)\n'
            '   - "width_m": shortest side in meters (number)\n'
            '   - "boundary_dimensions": array of {from, to, length_m} for each boundary segment '
            '(e.g. B1 to B2 = 8.21m)\n\n'
            '5. "extracted_boundary": array of [x, y] coordinate pairs for each boundary marker '
            '(B1, B2, B3, B4) as shown in the coordinate table on the document.\n\n'
            '6. "extracted_gps": (object) GPS coordinates if visible on the image: {lat, lng}\n\n'
            '7. "terrain_type": "flat", "sloped", "steep", "uneven", or "" if not determinable.\n\n'
            '8. "terrain_notes": detailed notes about the terrain (one sentence).\n\n'
            '9. "orientation_notes": orientation of the plot if visible.\n\n'
            '10. "constraints": array of observed constraints or notes.\n\n'
            '11. "suggested_dimensions": object with "length_m" and "width_m" — suggested plot dimensions in meters.\n\n'
            '12. "suggested_building_footprint": object with "length_m" and "width_m" — suggested building footprint.\n\n'
            '13. "setback_suggestions": object with "front", "rear", "left", "right" (numbers) — suggested setbacks in meters.\n\n'
            '14. "access_info": (object) {type: "servitude"|"road"|"other", description: "..."}\n\n'
            '15. "nearby_references": array of nearby land title reference numbers (e.g. "TF-32626/W")\n\n'
            "CRITICAL: Return ONLY valid JSON. No markdown, no code fences, no extra text. "
            "Numeric values must be numbers, not strings. "
            "If a field is not found, use null or empty array."
        )

    try:
        def call():
            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(role="user", parts=[
                        types.Part(text=prompt),
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_bytes)),
                    ])
                ],
            )

        logger.info("[analyze_plot_image] Sending plot image to Gemini for analysis")
        response = await asyncio.to_thread(call)

        text = response.candidates[0].content.parts[0].text
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("\n", 1)[0]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        if not isinstance(result, dict):
            logger.warning(f"[analyze_plot_image] Gemini returned a {type(result).__name__} instead of dict")
            result = {}

        logger.info(f"[analyze_plot_image] Analysis complete: terrain={result.get('terrain_type', 'unknown')}")
        return result

    except Exception as e:
        import traceback
        error_detail = f"[analyze_plot_image] Error: {type(e).__name__}: {e}"
        logger.error(error_detail)
        logger.error(traceback.format_exc())
        print(f"PLOT_ANALYSIS_ERROR: {error_detail}", flush=True)
        return {
            "plot_description": "",
            "terrain_type": "",
            "terrain_notes": "",
            "orientation_notes": "",
            "constraints": [],
            "suggested_dimensions": {},
            "suggested_building_footprint": {},
            "setback_suggestions": {},
            "image_type": "",
            "admin_info": None,
            "extracted_dimensions": None,
            "extracted_boundary": None,
            "extracted_gps": None,
            "access_info": None,
            "nearby_references": None,
            "error": f"Plot analysis failed: {type(e).__name__}: {str(e)}",
        }
