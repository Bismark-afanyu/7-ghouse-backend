import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Literal

from app.core.auth_middleware import verify_token
from app.repositories.generation_repository import (
    get_generation,
    set_video_job_id,
    set_video_url,
    set_video_error,
)
from app.services.video_service import (
    build_external_walkthrough_movie,
    build_internal_walkthrough_movie,
    submit_veo_render,
    poll_veo_render,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["video"])


class GenerateVideoRequest(BaseModel):
    generation_id: str
    video_type: Literal["external", "internal"] = "external"
    project_name: str = ""


@router.post("/generate")
async def generate_video(request: GenerateVideoRequest, user=Depends(verify_token)):
    uid = user["uid"]
    generation = await get_generation(request.generation_id, uid)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found.")

    images = generation.get("images", [])
    if not images:
        raise HTTPException(status_code=400, detail="No images in this generation.")

    spec = generation.get("floor_plan_spec") or {}
    client_name = generation.get("client_name", "")

    if request.video_type == "external":
        img_url, prompt = build_external_walkthrough_movie(
            images=images,
            spec=spec,
            project_name=request.project_name or "Projet 7G House",
            client_name=client_name,
        )
    else:
        img_url, prompt = build_internal_walkthrough_movie(
            images=images,
            spec=spec,
            project_name=request.project_name or "Projet 7G House",
            client_name=client_name,
        )

    if not img_url:
        raise HTTPException(status_code=400, detail="No suitable image found for this video type.")

    try:
        operation_name = await submit_veo_render(img_url, prompt)
    except RuntimeError as e:
        if "Billing exhausted" in str(e):
            raise HTTPException(
                status_code=429,
                detail="Video generation quota exhausted. Recharge AI Studio credits."
            )
        raise HTTPException(status_code=502, detail=str(e))

    if not operation_name:
        raise HTTPException(status_code=502, detail="Failed to submit video render to Google Veo.")

    await set_video_job_id(request.generation_id, operation_name, request.video_type)

    logger.info(
        f"Veo job started for generation={request.generation_id} "
        f"type={request.video_type} operation={operation_name}"
    )

    return {"project_id": operation_name, "status": "processing", "video_type": request.video_type}


@router.get("/status")
async def video_status(
    generation_id: str = Query(...),
    video_type: Literal["external", "internal"] = Query("external"),
    user=Depends(verify_token),
):
    uid = user["uid"]
    generation = await get_generation(generation_id, uid)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found.")

    status_field = f"video_{video_type}_status"
    url_field = f"video_{video_type}_url"

    stored_status = generation.get(status_field, "")
    stored_url = generation.get(url_field, "")

    # Fast-path: already completed or failed
    if stored_status == "done" and stored_url:
        return {"status": "done", "url": stored_url, "video_type": video_type}

    if stored_status == "error":
        err_msg = generation.get(f"video_{video_type}_error", "") or "Video generation failed"
        return {"status": "error", "video_type": video_type, "message": err_msg}

    # Poll the Veo operation if we have a job ID
    if stored_status == "processing":
        job_id_field = f"video_{video_type}_project_id"
        operation_name = generation.get(job_id_field)

        if operation_name:
            result_status, video_url, error_msg = await poll_veo_render(
                operation_name=operation_name,
                generation_id=generation_id,
                video_type=video_type,
            )

            if result_status == "done" and video_url:
                for attempt in range(3):
                    saved = await set_video_url(generation_id, video_url, video_type)
                    if saved:
                        break
                    logger.warning(f"Failed to save video_{video_type}_url (attempt {attempt + 1}/3), retrying...")
                    await asyncio.sleep(1)
                if not saved:
                    logger.error(f"Failed to save video_{video_type}_url to Firestore for generation {generation_id} after 3 attempts")
                return {"status": "done", "url": video_url, "video_type": video_type}

            if result_status == "error":
                await set_video_error(generation_id, video_type, message=error_msg or "")
                return {"status": "error", "video_type": video_type, "message": error_msg or "Video generation failed"}

        # Still processing
        return {"status": "processing", "video_type": video_type}

    return {"status": "idle", "video_type": video_type}


@router.get("/proxy")
async def proxy_video(url: str = Query(...)):
    """Proxy video requests to bypass browser CORS restrictions on Firebase Storage."""
    from app.db.firebase import settings
    from starlette.responses import Response
    bucket = settings.FIREBASE_STORAGE_BUCKET
    gcs_name = bucket.replace(".firebasestorage.app", ".appspot.com")
    allowed_prefixes = [
        f"https://storage.googleapis.com/{bucket}/",
        f"https://storage.googleapis.com/{gcs_name}/",
        f"https://firebasestorage.googleapis.com/v0/b/{bucket}/",
        f"https://firebasestorage.googleapis.com/v0/b/{gcs_name}/",
    ]
    if not any(url.startswith(p) for p in allowed_prefixes):
        raise HTTPException(status_code=400, detail="Invalid video URL origin")

    import httpx
    headers = {"User-Agent": "7G-House-Proxy/1.0"}
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "video/mp4")
        return Response(content=resp.content, media_type=content_type)
