from datetime import datetime, timezone
from typing import Optional


def _get_db():
    """Lazy import to avoid import-time Firebase init issues."""
    from app.db.firebase import db
    return db


async def save_generation(
    user_id: str,
    client_name: Optional[str],
    property_type: str,
    num_rooms: int,
    land_size: str,
    architectural_style: str,
    additional_preferences: Optional[str],
    prompt_used: str,
    images: list[dict],
) -> str:
    """Save a generation record to Firestore. Returns the document ID."""
    db = _get_db()
    doc_ref = db.collection("generations").document()
    doc_ref.set({
        "user_id": user_id,
        "client_name": client_name,
        "property_type": property_type,
        "num_rooms": num_rooms,
        "land_size": land_size,
        "architectural_style": architectural_style,
        "additional_preferences": additional_preferences,
        "prompt_used": prompt_used,
        "images": images,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_ref.id


async def get_generation(generation_id: str, user_id: str) -> Optional[dict]:
    """Get a single generation by ID, scoped to the user."""
    db = _get_db()
    doc = db.collection("generations").document(generation_id).get()
    if doc.exists:
        data = doc.to_dict()
        if data.get("user_id") == user_id:
            return {"id": doc.id, **data}
    return None


async def get_user_generations(user_id: str, limit: int = 20) -> list[dict]:
    """Get all generations for a user, most recent first."""
    db = _get_db()
    query = (
        db.collection("generations")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        images = data.get("images", [])
        results.append({
            "id": doc.id,
            "client_name": data.get("client_name"),
            "property_type": data.get("property_type", ""),
            "architectural_style": data.get("architectural_style", ""),
            "num_rooms": data.get("num_rooms", 0),
            "land_size": data.get("land_size", ""),
            "thumbnail_url": images[0]["url"] if images else None,
            "image_count": len(images),
            "created_at": data.get("created_at", ""),
        })
    return results
