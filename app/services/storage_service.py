import uuid
import asyncio
from fastapi import HTTPException
from app.db.firebase import bucket


def _upload_image_sync(image_bytes: bytes, blob_path: str) -> dict:
    blob = bucket.blob(blob_path)
    blob.upload_from_string(image_bytes, content_type="image/png")
    blob.make_public()
    return {
        "url": blob.public_url,
        "storage_path": blob_path,
    }


def _upload_file_sync(file_bytes: bytes, blob_path: str, content_type: str) -> dict:
    blob = bucket.blob(blob_path)
    blob.upload_from_string(file_bytes, content_type=content_type)
    blob.make_public()
    return {
        "url": blob.public_url,
        "storage_path": blob_path,
    }


def _delete_image_sync(storage_path: str) -> bool:
    try:
        blob = bucket.blob(storage_path)
        blob.delete()
        return True
    except Exception:
        return False


async def upload_image(image_bytes: bytes, user_id: str, generation_id: str, index: int) -> dict:
    if bucket is None:
        raise HTTPException(status_code=500, detail="Firebase Storage not initialized")

    filename = f"{uuid.uuid4().hex}.png"
    blob_path = f"generations/{user_id}/{generation_id}/{filename}"
    return await asyncio.to_thread(_upload_image_sync, image_bytes, blob_path)


async def upload_file(file_bytes: bytes, user_id: str, generation_id: str, filename: str, content_type: str) -> dict:
    if bucket is None:
        raise HTTPException(status_code=500, detail="Firebase Storage not initialized")

    blob_path = f"generations/{user_id}/{generation_id}/{filename}"
    return await asyncio.to_thread(_upload_file_sync, file_bytes, blob_path, content_type)


async def delete_image(storage_path: str) -> bool:
    if bucket is None:
        return False
    return await asyncio.to_thread(_delete_image_sync, storage_path)
