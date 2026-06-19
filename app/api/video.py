import os
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth_middleware import verify_token
from app.repositories.generation_repository import (
    get_generation,
)
from app.services.video_service import (
    build_walkthrough_movie,
    submit_render,
    get_render_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["video"])


class GenerateVideoRequest(BaseModel):
    generation_id: str
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

    video_request = build_walkthrough_movie(
        images=images,
        spec=spec,
        project_name=request.project_name or "Projet 7G House",
        client_name=client_name,
    )

    job_id = await submit_render(video_request)
    if not job_id:
        raise HTTPException(status_code=502, detail="Failed to submit video render.")

    from app.db.firebase import db
    if db:
        try:
            db.collection("generations").document(request.generation_id).update({
                "video_project_id": job_id,
                "video_status": "processing",
            })
        except Exception as e:
            logger.warning(f"Failed to save video_project_id: {e}")

    return {"project_id": job_id, "status": "processing"}


@router.get("/status")
async def video_status(generation_id: str, user=Depends(verify_token)):
    uid = user["uid"]
    generation = await get_generation(generation_id, uid)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found.")

    video_status = generation.get("video_status", "")
    video_url = generation.get("video_url", "")
    job_id = generation.get("video_project_id", "")

    if video_status == "done" and video_url:
        return {"status": "done", "url": video_url}

    if video_status == "error":
        return {"status": "error", "url": video_url}

    if not job_id:
        return {"status": "idle"}

    result = await get_render_status(job_id)
    new_status = result.get("status", "unknown")

    if new_status == "done" and result.get("url"):
        from app.db.firebase import db
        if db:
            try:
                db.collection("generations").document(generation_id).update({
                    "video_status": "done",
                    "video_url": result["url"],
                })
            except Exception as e:
                logger.warning(f"Failed to save video_url: {e}")
        return {"status": "done", "url": result["url"]}

    if new_status == "error":
        from app.db.firebase import db
        if db:
            try:
                db.collection("generations").document(generation_id).update({
                    "video_status": "error",
                })
            except Exception as e:
                logger.warning(f"Failed to save video_error: {e}")
        return {"status": "error", "message": result.get("message", "Video generation failed")}

    return {"status": "processing"}
