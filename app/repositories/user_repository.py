from app.db.firebase import db
from datetime import datetime

async def get_user_role(uid: str) -> str:
    """Fetch user role from Firestore. Default to 'user' if not found."""
    if not db:
        return "user"
    
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        return doc.to_dict().get("role", "user")
    
    # If user doesn't exist in Firestore 'users' collection yet, create them with default role
    db.collection("users").document(uid).set({
        "role": "user",
        "created_at": datetime.utcnow()
    })
    return "user"

async def get_user_by_id(uid: str) -> dict:
    """Fetch a single user by UID."""
    if not db:
        return None
    
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        data = doc.to_dict()
        return {
            "uid": doc.id,
            "email": data.get("email"),
            "display_name": data.get("display_name"),
            "job_title": data.get("job_title"),
            "photo_url": data.get("photo_url"),
            "role": data.get("role", "user"),
            "created_at": data.get("created_at")
        }
    return None

async def list_users() -> list:
    """List all users in the system."""
    if not db:
        return []
    
    users = []
    docs = db.collection("users").stream()
    for doc in docs:
        data = doc.to_dict()
        users.append({
            "uid": doc.id,
            "email": data.get("email"),
            "display_name": data.get("display_name"),
            "job_title": data.get("job_title"),
            "photo_url": data.get("photo_url"),
            "role": data.get("role", "user"),
            "created_at": data.get("created_at")
        })
    return users

async def update_user(uid: str, data: dict):
    """Update a user's profile and role."""
    if not db:
        return
    data["updated_at"] = datetime.utcnow()
    db.collection("users").document(uid).update(data)

async def delete_user(uid: str):
    """Delete a user from Firestore and Firebase Auth."""
    from app.db.firebase import auth
    if not db:
        return
    
    # 1. Delete from Firestore
    db.collection("users").document(uid).delete()
    
    # 2. Delete from Firebase Auth
    try:
        auth.delete_user(uid)
    except Exception as e:
        print(f"Error deleting from Auth: {e}")
