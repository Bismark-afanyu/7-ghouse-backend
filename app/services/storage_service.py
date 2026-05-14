import uuid
from datetime import timedelta


def _get_bucket():
    """Lazy import to avoid import-time Firebase init issues."""
    from app.core.firebase import bucket
    return bucket


async def upload_image(image_bytes: bytes, user_id: str, generation_id: str, index: int) -> dict:
    """
    Upload an image to Firebase Storage.
    Returns dict with 'url' and 'storage_path'.
    """
    bucket = _get_bucket()
    filename = f"{uuid.uuid4().hex}.png"
    storage_path = f"generations/{user_id}/{generation_id}/{filename}"

    blob = bucket.blob(storage_path)
    blob.upload_from_string(image_bytes, content_type="image/png")
    blob.make_public()

    return {
        "url": blob.public_url,
        "storage_path": storage_path,
    }
