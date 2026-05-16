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
    client_id: Optional[str] = None,
) -> str:
    """Save a generation record to Firestore. Returns the document ID."""
    db = _get_db()
    doc_ref = db.collection("generations").document()
    doc_ref.set({
        "user_id": user_id,
        "client_name": client_name,
        "client_id": client_id,
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


async def get_generation(generation_id: str, user_id: str, is_admin: bool = False) -> Optional[dict]:
    """Get a single generation by ID. Scoped to user unless is_admin=True."""
    db = _get_db()
    doc = db.collection("generations").document(generation_id).get()
    if doc.exists:
        data = doc.to_dict()
        if is_admin or data.get("user_id") == user_id:
            return {"id": doc.id, **data}
    return None


async def get_user_generations(user_id: str, limit: int = 20) -> list[dict]:
    """Get all generations for a specific user."""
    db = _get_db()
    query = (
        db.collection("generations")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )
    return await _execute_generation_query(query)


async def list_all_generations(limit: int = 50) -> list[dict]:
    """Admin function: Get generations from all users."""
    db = _get_db()
    query = (
        db.collection("generations")
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )
    return await _execute_generation_query(query)


async def _execute_generation_query(query) -> list[dict]:
    """Helper to format firestore results."""
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        images = data.get("images", [])
        results.append({
            "id": doc.id,
            "user_id": data.get("user_id"),
            "client_name": data.get("client_name"),
            "client_id": data.get("client_id"),
            "property_type": data.get("property_type", ""),
            "architectural_style": data.get("architectural_style", ""),
            "num_rooms": data.get("num_rooms", 0),
            "land_size": data.get("land_size", ""),
            "thumbnail_url": images[0]["url"] if images else None,
            "image_count": len(images),
            "created_at": data.get("created_at", ""),
        })
    return results


async def update_generation(generation_id: str, user_id: str, updates: dict, is_admin: bool = False) -> bool:
    """Update a specific generation record."""
    db = _get_db()
    doc_ref = db.collection("generations").document(generation_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    
    data = doc.to_dict()
    if not is_admin and data.get("user_id") != user_id:
        return False
    
    # We only allow updating specific fields, e.g., client_name
    allowed_updates = {}
    if "client_name" in updates:
        allowed_updates["client_name"] = updates["client_name"]
        
    if allowed_updates:
        doc_ref.update(allowed_updates)
    return True


async def delete_generation(generation_id: str, user_id: str, is_admin: bool = False) -> bool:
    """Delete a specific generation record."""
    db = _get_db()
    doc_ref = db.collection("generations").document(generation_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    
    data = doc.to_dict()
    if not is_admin and data.get("user_id") != user_id:
        return False
    
    doc_ref.delete()
    return True
