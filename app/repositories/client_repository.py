from app.db.firebase import db
from google.cloud import firestore
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

COLLECTION_NAME = "clients"


async def create_client(user_id: str, client_data: dict) -> str:
    """Create a new client portfolio record."""
    doc_ref = db.collection(COLLECTION_NAME).document()
    
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": doc_ref.id,
        "user_id": user_id,
        "name": client_data.get("name"),
        "email": client_data.get("email"),
        "phone": client_data.get("phone"),
        "notes": client_data.get("notes"),
        "created_at": now,
        "updated_at": now,
    }
    
    doc_ref.set(data)
    return doc_ref.id


async def get_user_clients(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all clients for a specific user, ordered by name."""
    docs = (
        db.collection(COLLECTION_NAME)
        .where("user_id", "==", user_id)
        .order_by("name", direction=firestore.Query.ASCENDING)
        .stream()
    )
    
    return [doc.to_dict() for doc in docs]


async def get_client(client_id: str, user_id: str, is_admin: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieve a specific client."""
    doc_ref = db.collection(COLLECTION_NAME).document(client_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        return None
        
    data = doc.to_dict()
    if not is_admin and data.get("user_id") != user_id:
        return None
        
    return data


async def update_client(client_id: str, user_id: str, update_data: dict) -> bool:
    """Update an existing client."""
    doc_ref = db.collection(COLLECTION_NAME).document(client_id)
    doc = doc_ref.get()
    
    if not doc.exists or doc.to_dict().get("user_id") != user_id:
        return False
        
    # Filter out None values to only update provided fields
    clean_data = {k: v for k, v in update_data.items() if v is not None}
    if not clean_data:
        return True
        
    clean_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc_ref.update(clean_data)
    return True


async def delete_client(client_id: str, user_id: str) -> bool:
    """Delete a client."""
    doc_ref = db.collection(COLLECTION_NAME).document(client_id)
    doc = doc_ref.get()
    
    if not doc.exists or doc.to_dict().get("user_id") != user_id:
        return False
        
    doc_ref.delete()
    return True
