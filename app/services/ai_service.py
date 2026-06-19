import httpx
import base64
import asyncio
import urllib.parse
from google import genai
from google.genai import types
from typing import Optional
from app.db.firebase import settings
from app.services.label_service import overlay_labels


def is_multi_story(property_type: str) -> bool:
    multi_story_types = ["Duplex", "Townhouse", "Mansion", "Apartment Building"]
    return property_type in multi_story_types


def get_views_to_generate(property_type: str, multi_story: bool = False, num_stories: int = 1) -> list[str]:
    views = [
        "elevations_composite",
        "exterior_3d_composite",
        "interior_living_composite",
        "master_suite_composite",
        "topdown_3d_view",
        "cross_section_view",
    ]
    if multi_story and num_stories >= 2:
        views.append("topdown_3d_ground_floor")
        views.append("topdown_3d_upper_floor")
    return views


def get_view_labels() -> dict[str, str]:
    return {
        "floor_plans_composite": "Floor Plans",
        "elevations_composite": "Elevations",
        "exterior_3d_composite": "3D Exterior",
        "interior_living_composite": "Living & Kitchen",
        "master_suite_composite": "Master Suite",
        "topdown_3d_view": "3D Top-Down View",
        "cross_section_view": "Cross-Section View",
        "topdown_3d_ground_floor": "Ground Floor (Top-Down)",
        "topdown_3d_upper_floor": "Upper Floor (Top-Down)",
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
    land_size: str,
    architectural_style: str,
    view_type: str = "3d_exterior",
    additional_preferences: Optional[str] = None,
    num_stories: int = 1,
    roof_type: str = "Flat",
) -> str:
    wabi_sabi_style = (
        "warm wabi-sabi style. Use light natural wood, textured plaster or limewash walls, soft stone surfaces, linen fabrics, "
        "and earthy tones like beige, sand, taupe, and muted brown. Keep furniture minimal, low-profile, and organic in shape. "
        "Add subtle imperfections, handmade decor, ceramics, and light greenery for a lived-in natural feel. "
        "Ensure the layout feels calm, uncluttered, and balanced. Use soft natural lighting, as if daylight is coming through the windows. "
        "Maintain a clean, premium interior design look with photorealistic materials and textures, high detail, interior design visualization quality, no text, no UI elements."
    )

    roof_desc = f"{roof_type.lower()}-roofed" if roof_type.lower() != "flat" else "flat-roofed"

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

    base_info = f"{architectural_style} style {property_type} with {num_rooms} rooms on a {land_size} plot."

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
            "Style: Clean fine black vector-style linework on a solid, pure white background. "
            "Zero color, zero gray fills, zero realistic rendering, zero shading or shadow gradients, zero paper textures, and zero blue grids. "
            "Precise thin black line drawings of rooms, wall thicknesses, door swing symbols, window cutouts, staircases, and simple furniture shapes. "
            "Do NOT render any text or labels. "
            "Professional architectural CAD/Revit export quality, minimal, high-contrast, clean blueprint lines."
        )
    else:
        floor_plans_prompt = (
            f"A professional architectural 2D floor plan drawing sheet for a {base_info}. "
            "A single clean floor plan showing the complete single-story layout in one sheet. "
            "Style: Clean fine black vector-style linework on a solid, pure white background. "
            "Zero color, zero gray fills, zero realistic rendering, zero shading or shadow gradients, zero paper textures, and zero blue grids. "
            "Precise thin black line drawings of rooms, wall thicknesses, door swing symbols, window cutouts, and simple furniture shapes. "
            "Do NOT render any text or labels. "
            "Professional architectural CAD/Revit export quality, minimal, high-contrast, clean blueprint lines."
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

    cross_section_prompt = (
        f"A professional architectural cross-section rendering through a {story_text} {property_type.lower()} "
        f"with a {roof_type.lower()} roof on a {land_size} plot. "
        f"{story_info} "
        f"The building has a {roof_type.lower()} roof structure clearly visible in the section cut. "
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
        "cross_section_view": cross_section_prompt,
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
    }

    prompt = prompts.get(view_type, prompts["exterior_3d_composite"])
    if additional_preferences:
        prompt += f" Special user requirements to integrate: {additional_preferences}."

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
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
) -> tuple[str, list[bytes]]:
    api_key = settings.NANO_BANANA_API_KEY
    if not api_key:
        placeholder_bytes = await _generate_placeholder_images(7)
        placeholder_labels = ["2D Blueprint", "3D Exterior", "Top-Down View", "Living Room", "Master Bedroom", "Kitchen", "Bathroom"]
        return "Dev Mode Prompt", [(placeholder_labels[i], b) for i, b in enumerate(placeholder_bytes)]

    views_to_generate = get_views_to_generate(property_type, multi_story=is_multi_story, num_stories=num_stories)
    labels = get_view_labels()
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def generate_gemini_image(prompt_text: str) -> Optional[bytes]:
        try:
            def call_imagen():
                return client.models.generate_images(
                    model="imagen-4.0-generate-001",
                    prompt=prompt_text,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/png",
                        aspect_ratio="16:9"
                    )
                )
            response = await asyncio.to_thread(call_imagen)
            if response.generated_images:
                return response.generated_images[0].image.image_bytes
            return None
        except Exception as e:
            print(f"Gemini Error: {e}")
            return None

    all_images = []
    master_prompt = ""
    for i, view in enumerate(views_to_generate):
        prompt = build_prompt(
            property_type, num_rooms, land_size, architectural_style, view,
            additional_preferences, num_stories=num_stories,
        )
        if i == 0: master_prompt = prompt
        print(f"Generating {view} via Gemini (Imagen 4.0)...")
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
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
):
    if cancel_event and cancel_event.is_set():
        yield {"type": "cancelled"}
        return

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        yield {"type": "progress", "progress_type": "dev_mode"}
        placeholder_bytes = await _generate_placeholder_images(7)
        placeholder_labels = ["2D Blueprint", "3D Exterior", "Top-Down View", "Living Room", "Master Bedroom", "Kitchen", "Bathroom"]
        yield {"type": "master_prompt", "prompt": "Dev Mode Prompt"}
        for i, b in enumerate(placeholder_bytes):
            if cancel_event and cancel_event.is_set():
                yield {"type": "cancelled"}
                return
            yield {"type": "image", "label": placeholder_labels[i], "bytes": b}
        return

    views_to_generate = get_views_to_generate(property_type, multi_story=is_multi_story, num_stories=num_stories)
    labels = get_view_labels()

    view_list = [{"key": v, "label": labels[v]} for v in views_to_generate]
    yield {"type": "view_list", "views": view_list}

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        yield {"type": "error", "message": f"Failed to initialize AI client: {str(e)}"}
        return

    async def generate_gemini_image(prompt_text: str) -> Optional[bytes]:
        try:
            def call_imagen():
                return client.models.generate_images(
                    model="imagen-4.0-generate-001",
                    prompt=prompt_text,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/png",
                        aspect_ratio="16:9"
                    )
                )
            response = await asyncio.to_thread(call_imagen)
            if response.generated_images:
                return response.generated_images[0].image.image_bytes
            return None
        except Exception as e:
            print(f"Gemini Error: {e}")
            return None

    for i, view in enumerate(views_to_generate):
        if cancel_event and cancel_event.is_set():
            yield {"type": "cancelled"}
            return

        prompt = build_prompt(
            property_type, num_rooms, land_size, architectural_style, view,
            additional_preferences, num_stories=num_stories, roof_type=roof_type,
        )
        if i == 0:
            yield {"type": "master_prompt", "prompt": prompt}

        yield {"type": "view_start", "view_key": view, "label": labels[view]}
        yield {"type": "progress", "progress_type": "generating", "label": labels[view]}

        img_bytes = await generate_gemini_image(prompt)

        if cancel_event and cancel_event.is_set():
            yield {"type": "cancelled"}
            return

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
            yield {"type": "view_complete", "view_key": view, "label": labels[view]}
            yield {"type": "image", "label": labels[view], "bytes": labeled_bytes}
        else:
            yield {"type": "view_error", "view_key": view, "label": labels[view]}
            yield {"type": "progress", "message": f"Failed to generate {labels[view]}."}



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
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
) -> Optional[bytes]:
    api_key = settings.NANO_BANANA_API_KEY
    if not api_key:
        placeholder_bytes = await _generate_placeholder_images(1)
        return placeholder_bytes[0] if placeholder_bytes else None

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = build_prompt(
        property_type, num_rooms, land_size, architectural_style, view_type,
        additional_preferences, num_stories=num_stories, roof_type=roof_type,
    )

    try:
        def call_imagen():
            return client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                    aspect_ratio="16:9"
                )
            )

        print(f"Regenerating {view_type} via Gemini (Imagen 4.0)...")
        response = await asyncio.to_thread(call_imagen)

        if response.generated_images:
            print(f"{view_type} regenerated successfully!")
            img_bytes = response.generated_images[0].image.image_bytes
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


async def generate_floor_plan_image(
    prompt: str,
    view_type: str = "floor_plan_main",
    overlay_language: str = "en",
) -> Optional[bytes]:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        placeholder = await _generate_placeholder_images(1)
        return placeholder[0] if placeholder else None

    client = genai.Client(api_key=api_key)

    try:
        def call_imagen():
            return client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                    aspect_ratio="16:9",
                ),
            )
        response = await asyncio.to_thread(call_imagen)
        if response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            return overlay_labels(img_bytes, view_type, language=overlay_language)
        return None
    except Exception as e:
        print(f"Floor plan generation error: {e}")
        try:
            fallback_prompt = f"Professional architectural floor plan: {prompt[:200]}"
            def call_fallback():
                return client.models.generate_images(
                    model="imagen-4.0-generate-001",
                    prompt=fallback_prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/png",
                        aspect_ratio="16:9",
                    ),
                )
            response = await asyncio.to_thread(call_fallback)
            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                return overlay_labels(img_bytes, view_type, language=overlay_language)
        except Exception as e2:
            print(f"Floor plan fallback also failed: {e2}")
        return None
