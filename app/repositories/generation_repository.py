from datetime import datetime, timezone
from typing import Optional


def _get_db():
    from app.db.firebase import db
    return db


async def save_floor_plan_generation(
    user_id: str,
    images: list[dict],
    prompt_used: str,
    specification: dict,
    client_name: Optional[str] = None,
) -> str:
    db = _get_db()
    doc_ref = db.collection("generations").document()
    doc_ref.set({
        "user_id": user_id,
        "generation_type": "floor_plan",
        "client_name": client_name,
        "property_type": "Floor Plan",
        "num_rooms": specification.get("num_bedrooms", 0),
        "land_size": f"{specification.get('gross_area', '0')} m²",
        "architectural_style": "N/A",
        "region": specification.get("region", "Center"),
        "construction_standard": "Standard Modern",
        "additional_preferences": None,
        "prompt_used": prompt_used,
        "images": images,
        "floor_plan_spec": specification,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_ref.id


async def save_generation(
    user_id: str,
    client_name: Optional[str] = None,
    house_style: str = "",
    gross_area: str = "",
    is_multi_story: bool = False,
    num_stories: Optional[int] = None,
    num_bedrooms: int = 0,
    num_bathrooms: float = 0,
    roof_type: str = "",
    foundation: str = "",
    num_garages: int = 0,
    outdoor_spaces: Optional[list[str]] = None,
    overall_layout: str = "",
    kitchen_type: str = "",
    key_rooms: Optional[list[str]] = None,
    region: str = "Center",
    additional_preferences: Optional[str] = None,
    prompt_used: str = "",
    images: Optional[list[dict]] = None,
) -> str:
    db = _get_db()
    doc_ref = db.collection("generations").document()
    doc_ref.set({
        "user_id": user_id,
        "generation_type": "house_plan",
        "client_name": client_name,
        "house_style": house_style,
        "gross_area": gross_area,
        "is_multi_story": is_multi_story,
        "num_stories": num_stories,
        "num_bedrooms": num_bedrooms,
        "num_bathrooms": num_bathrooms,
        "roof_type": roof_type,
        "foundation": foundation,
        "num_garages": num_garages,
        "outdoor_spaces": outdoor_spaces or [],
        "overall_layout": overall_layout,
        "kitchen_type": kitchen_type,
        "key_rooms": key_rooms or [],
        "region": region or "Center",
        "additional_preferences": additional_preferences,
        "prompt_used": prompt_used,
        "images": images or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_ref.id


async def get_generation(generation_id: str, user_id: str, is_admin: bool = False) -> Optional[dict]:
    db = _get_db()
    doc = db.collection("generations").document(generation_id).get()
    if doc.exists:
        data = doc.to_dict()
        if is_admin or data.get("user_id") == user_id:
            return {"id": doc.id, **data}
    return None


async def get_user_generations(user_id: str, limit: int = 20) -> list[dict]:
    db = _get_db()
    query = (
        db.collection("generations")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )
    return await _execute_generation_query(query)


async def list_all_generations(limit: int = 50) -> list[dict]:
    db = _get_db()
    query = (
        db.collection("generations")
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )
    return await _execute_generation_query(query)


async def _execute_generation_query(query) -> list[dict]:
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        images = data.get("images", [])
        generation_type = data.get("generation_type", "house_plan")

        if generation_type == "floor_plan":
            fp_spec = data.get("floor_plan_spec", {})
            gross_area = fp_spec.get("gross_area", data.get("land_size", ""))
            num_bedrooms = fp_spec.get("num_bedrooms", data.get("num_rooms", 0))
        else:
            gross_area = data.get("gross_area", "")
            num_bedrooms = data.get("num_bedrooms", 0)

        results.append({
            "id": doc.id,
            "user_id": data.get("user_id"),
            "generation_type": generation_type,
            "client_name": data.get("client_name"),
            "house_style": data.get("house_style", ""),
            "gross_area": gross_area,
            "num_bedrooms": num_bedrooms,
            "region": data.get("region", "Center"),
            "thumbnail_url": images[0]["url"] if images else None,
            "image_count": len(images),
            "created_at": data.get("created_at", ""),
        })
    return results


async def update_generation(generation_id: str, user_id: str, updates: dict, is_admin: bool = False) -> bool:
    db = _get_db()
    doc_ref = db.collection("generations").document(generation_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    
    data = doc.to_dict()
    if not is_admin and data.get("user_id") != user_id:
        return False
    
    allowed_updates = {}
    if "client_name" in updates:
        allowed_updates["client_name"] = updates["client_name"]
        
    if allowed_updates:
        doc_ref.update(allowed_updates)
    return True


async def set_share_token(generation_id: str, user_id: str, is_admin: bool = False) -> Optional[str]:
    db = _get_db()
    doc_ref = db.collection("generations").document(generation_id)
    doc = doc_ref.get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    if not is_admin and data.get("user_id") != user_id:
        return None

    import uuid
    share_token = data.get("share_token") or uuid.uuid4().hex
    if not data.get("share_token"):
        doc_ref.update({"share_token": share_token})
    return share_token


async def get_generation_by_share_token(share_token: str) -> Optional[dict]:
    db = _get_db()
    docs = db.collection("generations").where("share_token", "==", share_token).limit(1).stream()
    for doc in docs:
        data = doc.to_dict()
        return {"id": doc.id, **data}
    return None


async def delete_generation(generation_id: str, user_id: str, is_admin: bool = False) -> bool:
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
