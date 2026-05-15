import httpx
import base64
import asyncio
import urllib.parse
from google import genai
from google.genai import types
from typing import Optional
from app.db.firebase import settings


def is_multi_story(property_type: str) -> bool:
    """Determine if a property type typically has multiple stories."""
    multi_story_types = ["Duplex", "Townhouse", "Mansion", "Apartment Building"]
    return property_type in multi_story_types


def get_views_to_generate(property_type: str) -> list[str]:
    """Dynamically determine the list of views to generate based on property type."""
    views = [
        "composite_presentation",
        "exterior_front",
        "exterior_angled",
        "exterior_rear",
        "2d_blueprint_ground",
    ]
    
    if is_multi_story(property_type):
        views.append("2d_blueprint_upper")
    
    views.extend([
        "3d_topdown_ground",
    ])
    
    if is_multi_story(property_type):
        views.append("3d_topdown_upper")
        
    views.extend([
        "interior_living",
        "interior_bedroom",
        "interior_kitchen",
        "interior_bathroom",
    ])
    return views


def get_view_labels() -> dict[str, str]:
    """Return human-friendly labels for all possible view types."""
    return {
        "composite_presentation": "Presentation Suite",
        "exterior_front": "Front View",
        "exterior_angled": "Angled View",
        "exterior_rear": "Rear View",
        "2d_blueprint_ground": "2D Plan (Ground)",
        "2d_blueprint_upper": "2D Plan (Upper)",
        "3d_topdown_ground": "3D Plan (Ground)",
        "3d_topdown_upper": "3D Plan (Upper)",
        "interior_living": "Living Room",
        "interior_bedroom": "Master Bedroom",
        "interior_kitchen": "Kitchen",
        "interior_bathroom": "Bathroom",
    }


