from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from app.core.auth_middleware import verify_token
from app.schemas.generation import GenerationRequest, GenerationResponse, GenerationHistoryItem, WorkspaceResponse, SingleRoomRequest, SaveGenerationRequest, GenerationImage, GenerationUpdate
from app.services import ai_service, storage_service
from app.repositories import generation_repository as db_service
import uuid

router = APIRouter()


import json

@router.post("/generate")
async def generate_design(request: GenerationRequest, user=Depends(verify_token)):
    """Generate initial AI exterior house design concepts with real-time SSE progress."""
    user_id = user["uid"]

    async def event_generator():
        try:
            # Create a temporary generation ID for storage paths
            generation_id = uuid.uuid4().hex
            uploaded_images = []
            prompt_used = ""
            idx = 0

            # Yield an initial progress event
            yield f"data: {json.dumps({'status': 'progress', 'message': 'Initializing AI engines...'})}\n\n"

            async for event in ai_service.generate_images_stream(
                property_type=request.property_type,
                num_rooms=request.num_rooms,
                land_size=request.land_size,
                architectural_style=request.architectural_style,
                additional_preferences=request.additional_preferences,
            ):
                if event["type"] in ["progress", "view_list", "view_start", "view_complete", "view_error", "error"]:
                    # Send structured event to the client
                    yield f"data: {json.dumps({'status': event['type'], **event})}\n\n"
                    if event["type"] == "error":
                        return # Stop stream on fatal error
                
                elif event["type"] == "master_prompt":
                    prompt_used = event["prompt"]
                
                elif event["type"] == "image":
                    # Upload the image chunk to cloud storage
                    label_str = event["label"]
                    yield f"data: {json.dumps({'status': 'progress', 'message': f'Uploading {label_str}...'})}\n\n"
                    
                    img_data = await storage_service.upload_image(
                        image_bytes=event["bytes"],
                        user_id=user_id,
                        generation_id=generation_id,
                        index=idx,
                    )
                    idx += 1
                    
                    uploaded_images.append({
                        "url": img_data["url"],
                        "storage_path": img_data["storage_path"],
                        "label": event["label"]
                    })
                    
            # Final yield with the complete workspace payload
            workspace_payload = {
                "generation_id": generation_id,
                "images": uploaded_images,
                "prompt_used": prompt_used,
            }
            yield f"data: {json.dumps({'status': 'complete', 'workspace': workspace_payload})}\n\n"

        except Exception as e:
            # We must yield an error event since the HTTP status is already 200 OK (stream started)
            error_payload = {"status": "error", "detail": f"Generation failed: {str(e)}"}
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")



@router.post("/generate/room", response_model=GenerationImage)
async def generate_single_room(request: SingleRoomRequest, user=Depends(verify_token)):
    """Regenerate a single specific room."""
    user_id = user["uid"]
    
    try:
        img_bytes = await ai_service.generate_single_view(
            property_type=request.property_type,
            num_rooms=request.num_rooms,
            land_size=request.land_size,
            architectural_style=request.architectural_style,
            view_type=request.view_type,
            additional_preferences=request.additional_preferences,
        )
        
        if not img_bytes:
            raise Exception("AI failed to generate image.")

        # Upload the single image
        # Use a random index to avoid overwriting existing images if they keep regenerating
        random_idx = int(uuid.uuid4().int % 10000)
        img_data = await storage_service.upload_image(
            image_bytes=img_bytes,
            user_id=user_id,
            generation_id=request.generation_id,
            index=random_idx,
        )
        
        return GenerationImage(
            url=img_data["url"],
            storage_path=img_data["storage_path"]
        )
    except Exception as e:
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Room generation failed: {str(e)}",
        )


@router.post("/generation/save", response_model=GenerationResponse)
async def save_generation(request: SaveGenerationRequest, user=Depends(verify_token)):
    """Officially save an approved Workspace generation to the database."""
    user_id = user["uid"]
    
    try:
        # Convert Pydantic models to dicts for Firestore
        images_dict = [{"url": img.url, "storage_path": img.storage_path} for img in request.images]
        
        doc_id = await db_service.save_generation(
            user_id=user_id,
            client_name=request.client_name,
            property_type=request.property_type,
            num_rooms=request.num_rooms,
            land_size=request.land_size,
            architectural_style=request.architectural_style,
            additional_preferences=request.additional_preferences,
            prompt_used=request.prompt_used,
            images=images_dict,
            client_id=request.client_id,
        )

        return GenerationResponse(
            id=doc_id,
            client_name=request.client_name,
            client_id=request.client_id,
            property_type=request.property_type,
            num_rooms=request.num_rooms,
            land_size=request.land_size,
            architectural_style=request.architectural_style,
            additional_preferences=request.additional_preferences,
            images=request.images,
            prompt_used=request.prompt_used,
            created_at="",  # Will be set by Firestore
            user_id=user_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save generation: {str(e)}",
        )


@router.get("/history", response_model=list[GenerationHistoryItem])
async def get_history(user=Depends(verify_token)):
    """Get the user's generation history."""
    user_id = user["uid"]
    try:
        results = await db_service.get_user_generations(user_id)
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch history: {str(e)}",
        )


@router.get("/admin/all-history", response_model=list[GenerationHistoryItem])
async def get_all_history(user=Depends(verify_token)):
    """Admin only: Get history from ALL users."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    try:
        results = await db_service.list_all_generations()
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch all history: {str(e)}",
        )


@router.get("/generation/{generation_id}", response_model=GenerationResponse)
async def get_generation(generation_id: str, user=Depends(verify_token)):
    """Get a specific generation by ID."""
    user_id = user["uid"]
    is_admin = user.get("role") == "admin"
    try:
        result = await db_service.get_generation(generation_id, user_id, is_admin=is_admin)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation not found or access denied",
            )
        return GenerationResponse(
            id=result["id"],
            client_name=result.get("client_name"),
            client_id=result.get("client_id"),
            property_type=result.get("property_type", ""),
            num_rooms=result.get("num_rooms", 0),
            land_size=result.get("land_size", ""),
            architectural_style=result.get("architectural_style", ""),
            additional_preferences=result.get("additional_preferences"),
            images=result.get("images", []),
            prompt_used=result.get("prompt_used", ""),
            created_at=result.get("created_at", ""),
            user_id=result.get("user_id", user_id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch generation: {str(e)}",
        )


@router.put("/generation/{generation_id}", response_model=dict)
async def update_generation_endpoint(generation_id: str, request: GenerationUpdate, user=Depends(verify_token)):
    """Update a generation (e.g. client name)."""
    user_id = user["uid"]
    is_admin = user.get("role") == "admin"
    try:
        success = await db_service.update_generation(generation_id, user_id, request.dict(exclude_unset=True), is_admin=is_admin)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation not found or access denied",
            )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update generation: {str(e)}",
        )


@router.delete("/generation/{generation_id}")
async def delete_generation_endpoint(generation_id: str, user=Depends(verify_token)):
    """Delete a generation."""
    user_id = user["uid"]
    is_admin = user.get("role") == "admin"
    try:
        success = await db_service.delete_generation(generation_id, user_id, is_admin=is_admin)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation not found or access denied",
            )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete generation: {str(e)}",
        )
