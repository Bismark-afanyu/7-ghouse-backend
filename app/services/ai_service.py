import httpx
import base64
import asyncio
import urllib.parse
from google import genai
from google.genai import types
from typing import Optional
from app.db.firebase import settings


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
    
    base_info = f"{architectural_style} style {property_type} with {num_rooms} rooms on a {land_size} plot."
    
    prompts = {
        "2d_blueprint": (
            f"A professional, industry-standard 2D architectural floor plan blueprint of a {base_info}. "
            f"Black and white technical drawing, clean lines, precise labels, dimension lines with measurements. "
            f"Shows a cohesive layout with a living room, bedroom (bed on right, windows in front), bathroom (bathtub on left, basin in front, toilet on right), and kitchen. "
            f"Best practices architectural documentation style."
        ),
        "3d_exterior": (
            f"A photorealistic high-end exterior architectural rendering of a {base_info}. "
            f"Front perspective view, professional lighting, landscaped surroundings, blue sky. "
            f"Exterior materials feature natural wood, textured plaster, and soft stone to match the interior wabi-sabi theme. Ultra-detailed, 8K resolution."
        ),
        "3d_topdown": (
            f"A realistic top-down interior render (bird's-eye view) of a {base_info} showing how the home would look in real life. "
            f"Keep all room positions accurate: living room, bedroom (bed on right), bathroom (bathtub on left, basin in front, toilet on right), kitchen, dining area, and entryway. "
            f"Redesign the entire space in a {wabi_sabi_style} Realistic proportions, soft shadows, ar 4:5."
        ),
        "interior_living": (
            f"Generate an interior image of the living room space on an eye level following faithfully to the top down reference. "
            f"Follow the top down reference for furniture placements. Style: {wabi_sabi_style} ar 4:5."
        ),
        "interior_bedroom": (
            f"Generate an interior image of the bedroom space on an eye level following faithfully to the top down reference. "
            f"Door on the left, windows in front, bed on the right. Follow the top down reference for furniture placements. Style: {wabi_sabi_style} ar 4:5."
        ),
        "interior_kitchen": (
            f"Generate a wide angle interior image of the kitchen space on an eye level following faithfully to the top down reference. "
            f"Open layout, island in the center, seamless integration with the dining area. Style: {wabi_sabi_style} ar 4:5."
        ),
        "interior_bathroom": (
            f"Generate a wide angle interior image of the bathroom space on an eye level following faithfully to the top down reference. "
            f"Above the bathtub should have a shower head. Bathtub is on the left, basin is in front, toilet bowl on right and there is a cabinet with plant on top on the right wall near the door. "
            f"Follow the top down image placement! Style: {wabi_sabi_style} ar 4:5."
        ),
    }
    
    prompt = prompts.get(view_type, prompts["3d_exterior"])
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

    views_to_generate = [
        "2d_blueprint",
        "3d_exterior",
        "3d_topdown",
        "interior_living",
        "interior_bedroom",
        "interior_kitchen",
        "interior_bathroom",
    ]
    
    all_images: list[tuple[str, bytes]] = []
    reference_url = None
    master_prompt = ""

    # Human-friendly labels for the UI
    labels = {
        "2d_blueprint": "2D Blueprint",
        "3d_exterior": "3D Exterior",
        "3d_topdown": "Top-Down View",
        "interior_living": "Living Room",
        "interior_bedroom": "Master Bedroom",
        "interior_kitchen": "Kitchen",
        "interior_bathroom": "Bathroom",
    }

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