def build_prompt(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    view_type: str = "3d_exterior",
    additional_preferences: Optional[str] = None,
) -> str:
    """Construct a highly detailed prompt enforcing a cohesive, premium warm wabi-sabi style and layout consistency."""
    
    # The universal style guide based on user requirements
    wabi_sabi_style = (
        "warm wabi-sabi style. Use light natural wood, textured plaster or limewash walls, soft stone surfaces, linen fabrics, "
        "and earthy tones like beige, sand, taupe, and muted brown. Keep furniture minimal, low-profile, and organic in shape. "
        "Add subtle imperfections, handmade decor, ceramics, and light greenery for a lived-in natural feel. "
        "Ensure the layout feels calm, uncluttered, and balanced. Use soft natural lighting, as if daylight is coming through the windows. "
        "Maintain a clean, premium interior design look with photorealistic materials and textures, high detail, interior design visualization quality, no text, no UI elements."
    )
    
    # Detailed Architectural Anchor Points - These force the AI to keep the same 'DNA'
    # We use very specific descriptors that the model can easily replicate across views
    architectural_dna = (
        f"This specific {property_type} has a distinctive modern geometry: "
        "A flat-roofed structure with a cantilevered second floor that overhangs a stone-paved terrace. "
        "The facade is a precise mix of vertical light-oak wood slats, smooth matte-white plaster, "
        "and oversized charcoal-framed floor-to-ceiling windows. "
        "A floating black metal staircase is visible through the main glass entry. "
        "The landscaping features drought-resistant grasses and soft perimeter up-lighting."
    )
    
    # Master Design Seed - Enforcing structural consistency across all prompts
    master_seed = (
        f"A cohesive {architectural_style} {property_type}. "
        f"{architectural_dna} "
        "Every view must show the EXACT SAME building materials, colors, and structural geometry. "
        "Consistency is mandatory."
    )
    
    base_info = f"{architectural_style} style {property_type} with {num_rooms} rooms on a {land_size} plot."
    
    prompts = {
        "composite_presentation": (
            f"An industry-standard architectural presentation board of a {base_info}. "
            "Split-screen layout. TOP HALF: A photorealistic high-end 3D exterior rendering of the house with professional lighting and landscaping. "
            "BOTTOM HALF: A detailed 3D top-down isometric floor plan cutaway of the EXACT SAME house, showing the interior furniture and layout perfectly matching the exterior structure. "
            f"Style: {wabi_sabi_style} 8K resolution, architectural visualization masterpiece."
        ),
        "exterior_front": (
            f"A photorealistic high-end exterior architectural rendering of a {base_info}. "
            "FRONT ELEVATION perspective view, eye-level, professional lighting, landscaped surroundings, blue sky. "
            f"{master_seed} Ultra-detailed, 8K resolution."
        ),
        "exterior_angled": (
            f"A photorealistic high-end exterior architectural rendering of a {base_info}. "
            "ANGLED STREET PERSPECTIVE view (45-degree angle), showing the depth and side of the property. "
            f"{master_seed} Professional lighting, lush landscaping, 8K resolution."
        ),
        "exterior_rear": (
            f"A photorealistic high-end exterior architectural rendering of a {base_info}. "
            "REAR ELEVATION view from the backyard, showing the back patio, pool, or garden area. "
            f"{master_seed} Soft evening lighting, architectural visualization quality."
        ),
        "2d_blueprint_ground": (
            f"A professional, industry-standard 2D architectural floor plan blueprint of the GROUND FLOOR of a {base_info}. "
            "Black and white technical drawing, clean lines, precise labels, dimension lines with measurements. "
            "Shows a cohesive layout matching the master design. Best practices architectural documentation style."
        ),
        "2d_blueprint_upper": (
            f"A professional, industry-standard 2D architectural floor plan blueprint of the UPPER/FIRST FLOOR of a {base_info}. "
            "Black and white technical drawing, clean lines, precise labels. Shows staircases and upper level rooms."
        ),
        "3d_topdown_ground": (
            f"A realistic 3D top-down interior render (bird's-eye view cutaway) of the GROUND FLOOR of a {base_info}. "
            f"{master_seed} {wabi_sabi_style} Realistic proportions, soft shadows, ar 4:5."
        ),
        "3d_topdown_upper": (
            f"A realistic 3D top-down interior render (bird's-eye view cutaway) of the UPPER FLOOR of a {base_info}. "
            f"{master_seed} {wabi_sabi_style} Consistent with ground floor structural walls."
        ),
        "interior_living": (
            f"Eye-level interior rendering of the living room following the {master_seed}. "
            f"Large windows, premium materials. Style: {wabi_sabi_style} ar 4:5."
        ),
        "interior_bedroom": (
            f"Eye-level interior rendering of the master bedroom following the {master_seed}. "
            f"Style: {wabi_sabi_style} ar 4:5."
        ),
        "interior_kitchen": (
            f"Eye-level wide-angle interior rendering of the kitchen and dining area following the {master_seed}. "
            f"Minimalist cabinetry, premium island. Style: {wabi_sabi_style} ar 4:5."
        ),
        "interior_bathroom": (
            f"Eye-level interior rendering of the luxury bathroom following the {master_seed}. "
            f"Spa-like atmosphere. Style: {wabi_sabi_style} ar 4:5."
        ),
    }
    
    prompt = prompts.get(view_type, prompts["exterior_front"])
    if additional_preferences:
        prompt += f" Special user requirements to integrate: {additional_preferences}."
    
    return prompt


async def generate_images(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str] = None,
    num_images: int = 1, # Not used in the new pro suite flow
) -> tuple[str, list[bytes]]:
    """
    Generate a full Pro Architectural Suite (2D Plan, 3D Front, Top-Down, and 4 Interiors).
    Returns (master_prompt, list_of_image_bytes).
    """
    api_key = settings.NANO_BANANA_API_KEY
    if not api_key:
        placeholder_bytes = await _generate_placeholder_images(7)
        placeholder_labels = ["2D Blueprint", "3D Exterior", "Top-Down View", "Living Room", "Master Bedroom", "Kitchen", "Bathroom"]
        return "Dev Mode Prompt", [(placeholder_labels[i], b) for i, b in enumerate(placeholder_bytes)]

    views_to_generate = get_views_to_generate(property_type)
    labels = get_view_labels()

    # Initialize the Gemini Client
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def generate_gemini_image(prompt_text: str) -> Optional[bytes]:
        try:
            # We wrap this in to_thread because the SDK is synchronous
            def call_imagen():
                # Explicitly calling the models.generate_images on the client
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
            print(f"❌ Gemini (New SDK) Error: {e}")
            return None

    for i, view in enumerate(views_to_generate):
        prompt = build_prompt(
            property_type, num_rooms, land_size, architectural_style, view, additional_preferences
        )
        if i == 0: master_prompt = prompt
        
        print(f"🎨 Generating {view} via Gemini (Imagen 4.0)...")
        img_bytes = await generate_gemini_image(prompt)
        
        if img_bytes:
            all_images.append((labels[view], img_bytes))
            print(f"✅ {view} completed!")
        else:
            print(f"❌ Gemini failed to generate {view}. No fallback configured.")

    return master_prompt, all_images


