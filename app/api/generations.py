from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from app.core.auth_middleware import verify_token
from app.schemas.generation import GenerationRequest, GenerationResponse, GenerationHistoryItem, WorkspaceResponse, SingleRoomRequest, SaveGenerationRequest, GenerationImage, GenerationUpdate, FloorPlanRequest, FloorPlanWorkspaceResponse, FloorPlanSpecification, SingleFloorPlanViewRequest, SaveFloorPlanRequest
from app.services import ai_service, storage_service
from app.repositories import generation_repository as db_service
import uuid
import os
import asyncio
from typing import Optional
from typing import List

router = APIRouter()

_cancel_events: dict[str, asyncio.Event] = {}


@router.post("/generate/cancel")
async def cancel_generation(request: dict, user=Depends(verify_token)):
    generation_id = request.get("generation_id")
    if generation_id and generation_id in _cancel_events:
        _cancel_events[generation_id].set()
        return {"status": "cancelled"}
    return {"status": "not_found"}


import json

def _build_house_plan_prompt(
    request: GenerationRequest,
) -> str:
    """Build a comprehensive prompt from the structured house plan request."""
    parts = []

    # Core description
    story_text = f"{request.num_stories}-story" if request.is_multi_story and request.num_stories else "single-story"
    parts.append(
        f"A {request.house_style} style residential property in Cameroon: "
        f"a {story_text} home with {request.num_bedrooms} bedroom{'s' if request.num_bedrooms > 1 else ''} "
        f"and {request.num_bathrooms} bathroom{'s' if request.num_bathrooms > 1 else ''}. "
        f"Total gross floor area approximately {request.gross_area} square meters."
    )

    # Exterior & Structure
    exterior_parts = [f"Roof: {request.roof_type} style.", f"Foundation: {request.foundation}."]
    if request.num_garages > 0:
        exterior_parts.append(f"Garage: {request.num_garages} vehicle{'s' if request.num_garages > 1 else ''}.")
    if request.outdoor_spaces:
        exterior_parts.append("Outdoor spaces: " + ", ".join(request.outdoor_spaces) + ".")
    parts.append(" ".join(exterior_parts))

    # Interior Layout
    kitchen_desc = "open-plan kitchen" if request.kitchen_type == "Open" else "separate enclosed kitchen"
    interior_parts = [
        f"Overall layout: {request.overall_layout}.",
        f"Kitchen: {kitchen_desc}.",
    ]
    if request.key_rooms:
        interior_parts.append("Additional rooms: " + ", ".join(request.key_rooms) + ".")
    parts.append(" ".join(interior_parts))

    # Cameroon Region Context
    region_contexts = {
        "Douala": "Optimized for Douala's coastal wet/clay soil: elevated foundation, high cross-ventilation, wide verandas.",
        "Yaoundé": "Tailored for Yaoundé's steep sloped/rocky terrain: multi-level layout, stone retaining walls, stepped design.",
        "Coastal": "Designed for the coastal flood-risk zone: elevated concrete structure, flood-safe ground clearance, large shaded areas.",
        "West": "Adapted for Western Highlands: deep roof overhangs, robust surface drainage, slope-stabilized foundation.",
        "North": "Designed for Sahel hot-arid climate: high thermal mass walls, high ceilings, small shaded openings, cross-ventilation.",
        "Center": "Standard design for stable laterite soil: clean modern layout with good cross-ventilation and natural light.",
    }
    region_ctx = region_contexts.get(request.region, "")
    if region_ctx:
        parts.append(region_ctx)

    # Additional preferences
    if request.additional_preferences:
        parts.append(f"Special requirements: {request.additional_preferences}.")

    return " ".join(parts)


