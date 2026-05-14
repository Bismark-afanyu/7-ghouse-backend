from fastapi import APIRouter, Depends, HTTPException, status
from app.core.auth_middleware import verify_token
from app.schemas.generation import GenerationRequest, GenerationResponse, GenerationHistoryItem
from app.services import ai_service, storage_service
from app.repositories import generation_repository as db_service
import uuid

router = APIRouter()


@router.post("/generate", response_model=GenerationResponse)
async def generate_design(request: GenerationRequest, user=Depends(verify_token)):
    """Generate AI exterior house design concepts from property details."""
    user_id = user["uid"]

    try:
        # 1. Generate images using AI
        prompt_used, image_bytes_list = await ai_service.generate_images(
            property_type=request.property_type,
            num_rooms=request.num_rooms,
            land_size=request.land_size,
            architectural_style=request.architectural_style,
            additional_preferences=request.additional_preferences,
            num_images=3,
        )

        # 2. Create a temporary generation ID for storage paths
        generation_id = uuid.uuid4().hex

        # 3. Upload images to Firebase Storage
        uploaded_images = []
        for idx, img_bytes in enumerate(image_bytes_list):
            img_data = await storage_service.upload_image(
                image_bytes=img_bytes,
                user_id=user_id,
                generation_id=generation_id,
                index=idx,
            )
            uploaded_images.append(img_data)

        # 4. Save generation record to Firestore
        doc_id = await db_service.save_generation(
            user_id=user_id,
            client_name=request.client_name,
            property_type=request.property_type,
            num_rooms=request.num_rooms,
            land_size=request.land_size,
            architectural_style=request.architectural_style,
            additional_preferences=request.additional_preferences,
            prompt_used=prompt_used,
            images=uploaded_images,
        )

        return GenerationResponse(
            id=doc_id,
            client_name=request.client_name,
            property_type=request.property_type,
            num_rooms=request.num_rooms,
            land_size=request.land_size,
            architectural_style=request.architectural_style,
            additional_preferences=request.additional_preferences,
            images=uploaded_images,
            prompt_used=prompt_used,
            created_at="",  # Will be set by Firestore
            user_id=user_id,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {str(e)}",
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


@router.get("/generation/{generation_id}", response_model=GenerationResponse)
async def get_generation(generation_id: str, user=Depends(verify_token)):
    """Get a specific generation by ID."""
    user_id = user["uid"]
    try:
        result = await db_service.get_generation(generation_id, user_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation not found",
            )
        return GenerationResponse(
            id=result["id"],
            client_name=result.get("client_name"),
            property_type=result.get("property_type", ""),
            num_rooms=result.get("num_rooms", 0),
            land_size=result.get("land_size", ""),
            architectural_style=result.get("architectural_style", ""),
            additional_preferences=result.get("additional_preferences"),
            images=result.get("images", []),
            prompt_used=result.get("prompt_used", ""),
            created_at=result.get("created_at", ""),
            user_id=user_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch generation: {str(e)}",
        )