async def generate_images_stream(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str] = None,
):
    """
    Generate a full Pro Architectural Suite via async generator.
    Yields dicts representing progress or completed images.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        yield {"type": "progress", "message": "Development Mode: Mocking images..."}
        placeholder_bytes = await _generate_placeholder_images(7)
        placeholder_labels = ["2D Blueprint", "3D Exterior", "Top-Down View", "Living Room", "Master Bedroom", "Kitchen", "Bathroom"]
        yield {"type": "master_prompt", "prompt": "Dev Mode Prompt"}
        for i, b in enumerate(placeholder_bytes):
            yield {"type": "image", "label": placeholder_labels[i], "bytes": b}
        return

    views_to_generate = get_views_to_generate(property_type)
    labels = get_view_labels()
    
    # Generate a unified design seed to anchor visual identity across all views
    import random
    design_seed = random.randint(1, 1000000)
    
    # Send the initial list of views to the frontend so it can build the UI list
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
                        aspect_ratio="16:9",
                        seed=design_seed
                    )
                )

            response = await asyncio.to_thread(call_imagen)
            if response.generated_images:
                return response.generated_images[0].image.image_bytes
            return None
        except Exception as e:
            print(f"❌ Gemini (New SDK) Error: {e}")
            return None

    for i, view in enumerate(views_to_generate):
        prompt = build_prompt(
            property_type, num_rooms, land_size, architectural_style, view, additional_preferences
        )
        if i == 0: 
            yield {"type": "master_prompt", "prompt": prompt}
        
        yield {"type": "view_start", "view_key": view, "label": labels[view]}
        yield {"type": "progress", "message": f"🎨 Generating {labels[view]} via Gemini..."}
        
        img_bytes = await generate_gemini_image(prompt)
        
        if img_bytes:
            yield {"type": "view_complete", "view_key": view, "label": labels[view]}
            yield {"type": "image", "label": labels[view], "bytes": img_bytes}
        else:
            yield {"type": "view_error", "view_key": view, "label": labels[view]}
            yield {"type": "progress", "message": f"❌ Failed to generate {labels[view]}."}



async def generate_single_view(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    view_type: str,
    additional_preferences: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a single specific view (for the interactive workspace regenerate feature).
    """
    api_key = settings.NANO_BANANA_API_KEY
    if not api_key:
        placeholder_bytes = await _generate_placeholder_images(1)
        return placeholder_bytes[0] if placeholder_bytes else None

    # Initialize the Gemini Client
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

        print(f"🎨 Regenerating {view_type} via Gemini (Imagen 4.0)...")
        response = await asyncio.to_thread(call_imagen)
        
        if response.generated_images:
            print(f"✅ {view_type} regenerated successfully!")
            return response.generated_images[0].image.image_bytes
        
        return None
    except Exception as e:
        print(f"❌ Gemini (New SDK) Error regenerating {view_type}: {e}")
        return None


async def _generate_placeholder_images(num_images: int) -> list[bytes]:
    """Download placeholder architectural images for development."""
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
                # If placeholder download fails, create a minimal PNG
                images.append(_minimal_png())
    return images


def _minimal_png() -> bytes:
    """Return a tiny valid 1x1 PNG as absolute fallback."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
