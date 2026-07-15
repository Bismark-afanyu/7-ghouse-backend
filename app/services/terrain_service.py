import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TerrainInfo:
    elevation_m: float
    slope_category: str
    terrain_type: str
    foundation_recommendation: str
    terrain_notes: str

_ELEVATION_API = "https://api.open-meteo.com/v1/elevation"

_SLOPE_MAP: dict[str, dict] = {
    "flat": {
        "max_elevation": 100,
        "slope": "flat",
        "terrain": "Flat or gently undulating",
        "foundation": "Standard slab-on-grade foundation suitable. Minimal earthwork required.",
    },
    "gentle": {
        "max_elevation": 300,
        "slope": "gentle",
        "terrain": "Gently sloping terrain",
        "foundation": "Cut-and-fill foundation with stepped slab. Moderate earthwork required.",
    },
    "moderate": {
        "max_elevation": 700,
        "slope": "moderate",
        "terrain": "Moderately sloped or hilly terrain",
        "foundation": "Stepped foundation with retaining walls. Significant earthwork and drainage required.",
    },
    "steep": {
        "max_elevation": 99999,
        "slope": "steep",
        "terrain": "Steep or mountainous terrain",
        "foundation": "Pile or deep foundation with extensive retaining walls. Terracing and slope stabilization required.",
    },
}

_REGION_ELEVATION_MAP: dict[str, str] = {
    "Littoral": "Coastal plain, low elevation (0-50m). Flat terrain with clay/waterlogged soil.",
    "Centre": "Plateau, moderate elevation (600-800m). Sloped/rolling terrain with rocky soil.",
    "West": "Highlands, high elevation (1000-2000m). Steep terrain with volcanic soil.",
    "North": "Sahel plains, low-moderate elevation (200-500m). Flat to gently undulating arid terrain.",
    "Adamaoua": "Highland savannah, moderate-high elevation (800-1100m). Rolling plateau terrain.",
    "North-West": "Highlands, high elevation (1000-2500m). Steep mountainous terrain.",
    "South": "Rainforest, low elevation (0-200m). Flat to gently rolling forested terrain.",
    "East": "Forest-savannah transition, low-moderate elevation (300-600m). Mixed flat and rolling terrain.",
    "Far North": "Sahel, low elevation (200-400m). Flat hot arid terrain.",
    "South-West": "Coastal/volcanic, low-high elevation (0-1000m). Variable coastal and volcanic terrain.",
}


async def get_terrain_data(
    latitude: float,
    longitude: float,
    region: str = "",
) -> TerrainInfo:
    try:
        elevation = await _fetch_elevation(latitude, longitude)
        return _classify_terrain(elevation, region)
    except Exception as e:
        logger.warning(f"Elevation API failed: {e}. Falling back to region data.")
        return _region_fallback(region)


async def _fetch_elevation(latitude: float, longitude: float) -> float:
    import httpx

    apis = [
        (f"{_ELEVATION_API}?latitude={latitude}&longitude={longitude}", "open_meteo"),
        (f"https://api.open-elevation.com/api/v1/lookup?locations={latitude},{longitude}", "open_elevation"),
        (f"https://api.opentopodata.org/v1/test-dataset?locations={latitude},{longitude}", "open_topo"),
    ]

    for url, name in apis:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                if name == "open_meteo":
                    elevations = data.get("elevation", [])
                    if elevations:
                        return float(elevations[0])
                elif name == "open_elevation":
                    results = data.get("results", [])
                    if results:
                        return float(results[0].get("elevation", 0))
                elif name == "open_topo":
                    results = data.get("results", [])
                    if results:
                        return float(results[0].get("elevation", 0))
        except Exception as e:
            logger.debug(f"Elevation API {name} failed: {e}")
            continue

    raise RuntimeError("All elevation APIs failed")


def _classify_terrain(elevation: float, region: str) -> TerrainInfo:
    for grade, info in _SLOPE_MAP.items():
        if elevation < info["max_elevation"]:
            notes = f"Elevation: {elevation:.0f}m above sea level."
            if region:
                region_desc = _REGION_ELEVATION_MAP.get(region, "")
                notes += f" {region_desc}"

            return TerrainInfo(
                elevation_m=elevation,
                slope_category=info["slope"],
                terrain_type=info["terrain"],
                foundation_recommendation=info["foundation"],
                terrain_notes=notes.strip(),
            )

    return _region_fallback(region)


def _region_fallback(region: str) -> TerrainInfo:
    region_desc = _REGION_ELEVATION_MAP.get(region, "")
    if not region_desc:
        return TerrainInfo(
            elevation_m=0.0,
            slope_category="flat",
            terrain_type="Flat terrain",
            foundation_recommendation="Standard slab-on-grade foundation.",
            terrain_notes="No elevation data available. Assuming flat terrain.",
        )

    if "steep" in region_desc.lower() or "mountainous" in region_desc.lower():
        slope = "steep"
        foundation = "Pile or deep foundation with retaining walls. Terracing and slope stabilization required."
    elif "sloped" in region_desc.lower() or "rolling" in region_desc.lower() or "hilly" in region_desc.lower():
        slope = "moderate"
        foundation = "Stepped foundation with retaining walls. Significant earthwork and drainage required."
    elif "gently" in region_desc.lower():
        slope = "gentle"
        foundation = "Cut-and-fill foundation with stepped slab. Moderate earthwork required."
    else:
        slope = "flat"
        foundation = "Standard slab-on-grade foundation suitable. Minimal earthwork required."

    return TerrainInfo(
        elevation_m=0.0,
        slope_category=slope,
        terrain_type=region_desc.split(".")[0] if region_desc else "Unknown terrain",
        foundation_recommendation=foundation,
        terrain_notes=region_desc,
    )
