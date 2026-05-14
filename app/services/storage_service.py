import os
import uuid
from pathlib import Path

# Local storage path relative to the project root
UPLOAD_DIR = Path("static/uploads")
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def ensure_upload_dir():
    if not UPLOAD_DIR.exists():
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

async def upload_image(image_bytes: bytes, user_id: str, generation_id: str, index: int) -> dict:
    """
    Save an image locally for development.
    Returns dict with 'url' and 'storage_path'.
    """
    ensure_upload_dir()
    
    filename = f"{uuid.uuid4().hex}.png"
    # Create user and generation specific subdirectories
    relative_path = f"{user_id}/{generation_id}/{filename}"
    file_path = UPLOAD_DIR / relative_path
    
    # Ensure subdirectories exist
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save bytes to file
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    
    # Return the URL and path
    return {
        "url": f"{BASE_URL}/static/uploads/{relative_path}",
        "storage_path": str(file_path),
    }
