import httpx
import os
import base64
from typing import Optional


def build_prompt(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str] = None,
) -> str:
    """Construct a detailed prompt for the AI image generation service."""
    prompt = (
        f"A photorealistic exterior architectural rendering of a {architectural_style} style "
        f"{property_type} with {num_rooms} rooms, built on a {land_size} plot of land. "
        f"The image should show the full facade of the house from a slight angle, "
        f"with professional architectural photography lighting, landscaped surroundings, "
        f"blue sky with soft clouds, and high-end materials. "
        f"Ultra-detailed, 8K resolution, architectural visualization quality."
    )
    if additional_preferences:
        prompt += f" Additional details: {additional_preferences}."
    return prompt


async def generate_images(
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str] = None,
    num_images: int = 3,
) -> tuple[str, list[bytes]]:
    """
    Generate exterior house concept images using OpenAI DALL-E 3.
    Returns (prompt_used, list_of_image_bytes).
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    prompt = build_prompt(
        property_type, num_rooms, land_size, architectural_style, additional_preferences
    )

    if not api_key:
        # Return placeholder images for development/demo
        return prompt, await _generate_placeholder_images(num_images)

    images: list[bytes] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for _ in range(num_images):
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1792x1024",
                    "quality": "hd",
                    "response_format": "b64_json",
                },
            )
            response.raise_for_status()
            data = response.json()
            b64_data = data["data"][0]["b64_json"]
            images.append(base64.b64decode(b64_data))

    return prompt, images


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
