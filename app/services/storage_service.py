import uuid
from fastapi import HTTPException
from app.db.firebase import bucket

async def upload_image(image_bytes: bytes, user_id: str, generation_id: str, index: int) -> dict:
    if bucket is None:
        raise HTTPException(status_code=500, detail="Firebase Storage not initialized")

    filename = f"{uuid.uuid4().hex}.png"
    blob_path = f"generations/{user_id}/{generation_id}/{filename}"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(image_bytes, content_type="image/png")
    blob.make_public()
    return {
        "url": blob.public_url,
        "storage_path": blob_path,
    }


async def delete_image(storage_path: str) -> bool:
    if bucket is None:
        return False
    try:
        blob = bucket.blob(storage_path)
        blob.delete()
        return True
    except Exception:
        return False
