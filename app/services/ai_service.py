import httpx
import base64
import asyncio
import urllib.parse
from google import genai
from google.genai import types
from typing import Optional
from app.db.firebase import settings


def is_multi_story(property_type: str) -> bool:
    multi_story_types = ["Duplex", "Townhouse", "Mansion", "Apartment Building"]
    return property_type in multi_story_types


def get_views_to_generate(property_type: str, multi_story: bool = False) -> list[str]:
    return [
        "floor_plans_composite",
        "elevations_composite",
        "exterior_3d_composite",
        "interior_living_composite",
        "master_suite_composite",
    ]


def get_view_labels() -> dict[str, str]:
    return {
        "floor_plans_composite": "Floor Plans",
        "elevations_composite": "Elevations",
        "exterior_3d_composite": "3D Exterior",
        "interior_living_composite": "Living & Kitchen",
        "master_suite_composite": "Master Suite",
    }


def build_prompt(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    view_type: str = "3d_exterior",
    additional_preferences: Optional[str] = None,
) -> str:
    wabi_sabi_style = (
        "warm wabi-sabi style. Use light natural wood, textured plaster or limewash walls, soft stone surfaces, linen fabrics, "
        "and earthy tones like beige, sand, taupe, and muted brown. Keep furniture minimal, low-profile, and organic in shape. "
        "Add subtle imperfections, handmade decor, ceramics, and light greenery for a lived-in natural feel. "
        "Ensure the layout feels calm, uncluttered, and balanced. Use soft natural lighting, as if daylight is coming through the windows. "
        "Maintain a clean, premium interior design look with photorealistic materials and textures, high detail, interior design visualization quality, no text, no UI elements."
    )
    
    architectural_dna = (
        f"This specific {property_type} has a distinctive modern geometry: "
        "A flat-roofed structure with a cantilevered second floor that overhangs a stone-paved terrace. "
        "The facade is a precise mix of vertical light-oak wood slats, smooth matte-white plaster, "
        "and oversized charcoal-framed floor-to-ceiling windows. "
        "A floating black metal staircase is visible through the main glass entry. "
        "The landscaping features drought-resistant grasses and soft perimeter up-lighting."
    )
    
    master_seed = (
        f"A cohesive {architectural_style} {property_type}. "
        f"{architectural_dna} "
        "Every view must show the EXACT SAME building materials, colors, and structural geometry. "
        "Consistency is mandatory."
    )
    
    base_info = f"{architectural_style} style {property_type} with {num_rooms} rooms on a {land_size} plot."
    
    prompts = {
        "floor_plans_composite": (
            f"A professional architectural floor plan sheet for a {base_info}. "
            "Composite layout showing ALL floor plans in one clean architectural drawing. "
            "Include BASEMENT (if applicable), GROUND FLOOR, and UPPER FLOOR plans arranged vertically with labels. "
            "Black and white technical blueprint style, clean lines, precise room labels with names, "
            "dimension lines with measurements, door and window symbols, staircase indicators. "
            "Professional architectural documentation standard, high contrast, no color, no rendering."
        ),
        "elevations_composite": (
            f"A professional architectural elevation sheet for a {base_info}. "
            "Composite layout showing ALL FOUR exterior elevations in one clean architectural drawing: "
            "FRONT ELEVATION (top-left), REAR ELEVATION (top-right), "
            "LEFT SIDE ELEVATION (bottom-left), RIGHT SIDE ELEVATION (bottom-right). "
            "Each elevation must show the exact same building with consistent roofline, proportions, and materials. "
            "Black and white technical elevation style, clean lines, height annotations, ground line, "
            f"roof profile, window and door placements. {master_seed} Architectural documentation standard."
        ),
        "exterior_3d_composite": (
            f"A premium photorealistic 3D exterior rendering composite of a {base_info}. "
            "Split-screen layout. LEFT HALF: FRONT exterior view of the house — eye-level perspective showing the main entrance, "
            "landscaped front yard, facade details, and entrance. "
            "RIGHT HALF: REAR exterior view — showing the back patio, terrace, garden, and rear facade. "
            f"{master_seed} Professional architectural visualization, dramatic golden hour lighting, "
            "vibrant greens, blue sky, 8K resolution, ultra-detailed materials and textures."
        ),
        "interior_living_composite": (
            f"Split-screen interior rendering composite of a {base_info}. "
            "LEFT HALF: LIVING ROOM — eye-level view showing the main seating area, large windows, "
            "coffee table, and natural light flooding the space. "
            "RIGHT HALF: KITCHEN & DINING — wide-angle view showing the kitchen island, cabinetry, "
            f"dining table, and adjacent breakfast area. "
            f"Style: {wabi_sabi_style} Both halves must show the exact same material palette and design language."
        ),
        "master_suite_composite": (
            f"Split-screen interior rendering composite of a {base_info}. "
            "LEFT HALF: MASTER BEDROOM — eye-level view showing the bed,床头柜, large windows, "
            "walk-in closet entrance, and soft natural lighting. "
            "RIGHT HALF: LUXURY BATHROOM — showing the double vanity, freestanding bathtub, "
            f"glass shower, and premium tilework. "
            f"Style: {wabi_sabi_style} Spa-like atmosphere. Both halves must feel like the same cohesive suite."
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
) -> tuple[str, list[bytes]]:
    api_key = settings.NANO_BANANA_API_KEY
    if not api_key:
        placeholder_bytes = await _generate_placeholder_images(7)
        placeholder_labels = ["2D Blueprint", "3D Exterior", "Top-Down View", "Living Room", "Master Bedroom", "Kitchen", "Bathroom"]
        return "Dev Mode Prompt", [(placeholder_labels[i], b) for i, b in enumerate(placeholder_bytes)]

    views_to_generate = get_views_to_generate(property_type, multi_story=is_multi_story)
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
            property_type, num_rooms, land_size, architectural_style, view, additional_preferences
        )
        if i == 0: master_prompt = prompt
        print(f"Generating {view} via Gemini (Imagen 4.0)...")
        img_bytes = await generate_gemini_image(prompt)
        if img_bytes:
            all_images.append((labels[view], img_bytes))
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
):
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        yield {"type": "progress", "message": "Development Mode: Mocking images..."}
        placeholder_bytes = await _generate_placeholder_images(7)
        placeholder_labels = ["2D Blueprint", "3D Exterior", "Top-Down View", "Living Room", "Master Bedroom", "Kitchen", "Bathroom"]
        yield {"type": "master_prompt", "prompt": "Dev Mode Prompt"}
        for i, b in enumerate(placeholder_bytes):
            yield {"type": "image", "label": placeholder_labels[i], "bytes": b}
        return

    views_to_generate = get_views_to_generate(property_type, multi_story=is_multi_story)
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
        prompt = build_prompt(
            property_type, num_rooms, land_size, architectural_style, view, additional_preferences
        )
        if i == 0: 
            yield {"type": "master_prompt", "prompt": prompt}
        
        yield {"type": "view_start", "view_key": view, "label": labels[view]}
        yield {"type": "progress", "message": f"Generating {labels[view]} via Gemini..."}
        
        img_bytes = await generate_gemini_image(prompt)
        
        if img_bytes:
            yield {"type": "view_complete", "view_key": view, "label": labels[view]}
            yield {"type": "image", "label": labels[view], "bytes": img_bytes}
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
) -> Optional[bytes]:
    api_key = settings.NANO_BANANA_API_KEY
    if not api_key:
        placeholder_bytes = await _generate_placeholder_images(1)
        return placeholder_bytes[0] if placeholder_bytes else None

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = build_prompt(
        property_type, num_rooms, land_size, architectural_style, view_type, additional_preferences
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
            return response.generated_images[0].image.image_bytes
        
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


async def generate_floor_plan_image(prompt: str) -> Optional[bytes]:
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
            return response.generated_images[0].image.image_bytes
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
                return response.generated_images[0].image.image_bytes
        except Exception as e2:
            print(f"Floor plan fallback also failed: {e2}")
        return None
