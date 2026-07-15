import logging

import httpx

logger = logging.getLogger(__name__)

NOMINATOM_URL = "https://nominatim.openstreetmap.org/search"


async def geocode_location(name: str) -> tuple[float, float] | None:
    try:
        params = {
            "q": f"{name}, Cameroon",
            "format": "json",
            "limit": 1,
        }
        headers = {"User-Agent": "7G-House-Geocoder/1.0"}
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get(NOMINATOM_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lng = float(data[0]["lon"])
                return lat, lng
    except Exception as e:
        logger.warning(f"Geocoding failed for '{name}': {e}")
    return None
