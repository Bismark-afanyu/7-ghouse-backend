from fastapi import APIRouter, Depends, HTTPException, status
from app.core.auth_middleware import verify_token, require_admin
from app.repositories import user_repository
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UserCreateRequest(BaseModel):
    email: str
    password: str
    display_name: str
    job_title: Optional[str] = None
    role: str = "user"

@router.get("/me")
async def get_me(user=Depends(verify_token)):
    """Get current user profile and role."""
    return user

@router.get("/", dependencies=[Depends(require_admin)])
async def get_all_users():
    """List all users (Admin only)."""
    return await user_repository.list_users()

@router.get("/{uid}", dependencies=[Depends(require_admin)])
async def get_user_by_id(uid: str):
    """Get a single user by UID (Admin only)."""
    user = await user_repository.get_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    role: Optional[str] = None

@router.put("/{uid}", dependencies=[Depends(require_admin)])
async def update_user(uid: str, request: UserUpdateRequest, current_user=Depends(verify_token)):
    """Update a user's details (Admin only)."""
    # Prevent self-demotion
    if uid == current_user["uid"] and request.role and request.role != "admin":
        raise HTTPException(status_code=400, detail="Admins cannot demote themselves.")
        
    update_data = {k: v for k, v in request.dict().items() if v is not None}
    await user_repository.update_user(uid, update_data)
    return {"message": "User updated successfully"}

@router.delete("/{uid}", dependencies=[Depends(require_admin)])
async def delete_user(uid: str, current_user=Depends(verify_token)):
    """Delete a user (Admin only)."""
    if uid == current_user["uid"]:
        raise HTTPException(status_code=400, detail="Admins cannot delete their own accounts.")
        
    await user_repository.delete_user(uid)
    return {"message": "User deleted successfully"}

@router.post("/", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_user(request: UserCreateRequest):
    """Create a new user (Admin only)."""
    from app.db.firebase import auth, db
    from datetime import datetime
    
    try:
        # 1. Create in Firebase Auth
        user_record = auth.create_user(
            email=request.email,
            password=request.password,
            display_name=request.display_name
        )
        
        # 2. Store role and profile in Firestore
        db.collection("users").document(user_record.uid).set({
            "email": request.email,
            "display_name": request.display_name,
            "job_title": request.job_title,
            "role": request.role,
            "created_at": datetime.utcnow()
        })
        
        # 3. Send Welcome Email
        from app.services.email_service import send_welcome_email
        send_welcome_email(request.email, request.display_name, request.password)
        
        return {"uid": user_record.uid, "message": "User created successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