@router.post("/generate")
async def generate_design(request: GenerationRequest, user=Depends(verify_token)):
    """Generate AI exterior house design concepts with real-time SSE progress."""
    user_id = user["uid"]

    async def event_generator():
        cancel_event = asyncio.Event()
        generation_id = uuid.uuid4().hex
        _cancel_events[generation_id] = cancel_event
        try:
            uploaded_images = []
            prompt_used = ""
            idx = 0

            yield f"data: {json.dumps({'status': 'generation_id', 'generation_id': generation_id})}\n\n"

            if cancel_event.is_set():
                yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'progress', 'message': 'Initializing AI engines...'})}\n\n"

            # Build comprehensive prompt from structured fields
            enriched_prompt = _build_house_plan_prompt(request)

            if cancel_event.is_set():
                yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                return

            async for event in ai_service.generate_images_stream(
                property_type=f"{request.house_style} Residence",
                num_rooms=request.num_bedrooms,
                land_size=f"{request.gross_area} m²",
                architectural_style=request.house_style,
                additional_preferences=enriched_prompt,
                is_multi_story=request.is_multi_story,
                cancel_event=cancel_event,
            ):
                if event["type"] in ["progress", "view_list", "view_start", "view_complete", "view_error", "error"]:
                    yield f"data: {json.dumps({'status': event['type'], **event})}\n\n"
                    if event["type"] == "error":
                        return
                
                elif event["type"] == "cancelled":
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return
                
                elif event["type"] == "master_prompt":
                    prompt_used = event["prompt"]
                
                elif event["type"] == "image":
                    label_str = event["label"]
                    yield f"data: {json.dumps({'status': 'progress', 'message': f'Uploading {label_str}...'})}\n\n"

                    if cancel_event.is_set():
                        yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                        return
                    
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
                    
            workspace_payload = {
                "generation_id": generation_id,
                "images": uploaded_images,
                "prompt_used": prompt_used,
                "specification": {
                    "house_style": request.house_style,
                    "gross_area": request.gross_area,
                    "is_multi_story": request.is_multi_story,
                    "num_stories": request.num_stories,
                    "num_bedrooms": request.num_bedrooms,
                    "num_bathrooms": request.num_bathrooms,
                    "roof_type": request.roof_type,
                    "foundation": request.foundation,
                    "num_garages": request.num_garages,
                    "outdoor_spaces": request.outdoor_spaces,
                    "overall_layout": request.overall_layout,
                    "kitchen_type": request.kitchen_type,
                    "key_rooms": request.key_rooms,
                    "region": request.region,
                    "additional_preferences": request.additional_preferences,
                },
            }
            yield f"data: {json.dumps({'status': 'complete', 'workspace': workspace_payload})}\n\n"

        except Exception as e:
            error_payload = {"status": "error", "detail": f"Generation failed: {str(e)}"}
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            _cancel_events.pop(generation_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")



@router.post("/generate/room", response_model=GenerationImage)
async def generate_single_room(request: SingleRoomRequest, user=Depends(verify_token)):
    """Regenerate a single specific view."""
    user_id = user["uid"]
    
    try:
        enriched_prompt = _build_single_room_prompt(request)

        img_bytes = await ai_service.generate_single_view(
            property_type=f"{request.house_style} Residence",
            num_rooms=request.num_bedrooms,
            land_size=f"{request.gross_area} m²",
            architectural_style=request.house_style,
            view_type=request.view_type,
            additional_preferences=enriched_prompt,
        )
        
        if not img_bytes:
            raise Exception("AI failed to generate image.")

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


def _build_single_room_prompt(request: SingleRoomRequest) -> str:
    """Build enriched prompt for single room regeneration."""
    parts = []
    story_text = f"{request.num_stories}-story" if request.is_multi_story and request.num_stories else "single-story"
    parts.append(
        f"A {request.house_style} style Cameroon home: "
        f"{story_text}, {request.num_bedrooms} bedrooms, {request.num_bathrooms} bathrooms, "
        f"{request.gross_area} m². "
        f"Roof: {request.roof_type}. Foundation: {request.foundation}. "
        f"Layout: {request.overall_layout}. Kitchen: {request.kitchen_type}."
    )
    if request.outdoor_spaces:
        parts.append("Outdoor: " + ", ".join(request.outdoor_spaces) + ".")
    if request.key_rooms:
        parts.append("Rooms: " + ", ".join(request.key_rooms) + ".")
    if request.additional_preferences:
        parts.append(f"Extra: {request.additional_preferences}.")
    return " ".join(parts)


@router.post("/generation/save", response_model=GenerationResponse)
async def save_generation(request: SaveGenerationRequest, user=Depends(verify_token)):
    """Officially save an approved Workspace generation to the database."""
    user_id = user["uid"]
    
    try:
        images_dict = [{"url": img.url, "storage_path": img.storage_path} for img in request.images]
        
        doc_id = await db_service.save_generation(
            user_id=user_id,
            client_name=request.client_name,
            house_style=request.house_style,
            gross_area=request.gross_area,
            is_multi_story=request.is_multi_story,
            num_stories=request.num_stories,
            num_bedrooms=request.num_bedrooms,
            num_bathrooms=request.num_bathrooms,
            roof_type=request.roof_type,
            foundation=request.foundation,
            num_garages=request.num_garages,
            outdoor_spaces=request.outdoor_spaces,
            overall_layout=request.overall_layout,
            kitchen_type=request.kitchen_type,
            key_rooms=request.key_rooms,
            region=request.region,
            additional_preferences=request.additional_preferences,
            prompt_used=request.prompt_used,
            images=images_dict,
        )

        return GenerationResponse(
            id=doc_id,
            client_name=request.client_name,
            house_style=request.house_style,
            gross_area=request.gross_area,
            is_multi_story=request.is_multi_story,
            num_stories=request.num_stories,
            num_bedrooms=request.num_bedrooms,
            num_bathrooms=request.num_bathrooms,
            roof_type=request.roof_type,
            foundation=request.foundation,
            num_garages=request.num_garages,
            outdoor_spaces=request.outdoor_spaces,
            overall_layout=request.overall_layout,
            kitchen_type=request.kitchen_type,
            key_rooms=request.key_rooms,
            region=request.region,
            additional_preferences=request.additional_preferences,
            images=request.images,
            prompt_used=request.prompt_used,
            created_at="",
            user_id=user_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save generation: {str(e)}",
        )


@router.get("/history", response_model=list[GenerationHistoryItem])
async def get_history(user=Depends(verify_token)):
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


@router.get("/generation/{generation_id}")
async def get_generation(generation_id: str, user=Depends(verify_token)):
    user_id = user["uid"]
    is_admin = user.get("role") == "admin"
    try:
        result = await db_service.get_generation(generation_id, user_id, is_admin=is_admin)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation not found or access denied",
            )
        generation_type = result.get("generation_type", "house_plan")
        
        if generation_type == "floor_plan":
            spec = result.get("floor_plan_spec", {})
            return {
                "id": result["id"],
                "generation_type": "floor_plan",
                "property_type": "Floor Plan",
                "num_rooms": result.get("num_rooms", 0),
                "land_size": result.get("land_size", ""),
                "region": result.get("region", "Center"),
                "construction_standard": result.get("construction_standard", "Standard Modern"),
                "images": result.get("images", []),
                "prompt_used": result.get("prompt_used", ""),
                "created_at": result.get("created_at", ""),
                "user_id": result.get("user_id", user_id),
                "floor_plan_spec": spec,
            }
        
        return {
            "id": result["id"],
            "generation_type": "house_plan",
            "client_name": result.get("client_name"),
            "house_style": result.get("house_style", ""),
            "gross_area": result.get("gross_area", ""),
            "is_multi_story": result.get("is_multi_story", False),
            "num_stories": result.get("num_stories"),
            "num_bedrooms": result.get("num_bedrooms", 0),
            "num_bathrooms": result.get("num_bathrooms", 0),
            "roof_type": result.get("roof_type", ""),
            "foundation": result.get("foundation", ""),
            "num_garages": result.get("num_garages", 0),
            "outdoor_spaces": result.get("outdoor_spaces", []),
            "overall_layout": result.get("overall_layout", ""),
            "kitchen_type": result.get("kitchen_type", ""),
            "key_rooms": result.get("key_rooms", []),
            "region": result.get("region", "Center"),
            "additional_preferences": result.get("additional_preferences"),
            "images": result.get("images", []),
            "prompt_used": result.get("prompt_used", ""),
            "created_at": result.get("created_at", ""),
            "user_id": result.get("user_id", user_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch generation: {str(e)}",
        )


@router.put("/generation/{generation_id}", response_model=dict)
async def update_generation_endpoint(generation_id: str, request: GenerationUpdate, user=Depends(verify_token)):
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


# --- Floor Plan Endpoints (unchanged) ---

@router.post("/generate/floor-plan")
async def generate_floor_plan(request: FloorPlanRequest, user=Depends(verify_token)):
    user_id = user["uid"]

    async def event_generator():
        cancel_event = asyncio.Event()
        generation_id = uuid.uuid4().hex
        _cancel_events[generation_id] = cancel_event
        try:
            uploaded_images = []
            prompt_used = ""
            idx = 0

            yield f"data: {json.dumps({'status': 'generation_id', 'generation_id': generation_id})}\n\n"

            if cancel_event.is_set():
                yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'progress', 'message': 'Initializing floor plan engine...'})}\n\n"

            region_context = ""
            region = request.region or "Center"
            region_contexts = {
                "Douala": "Design for Douala's coastal climate: elevated foundation, high cross-ventilation, wide verandas.",
                "Yaoundé": "Design for Yaoundé's steep terrain: multi-level layout, retaining walls, stone accents.",
                "Coastal": "Design for coastal Cameroon: flood-safe elevated structure, large shaded areas, anti-corrosion materials.",
                "West": "Design for Western Highlands: deep roof overhangs, robust drainage, slope-adapted layout.",
                "North": "Design for Sahelian climate: high thermal mass walls, high ceilings, small shaded openings, cross-ventilation.",
                "Center": "Design for stable laterite soil: standard modern layout with good cross-ventilation.",
            }
            region_context = region_contexts.get(region, "")

            extras_desc = ""
            if request.extras:
                extras_desc = "Include the following rooms: " + ", ".join(request.extras) + "."

            kitchen_desc = "The kitchen should be open-plan, integrated with the living area." if request.kitchen_type == "open" else "The kitchen should be a separate enclosed room."

            prompt = (
                f"Professional architectural 2D floor plan for a Cameroon residential property. "
                f"Specifications: {request.num_bedrooms} bedrooms, {request.num_bathrooms} bathrooms, "
                f"gross floor area approximately {request.gross_area} square meters. "
                f"{kitchen_desc} "
                f"{extras_desc} "
                f"{region_context} "
                f"{request.additional_preferences or ''} "
                "Style: Clean fine black vector-style linework on a solid, pure white background. "
                "CRITICAL: Zero color, zero gray fills, zero realistic rendering, zero shading, and zero paper textures or blue grids. "
                "Every line is a fine, clean, high-contrast crisp black outline stroke (CAD/Revit export style). "
                "Show detailed room layouts, wall thicknesses, door swings, window placements, simple line-based furniture outlines, and room labels. "
                "High quality technical architectural drawing standard, neat lines, no text outside labels."
            )

            prompt_used = prompt

            views = [
                {"key": "floor_plan_main", "label": "Main Floor Plan"},
                {"key": "floor_plan_annotated", "label": "Annotated Plan with Dimensions"},
                {"key": "floor_plan_3d", "label": "3D Isometric Layout View"},
            ]
            yield f"data: {json.dumps({'status': 'view_list', 'views': views})}\n\n"

            for i, view in enumerate(views):
                if cancel_event.is_set():
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return

                view_key = view["key"]
                view_label = view["label"]

                yield f"data: {json.dumps({'status': 'view_start', 'view_key': view_key, 'label': view_label})}\n\n"
                yield f"data: {json.dumps({'status': 'progress', 'message': f'Generating {view_label}...'})}\n\n"

                if cancel_event.is_set():
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return

                view_prompt = prompt
                if view_key == "floor_plan_annotated":
                    view_prompt = prompt + " Add precise thin black dimension lines, measurement labels in meters, room area labels, and a clean north arrow. Professional technical construction document style."
                elif view_key == "floor_plan_3d":
                    view_prompt = prompt + " Show as a 3D isometric/perspective cutaway view of the floor plan, with color-coded rooms, 3D furniture, and realistic materials. Warm inviting style."

                img_bytes = await ai_service.generate_floor_plan_image(view_prompt)

                if cancel_event.is_set():
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return

                if img_bytes:
                    yield f"data: {json.dumps({'status': 'progress', 'message': f'Uploading {view_label}...'})}\n\n"

                    if cancel_event.is_set():
                        yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                        return

                    img_data = await storage_service.upload_image(
                        image_bytes=img_bytes,
                        user_id=user_id,
                        generation_id=generation_id,
                        index=idx,
                    )
                    idx += 1
                    uploaded_images.append({
                        "url": img_data["url"],
                        "storage_path": img_data["storage_path"],
                        "label": view_label,
                    })
                    yield f"data: {json.dumps({'status': 'view_complete', 'view_key': view_key, 'label': view_label})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': 'view_error', 'view_key': view_key, 'label': view_label})}\n\n"
                    yield f"data: {json.dumps({'status': 'progress', 'message': f'Failed to generate {view_label}.'})}\n\n"

            workspace_payload = {
                "generation_id": generation_id,
                "images": uploaded_images,
                "prompt_used": prompt_used,
                "specification": {
                    "num_bedrooms": request.num_bedrooms,
                    "num_bathrooms": request.num_bathrooms,
                    "gross_area": request.gross_area,
                    "kitchen_type": request.kitchen_type,
                    "extras": request.extras,
                    "region": request.region or "Center",
                },
            }
            yield f"data: {json.dumps({'status': 'complete', 'workspace': workspace_payload})}\n\n"

        except Exception as e:
            error_payload = {"status": "error", "detail": f"Floor plan generation failed: {str(e)}"}
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            _cancel_events.pop(generation_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/generate/floor-plan/save")
async def save_floor_plan(request: SaveFloorPlanRequest, user=Depends(verify_token)):
    user_id = user["uid"]
    try:
        images_dict = [{"url": img.url, "storage_path": img.storage_path, "label": getattr(img, "label", None)} for img in request.images]
        doc_id = await db_service.save_floor_plan_generation(
            user_id=user_id,
            client_name=request.client_name,
            images=images_dict,
            prompt_used=request.prompt_used,
            specification=request.specification.model_dump(),
        )
        return {"id": doc_id, "status": "success", "message": "Floor plan saved successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save floor plan: {str(e)}",
        )


@router.post("/generation/{generation_id}/share")
async def share_generation(generation_id: str, user=Depends(verify_token)):
    user_id = user["uid"]
    is_admin = user.get("role") == "admin"
    try:
        share_token = await db_service.set_share_token(generation_id, user_id, is_admin=is_admin)
        if not share_token:
            raise HTTPException(status_code=404, detail="Generation not found or access denied")
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return {
            "share_token": share_token,
            "share_url": f"{base_url}/shared?token={share_token}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate share link: {str(e)}")


@router.get("/shared/{share_token}")
async def get_shared_generation(share_token: str):
    try:
        result = await db_service.get_generation_by_share_token(share_token)
        if not result:
            raise HTTPException(status_code=404, detail="Shared generation not found")
        generation_type = result.get("generation_type", "house_plan")

        if generation_type == "floor_plan":
            spec = result.get("floor_plan_spec", {})
            images = [
                {"url": img["url"], "storage_path": img.get("storage_path", ""), "label": img.get("label")}
                for img in result.get("images", [])
            ]
            return {
                "id": result["id"],
                "client_name": result.get("client_name"),
                "generation_type": "floor_plan",
                "floor_plan_spec": spec,
                "images": images,
                "prompt_used": result.get("prompt_used", ""),
                "created_at": result.get("created_at", ""),
            }

        images = [
            {"url": img["url"], "storage_path": img.get("storage_path", ""), "label": img.get("label")}
            for img in result.get("images", [])
        ]
        return {
            "id": result["id"],
            "client_name": result.get("client_name"),
            "generation_type": "house_plan",
            "house_style": result.get("house_style", ""),
            "architectural_style": result.get("architectural_style", ""),
            "gross_area": result.get("gross_area", ""),
            "land_size": result.get("land_size", ""),
            "num_bedrooms": result.get("num_bedrooms", 0),
            "num_rooms": result.get("num_rooms", 0),
            "num_bathrooms": result.get("num_bathrooms", 0),
            "roof_type": result.get("roof_type", ""),
            "foundation": result.get("foundation", ""),
            "is_multi_story": result.get("is_multi_story", False),
            "num_stories": result.get("num_stories"),
            "overall_layout": result.get("overall_layout", ""),
            "region": result.get("region", "Center"),
            "outdoor_spaces": result.get("outdoor_spaces", []),
            "key_rooms": result.get("key_rooms", []),
            "construction_standard": result.get("construction_standard"),
            "additional_preferences": result.get("additional_preferences"),
            "images": images,
            "prompt_used": result.get("prompt_used", ""),
            "created_at": result.get("created_at", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shared generation: {str(e)}")


@router.post("/generate/floor-plan/room", response_model=GenerationImage)
async def regenerate_floor_plan_view(request: SingleFloorPlanViewRequest, user=Depends(verify_token)):
    try:
        prompt = request.prompt or "Regenerate the floor plan view with the same specifications."
        img_bytes = await ai_service.generate_floor_plan_image(prompt)
        if not img_bytes:
            raise Exception("AI failed to generate floor plan image.")
        random_idx = int(uuid.uuid4().int % 10000)
        img_data = await storage_service.upload_image(
            image_bytes=img_bytes,
            user_id=user["uid"],
            generation_id=request.generation_id,
            index=random_idx,
        )
        return GenerationImage(url=img_data["url"], storage_path=img_data["storage_path"])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Floor plan regeneration failed: {str(e)}",
        )
