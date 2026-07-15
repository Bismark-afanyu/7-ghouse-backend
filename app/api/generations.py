from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse, Response
from app.core.auth_middleware import verify_token
from app.schemas.generation import GenerationRequest, AnalyzePdfRequest, GenerationResponse, GenerationHistoryItem, WorkspaceResponse, SingleRoomRequest, SaveGenerationRequest, GenerationImage, GenerationUpdate, FloorPlanRequest, FloorPlanWorkspaceResponse, FloorPlanSpecification, SingleFloorPlanViewRequest, SaveFloorPlanRequest, CleanupRequest
from app.services import ai_service, storage_service
from app.services.floor_plan_layout import generate_floor_plan_layout
from app.services.floor_plan_ai import render_floor_plan_ai as render_floor_plan
from app.services.elevation_renderer import render_elevations
from app.services.cross_section_renderer import render_cross_section
from app.services.three_d_renderer import render_3d_wireframe
from app.services.roof_plan_renderer import render_roof_plan
from app.services.autocad_drafter import generate_precise_layout_data, render_preview_image, render_autocad_dxf
from app.repositories import generation_repository as db_service
import logging

logger = logging.getLogger(__name__)

_FLOOR_PLAN_VIEW_RENDERERS = {
    "floor_plan_main": lambda l: render_floor_plan(l, annotated=False),
    "floor_plan_annotated": lambda l: render_floor_plan(l, annotated=True),
    "elevations_composite": lambda l: asyncio.to_thread(render_elevations, l),
    "roof_plan_view": lambda l: asyncio.to_thread(render_roof_plan, l),
    "floor_plan_3d": lambda l: asyncio.to_thread(render_3d_wireframe, l),
}
import uuid
import os
import asyncio
import base64
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
    terrain_info: Optional[dict] = None,
) -> str:
    """Build a comprehensive prompt from the structured house plan request."""
    parts = []

    # Core description — varies by building type
    building_type = request.building_type or "single_family"
    story_text = f"{request.num_stories}-story" if request.is_multi_story and request.num_stories else "single-story"

    if building_type == "apartment" and request.units_per_floor and request.num_floors:
        total_units = request.units_per_floor * request.num_floors
        unit_bed = request.unit_bedrooms or 1
        unit_bath = request.unit_bathrooms or 1
        unit_kit = request.unit_kitchens or 1
        unit_lr = request.unit_living_rooms or 1
        parts.append(
            f"A {request.house_style} style apartment building in Cameroon: "
            f"a {story_text} building with {total_units} self-contained apartment units "
            f"({request.units_per_floor} units per floor x {request.num_floors} floors). "
            f"Each unit includes {unit_bed} bedroom{'s' if unit_bed > 1 else ''}, "
            f"{unit_bath} bathroom{'s' if unit_bath > 1 else ''}, "
            f"{unit_kit} kitchen{'s' if unit_kit > 1 else ''}, "
            f"and {unit_lr} living room{'s' if unit_lr > 1 else ''}. "
            f"Total gross floor area approximately {request.gross_area} square meters."
        )
    elif building_type == "duplex":
        parts.append(
            f"A {request.house_style} style duplex in Cameroon: "
            f"a {story_text} building with {request.num_bedrooms} bedroom{'s' if request.num_bedrooms > 1 else ''}, "
            f"{request.num_bathrooms} bathroom{'s' if request.num_bathrooms > 1 else ''}, "
            f"{request.num_kitchens} kitchen{'s' if request.num_kitchens > 1 else ''}, "
            f"and {request.num_living_rooms} living room{'s' if request.num_living_rooms > 1 else ''}. "
            f"Total gross floor area approximately {request.gross_area} square meters."
        )
    elif building_type == "townhouse":
        parts.append(
            f"A {request.house_style} style townhouse in Cameroon: "
            f"a {story_text} home with {request.num_bedrooms} bedroom{'s' if request.num_bedrooms > 1 else ''}, "
            f"{request.num_bathrooms} bathroom{'s' if request.num_bathrooms > 1 else ''}, "
            f"{request.num_kitchens} kitchen{'s' if request.num_kitchens > 1 else ''}, "
            f"and {request.num_living_rooms} living room{'s' if request.num_living_rooms > 1 else ''}. "
            f"Total gross floor area approximately {request.gross_area} square meters."
        )
    elif building_type == "commercial":
        parts.append(
            f"A {request.house_style} style commercial building in Cameroon: "
            f"a {story_text} building with {request.num_bedrooms} rooms, "
            f"{request.num_bathrooms} bathroom{'s' if request.num_bathrooms > 1 else ''}, "
            f"and {request.num_kitchens} kitchen{'s' if request.num_kitchens > 1 else ''}. "
            f"Total gross floor area approximately {request.gross_area} square meters."
        )
    else:
        # single_family (default)
        parts.append(
            f"A {request.house_style} style residential property in Cameroon: "
            f"a {story_text} home with {request.num_bedrooms} bedroom{'s' if request.num_bedrooms > 1 else ''}, "
            f"{request.num_bathrooms} bathroom{'s' if request.num_bathrooms > 1 else ''}, "
            f"{request.num_kitchens} kitchen{'s' if request.num_kitchens > 1 else ''}, "
            f"and {request.num_living_rooms} living room{'s' if request.num_living_rooms > 1 else ''}. "
            f"Total gross floor area approximately {request.gross_area} square meters."
        )

    # Land dimensions & shape context
    land_parts = []
    if request.land_shape and request.land_shape != "rectangle":
        land_parts.append(f"Land shape: {request.land_shape.replace('_', ' ').title()}.")
    if request.land_length and request.land_width:
        land_parts.append(f"Plot dimensions: {request.land_length}m × {request.land_width}m.")
    if request.terrain_shape:
        land_parts.append(f"Terrain: {request.terrain_shape}.")
    if land_parts:
        parts.append(" ".join(land_parts))

    # Coordinates / location context
    if request.latitude and request.longitude:
        parts.append(f"Building site coordinates: {request.latitude}, {request.longitude}.")
    if request.location_name:
        parts.append(f"Location: {request.location_name}.")

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
    ]
    if request.num_kitchens > 1:
        interior_parts.append(f"{request.num_kitchens} separate {kitchen_desc}s.")
    else:
        interior_parts.append(f"Kitchen: {kitchen_desc}.")
    if request.num_living_rooms > 1:
        interior_parts.append(f"{request.num_living_rooms} separate living rooms.")
    if request.key_rooms:
        interior_parts.append("Additional rooms: " + ", ".join(request.key_rooms) + ".")
    parts.append(" ".join(interior_parts))

    # Cameroon Region Context
    region_contexts = {
        "Littoral": "Optimized for Douala's coastal wet/clay soil: elevated foundation, high cross-ventilation, wide verandas.",
        "Centre": "Tailored for Yaoundé's steep sloped/rocky terrain: multi-level layout, stone retaining walls, stepped design.",
        "West": "Adapted for Western Highlands: deep roof overhangs, robust surface drainage, slope-stabilized foundation.",
        "North": "Designed for Sahel hot-arid climate: high thermal mass walls, high ceilings, small shaded openings, cross-ventilation.",
        "Adamaoua": "Designed for Adamaoua highland savannah: good cross-ventilation, sun-shading, robust rainwater harvesting.",
        "North-West": "Designed for North-West mountainous terrain: slope-adapted foundation, reinforced retaining walls, deep drainage.",
        "South": "Designed for South Cameroon dense rainforest: high-pitched roof, extensive covered areas, anti-mold ventilation.",
        "East": "Designed for East region forest-savannah transition: raised foundation, wide verandas, termite-resistant materials.",
        "Far North": "Designed for Far North extreme arid Sahel: high thermal mass, compact layout, shaded courtyard, minimal glazing.",
        "South-West": "Optimized for South-West volcanic/coastal zone: elevated structure, flood-safe ground clearance, corrosion-resistant fixtures.",
    }
    _legacy_map = {"Douala": "Littoral", "Yaoundé": "Centre", "Coastal": "South-West", "Center": "Centre"}
    mapped_region = _legacy_map.get(request.region, request.region)
    region_ctx = region_contexts.get(mapped_region, "")
    if region_ctx:
        parts.append(region_ctx)

    # Terrain data from coordinates
    if terrain_info:
        parts.append(
            f"Site terrain analysis: Elevation {terrain_info['elevation_m']:.0f}m, "
            f"{terrain_info['terrain_type']}. "
            f"Foundation recommendation: {terrain_info['foundation_recommendation']}"
        )

    # Additional preferences
    if request.additional_preferences:
        parts.append(f"Special requirements: {request.additional_preferences}.")

    # Reference analysis from uploaded PDF floor plan
    if request.reference_analysis:
        parts.append(f"Reference floor plan analysis: {request.reference_analysis}")

    return " ".join(parts)


@router.post("/generate")
async def generate_design(request: GenerationRequest, user=Depends(verify_token)):
    """Generate AI exterior house design concepts with real-time SSE progress."""
    user_id = user["uid"]

    async def event_generator():
        cancel_event = asyncio.Event()
        generation_id = uuid.uuid4().hex
        _cancel_events[generation_id] = cancel_event
        layout_task = None
        try:
            uploaded_images = []
            prompt_used = ""
            idx = 0

            yield f"data: {json.dumps({'status': 'generation_id', 'generation_id': generation_id})}\n\n"

            if cancel_event.is_set():
                yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'progress', 'progress_type': 'initializing'})}\n\n"

            # Resolve final coordinates for validation
            region_warning = None
            resolved_lat = request.latitude
            resolved_lng = request.longitude
            resolved_location_name = request.location_name

            # Geocode location_name if coordinates not provided
            if not resolved_lat or not resolved_lng:
                if request.location_name:
                    try:
                        from app.services.geocoding import geocode_location
                        coords = await geocode_location(request.location_name)
                        if coords:
                            resolved_lat, resolved_lng = coords
                    except Exception as e:
                        logger.warning(f"Geocoding for validation failed: {e}")

            # Validate resolved coordinates against selected region
            if resolved_lat and resolved_lng:
                try:
                    from app.data.cameroon_locations import validate_coords_in_region
                    warning = validate_coords_in_region(resolved_lat, resolved_lng, request.region, resolved_location_name)
                    if warning:
                        region_warning = warning
                        logger.warning(f"Region validation: {warning}")
                except Exception as e:
                    logger.warning(f"Region validation failed: {e}")

            # Fetch terrain data if coordinates provided
            terrain_info = None
            if request.latitude and request.longitude:
                try:
                    from app.services.terrain_service import get_terrain_data
                    ti = await get_terrain_data(request.latitude, request.longitude, request.region)
                    terrain_info = {
                        "elevation_m": ti.elevation_m,
                        "slope_category": ti.slope_category,
                        "terrain_type": ti.terrain_type,
                        "foundation_recommendation": ti.foundation_recommendation,
                        "terrain_notes": ti.terrain_notes,
                    }
                except Exception as e:
                    logger.warning(f"Terrain lookup failed: {e}")

            # Cost estimation with hub selection
            cost_estimate = None
            try:
                from app.services.cost_estimation import estimate_construction_cost
                gfa_val = float(request.gross_area) if request.gross_area else 150.0
                ce = await estimate_construction_cost(
                    gross_area=gfa_val,
                    num_bedrooms=request.num_bedrooms,
                    num_bathrooms=request.num_bathrooms,
                    roof_type=request.roof_type,
                    is_multi_story=request.is_multi_story,
                    num_stories=request.num_stories or 1,
                    quality_tier="standard",
                    region=request.region,
                    division=request.division or None,
                    site_lat=request.latitude,
                    site_lng=request.longitude,
                    material_source_hub=request.material_source_hub or "",
                    custom_hub_name=request.custom_hub_name,
                    custom_hub_lat=request.custom_hub_lat,
                    custom_hub_lng=request.custom_hub_lng,
                    terrain_category=terrain_info.get("slope_category", "flat") if terrain_info else "flat",
                )
                cost_estimate = ce.model_dump()
            except Exception as e:
                logger.warning(f"Cost estimation failed: {e}")

            enriched_prompt = _build_house_plan_prompt(request, terrain_info=terrain_info)

            if cancel_event.is_set():
                yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                return

            layout_task = asyncio.create_task(
                generate_floor_plan_layout(
                    num_bedrooms=request.num_bedrooms,
                    num_bathrooms=int(request.num_bathrooms),
                    kitchen_type=request.kitchen_type,
                    extras=request.key_rooms + request.outdoor_spaces,
                    gross_area=request.gross_area,
                    land_length=request.land_length,
                    land_width=request.land_width,
                    num_kitchens=request.num_kitchens,
                    num_living_rooms=request.num_living_rooms,
                )
            )

            # Decode reference image if provided
            reference_image_bytes = None
            reference_mime_type = "image/jpeg"
            if request.reference_file_data and request.reference_file_type == "image":
                try:
                    header, b64data = request.reference_file_data.split(",", 1)
                    if ";" in header:
                        reference_mime_type = header.split(":")[1].split(";")[0]
                    reference_image_bytes = base64.b64decode(b64data)
                except Exception as e:
                    logger.warning(f"Failed to decode reference image: {e}")

            async for event in ai_service.generate_images_stream(
                property_type=f"{request.house_style} Residence",
                num_rooms=request.num_bedrooms,
                land_size=f"{request.gross_area} m²",
                architectural_style=request.house_style,
                additional_preferences=enriched_prompt,
                is_multi_story=request.is_multi_story,
                num_stories=request.num_stories or 1,
                roof_type=request.roof_type,
                cancel_event=cancel_event,
                overlay_language="en",
                num_bathrooms=int(request.num_bathrooms),
                num_kitchens=request.num_kitchens,
                num_living_rooms=request.num_living_rooms,
                kitchen_type=request.kitchen_type,
                key_rooms=request.key_rooms,
                outdoor_spaces=request.outdoor_spaces,
                building_type=request.building_type,
                layout=None,
                layout_task=layout_task,
                reference_image_bytes=reference_image_bytes,
                reference_mime_type=reference_mime_type,
                reference_analysis=request.reference_analysis,
            ):
                if event["type"] == "view_list":
                    yield f"data: {json.dumps({'status': 'view_list', 'views': event.get('views', [])})}\n\n"

                elif event["type"] in ["progress", "view_start", "view_complete", "view_error", "error"]:
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
                    yield f"data: {json.dumps({'status': 'progress', 'progress_type': 'uploading', 'label': label_str})}\n\n"

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
                    
            if not uploaded_images:
                yield f"data: {json.dumps({'status': 'error', 'detail': 'All views failed to generate. Check backend logs for details.'})}\n\n"
                return

            # Extract room measurements from completed layout task
            room_measurements = []
            if layout_task and layout_task.done() and not layout_task.cancelled():
                try:
                    layout = layout_task.result()
                    from app.schemas.generation import RoomMeasurement
                    for room in layout.rooms:
                        room_measurements.append(RoomMeasurement(
                            name=room.name,
                            code=getattr(room, "room_code", "") or "",
                            room_type=room.room_type or "",
                            width_m=round(room.width_cm / 100, 2),
                            height_m=round(room.height_cm / 100, 2),
                            area_m2=round(room.width_cm * room.height_cm / 10000, 2),
                        ).model_dump())
                except Exception:
                    logger.warning("Failed to extract room measurements", exc_info=True)

            workspace_payload = {
                "generation_id": generation_id,
                "images": uploaded_images,
                "prompt_used": prompt_used,
                "specification": {
                    "building_type": request.building_type,
                    "house_style": request.house_style,
                    "gross_area": request.gross_area,
                    "is_multi_story": request.is_multi_story,
                    "num_stories": request.num_stories,
                    "num_bedrooms": request.num_bedrooms,
                    "num_bathrooms": request.num_bathrooms,
                    "num_living_rooms": request.num_living_rooms,
                    "num_kitchens": request.num_kitchens,
                    "roof_type": request.roof_type,
                    "foundation": request.foundation,
                    "num_garages": request.num_garages,
                    "outdoor_spaces": request.outdoor_spaces,
                    "overall_layout": request.overall_layout,
                    "kitchen_type": request.kitchen_type,
                    "key_rooms": request.key_rooms,
                    "region": request.region,
                    "division": request.division,
                    "additional_preferences": request.additional_preferences,
                    "land_shape": request.land_shape,
                    "land_length": request.land_length,
                    "land_width": request.land_width,
                    "latitude": request.latitude,
                    "longitude": request.longitude,
                    "location_name": request.location_name,
                    "terrain_info": terrain_info,
                    "region_warning": region_warning,
                    "units_per_floor": request.units_per_floor,
                    "num_floors": request.num_floors,
                    "unit_bedrooms": request.unit_bedrooms,
                    "unit_bathrooms": request.unit_bathrooms,
                    "unit_kitchens": request.unit_kitchens,
                    "unit_living_rooms": request.unit_living_rooms,
                },
                "room_measurements": room_measurements,
                "cost_estimate": cost_estimate,
            }
            yield f"data: {json.dumps({'status': 'complete', 'workspace': workspace_payload})}\n\n"

        except Exception as e:
            logger.exception("Generation stream failed for %s", generation_id)
            error_payload = {"status": "error", "detail": f"Generation failed: {str(e)}"}
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            _cancel_events.pop(generation_id, None)
            if layout_task and not layout_task.done():
                layout_task.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")



@router.post("/generate/cleanup")
async def cleanup_images(request: CleanupRequest, user=Depends(verify_token)):
    """Delete uploaded images from storage when user cancels without saving."""
    deleted = 0
    failed = 0
    for path in request.storage_paths:
        success = await storage_service.delete_image(path)
        if success:
            deleted += 1
        else:
            failed += 1
    return {"status": "success", "deleted": deleted, "failed": failed}

@router.post("/generate/analyze-pdf")

async def analyze_floor_plan_pdf(file: UploadFile = File(...), lang: str = Query("en", pattern="^(en|fr)$"), user=Depends(verify_token)):
    """Analyze an uploaded PDF floor plan and return room layout, gaps, and suggestions."""
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are accepted",
            )

        pdf_bytes = await file.read()
        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file uploaded",
            )

        result = await ai_service.analyze_floor_plan_pdf(pdf_bytes, lang=lang)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF analysis failed: {str(e)}",
        )


@router.post("/generate/analyze-image")
async def analyze_plot_image_endpoint(file: UploadFile = File(...), lang: str = Query("en", pattern="^(en|fr)$"), user=Depends(verify_token)):
    """Analyze an uploaded plot/land image and return terrain, dimensions, and constraints."""
    try:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided",
            )

        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
        content_type = file.content_type or ""
        if content_type not in allowed_types and not file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image files are accepted (JPEG, PNG, WebP, HEIC)",
            )

        image_bytes = await file.read()
        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file uploaded",
            )

        result = await ai_service.analyze_plot_image(image_bytes, lang=lang)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plot image analysis failed: {str(e)}",
        )


@router.post("/generate/room", response_model=GenerationImage)
async def generate_single_room(request: SingleRoomRequest, user=Depends(verify_token)):
    """Regenerate a single specific view."""
    user_id = user["uid"]
    
    try:
        if request.view_type == "floor_plans_composite":
            layout = await generate_floor_plan_layout(
                num_bedrooms=request.num_bedrooms,
                num_bathrooms=int(request.num_bathrooms),
                kitchen_type=request.kitchen_type,
                extras=request.key_rooms + request.outdoor_spaces,
                gross_area=request.gross_area,
            )
            img_bytes = await render_floor_plan(layout, True)
        else:
            enriched_prompt = _build_single_room_prompt(request)
    
            img_bytes = await ai_service.generate_single_view(
                property_type=f"{request.house_style} Residence",
                num_rooms=request.num_bedrooms,
                land_size=f"{request.gross_area} m²",
                architectural_style=request.house_style,
                view_type=request.view_type,
                additional_preferences=enriched_prompt,
                num_stories=request.num_stories or 1,
                roof_type=request.roof_type,
                overlay_language="en",
                num_bathrooms=int(request.num_bathrooms),
                num_kitchens=request.num_kitchens,
                num_living_rooms=request.num_living_rooms,
                kitchen_type=request.kitchen_type,
                key_rooms=request.key_rooms,
                outdoor_spaces=request.outdoor_spaces,
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
    kitchen_info = f"{request.num_kitchens} kitchen{'s' if request.num_kitchens > 1 else ''}" if request.num_kitchens > 1 else f"Kitchen: {request.kitchen_type}"
    living_info = f"{request.num_living_rooms} living room{'s' if request.num_living_rooms > 1 else ''}" if request.num_living_rooms > 1 else "1 living room"
    parts.append(
        f"A {request.house_style} style Cameroon home: "
        f"{story_text}, {request.num_bedrooms} bedrooms, {request.num_bathrooms} bathrooms, "
        f"{kitchen_info}, {living_info}, "
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
        images_dict = [
            {
                "url": img.url,
                "storage_path": img.storage_path,
                "label": getattr(img, "label", None),
                "view_key": getattr(img, "view_key", None),
            } for img in request.images
        ]
        
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
            division=request.division,
            additional_preferences=request.additional_preferences,
            prompt_used=request.prompt_used,
            images=images_dict,
            cost_estimate=request.cost_estimate,
            room_measurements=request.room_measurements,
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
            division=request.division,
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
                "division": result.get("division", ""),
                "construction_standard": result.get("construction_standard", "Standard Modern"),
                "images": result.get("images", []),
                "prompt_used": result.get("prompt_used", ""),
                "created_at": result.get("created_at", ""),
                "user_id": result.get("user_id", user_id),
                "floor_plan_spec": spec,
                "pdf_url": result.get("telegram_pdf_url", ""),
                "pdf_generated_at": result.get("pdf_generated_at", ""),
                "video_external_url": result.get("video_external_url", ""),
                "video_internal_url": result.get("video_internal_url", ""),
                "video_external_status": result.get("video_external_status", ""),
                "video_internal_status": result.get("video_internal_status", ""),
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
            "division": result.get("division", ""),
            "additional_preferences": result.get("additional_preferences"),
            "images": result.get("images", []),
            "prompt_used": result.get("prompt_used", ""),
            "created_at": result.get("created_at", ""),
            "user_id": result.get("user_id", user_id),
            "pdf_url": result.get("telegram_pdf_url", ""),
            "pdf_generated_at": result.get("pdf_generated_at", ""),
            "video_external_url": result.get("video_external_url", ""),
            "video_internal_url": result.get("video_internal_url", ""),
            "video_external_status": result.get("video_external_status", ""),
            "video_internal_status": result.get("video_internal_status", ""),
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
        gen = await db_service.get_generation(generation_id, user_id, is_admin=is_admin)
        if not gen:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation not found or access denied",
            )
        for img in gen.get("images", []):
            storage_path = img.get("storage_path")
            if storage_path:
                await storage_service.delete_image(storage_path)
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

            yield f"data: {json.dumps({'status': 'progress', 'progress_type': 'initializing_fp'})}\n\n"

            # Launch layout task for room measurements
            layout_task = asyncio.create_task(
                generate_floor_plan_layout(
                    num_bedrooms=request.num_bedrooms,
                    num_bathrooms=int(request.num_bathrooms),
                    kitchen_type=request.kitchen_type,
                    extras=request.extras,
                    gross_area=request.gross_area,
                    num_kitchens=request.num_kitchens,
                    num_living_rooms=request.num_living_rooms,
                )
            )

            region_context = ""
            region = request.region or "Centre"
            region_contexts = {
                "Littoral": "Design for Douala's coastal climate: elevated foundation, high cross-ventilation, wide verandas.",
                "Centre": "Design for Yaoundé's steep terrain: multi-level layout, retaining walls, stone accents.",
                "West": "Design for Western Highlands: deep roof overhangs, robust drainage, slope-adapted layout.",
                "North": "Design for Sahelian climate: high thermal mass walls, high ceilings, small shaded openings, cross-ventilation.",
                "Adamaoua": "Design for Adamaoua highland savannah: good cross-ventilation, sun-shading, spacious rooms.",
                "North-West": "Design for North-West mountains: slope-adapted layout, deep drainage, sturdy foundations.",
                "South": "Design for South Cameroon rainforest: high-pitched roofs, covered patios, good airflow.",
                "East": "Design for East region: raised foundation, wide verandas, cross-ventilation for humid climate.",
                "Far North": "Design for Far North extreme arid Sahel: compact layout, thermal mass walls, shaded openings.",
                "South-West": "Design for South-West volcanic/coastal zone: elevated structure, flood-safe layout, corrosion-resistant.",
            }
            _legacy_map = {"Douala": "Littoral", "Yaoundé": "Centre", "Coastal": "South-West", "Center": "Centre"}
            mapped_region = _legacy_map.get(region, region)
            region_context = region_contexts.get(mapped_region, "")

            extras_desc = ""
            if request.extras:
                extras_desc = "Include the following rooms: " + ", ".join(request.extras) + "."

            # Legacy layout generation removed to save time as we only generate precise CAD data now.

            prompt_3d = (
                f"Professional 3D isometric cutaway view of a {request.num_bedrooms}-bedroom, "
                f"{request.num_bathrooms}-bathroom Cameroon residence, "
                f"{request.num_kitchens} kitchen{'s' if request.num_kitchens > 1 else ''}, "
                f"{request.num_living_rooms} living room{'s' if request.num_living_rooms > 1 else ''}, "
                f"gross floor area approximately {request.gross_area} square meters. "
                f"{'Open-plan kitchen.' if request.kitchen_type == 'open' else 'Separate enclosed kitchen.'} "
                f"{extras_desc} "
                f"{region_context} "
                f"{request.additional_preferences or ''} "
                "Show as a 3D isometric/perspective cutaway view of the floor plan, "
                "with color-coded rooms, 3D furniture, and realistic materials. Warm inviting style. "
                "ULTRA-HIGH QUALITY: 4K resolution, sharp focus, photorealistic quality, no blur, no artifacts."
            )
            prompt_used = prompt_3d

            views = [
                {"key": "floor_plan_cad", "label": "Precise CAD Layout (AutoCAD Level)"},
            ]
            yield f"data: {json.dumps({'status': 'view_list', 'views': views})}\n\n"
            
            dxf_url = None

            for i, view in enumerate(views):
                if cancel_event.is_set():
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return

                view_key = view["key"]
                view_label = view["label"]

                yield f"data: {json.dumps({'status': 'view_start', 'view_key': view_key, 'label': view_label})}\n\n"
                yield f"data: {json.dumps({'status': 'progress', 'progress_type': 'generating_fp', 'label': view_label})}\n\n"

                if cancel_event.is_set():
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return

                img_bytes = None

                if view_key == "floor_plan_cad":
                    try:
                        precise_layout_data = await generate_precise_layout_data(
                            gross_area=request.gross_area,
                            bedrooms=request.num_bedrooms,
                            bathrooms=float(request.num_bathrooms),
                            kitchen_type=request.kitchen_type,
                            extras=request.extras,
                            num_kitchens=request.num_kitchens,
                            num_living_rooms=request.num_living_rooms,
                        )
                        img_bytes = await render_preview_image(precise_layout_data)
                        
                        # Generate and upload DXF asynchronously here since we already have the layout data
                        dxf_bytes = await render_autocad_dxf(precise_layout_data)
                        random_idx_dxf = int(uuid.uuid4().int % 10000)
                        from app.services.storage_service import upload_file
                        dxf_data = await upload_file(
                            file_bytes=dxf_bytes,
                            user_id=user_id,
                            generation_id=generation_id,
                            filename=f"floor_plan_{random_idx_dxf}.dxf",
                            content_type="application/dxf",
                        )
                        dxf_url = dxf_data["url"]
                    except Exception as e:
                        logger.warning(f"Failed to generate precise CAD data: {e}")
                        
                elif view_key in ("floor_plan_main", "floor_plan_annotated"):
                    annotated = view_key == "floor_plan_annotated"
                    img_bytes = await render_floor_plan(layout, annotated)
                elif view_key == "elevations_composite":
                    img_bytes = await asyncio.to_thread(render_elevations, layout)
                elif view_key == "roof_plan_view":
                    img_bytes = await asyncio.to_thread(render_roof_plan, layout)
                elif view_key == "floor_plan_3d":
                    img_bytes = await asyncio.to_thread(render_3d_wireframe, layout)

                if cancel_event.is_set():
                    yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                    return

                if img_bytes:
                    yield f"data: {json.dumps({'status': 'progress', 'progress_type': 'uploading_fp', 'label': view_label})}\n\n"

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
                        "view_key": view_key,
                    })
                    yield f"data: {json.dumps({'status': 'view_complete', 'view_key': view_key, 'label': view_label})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': 'view_error', 'view_key': view_key, 'label': view_label})}\n\n"
                    yield f"data: {json.dumps({'status': 'progress', 'progress_type': 'failed_fp', 'label': view_label})}\n\n"

            # Extract room measurements from layout task
            room_measurements = []
            if layout_task and layout_task.done() and not layout_task.cancelled():
                try:
                    layout = layout_task.result()
                    from app.schemas.generation import RoomMeasurement
                    for room in layout.rooms:
                        room_measurements.append(RoomMeasurement(
                            name=room.name,
                            code=getattr(room, "room_code", "") or "",
                            room_type=room.room_type or "",
                            width_m=round(room.width_cm / 100, 2),
                            height_m=round(room.height_cm / 100, 2),
                            area_m2=round(room.width_cm * room.height_cm / 10000, 2),
                        ).model_dump())
                except Exception:
                    logger.warning("Failed to extract room measurements", exc_info=True)

            workspace_payload = {
                "generation_id": generation_id,
                "images": uploaded_images,
                "prompt_used": prompt_used,
                "specification": {
                    "num_bedrooms": request.num_bedrooms,
                    "num_bathrooms": request.num_bathrooms,
                    "num_living_rooms": request.num_living_rooms,
                    "num_kitchens": request.num_kitchens,
                    "gross_area": request.gross_area,
                    "kitchen_type": request.kitchen_type,
                    "extras": request.extras,
                    "region": request.region or "Center",
                    "division": request.division,
                },
                "dxf_url": dxf_url,
                "room_measurements": room_measurements,
            }
            yield f"data: {json.dumps({'status': 'complete', 'workspace': workspace_payload})}\n\n"

        except Exception as e:
            error_payload = {"status": "error", "detail": f"Floor plan generation failed: {str(e)}"}
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            _cancel_events.pop(generation_id, None)
            if layout_task and not layout_task.done():
                layout_task.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/generate/floor-plan/save")
async def save_floor_plan(request: SaveFloorPlanRequest, user=Depends(verify_token)):
    user_id = user["uid"]
    try:
        images_dict = [{
            "url": img.url,
            "storage_path": img.storage_path,
            "label": getattr(img, "label", None),
            "view_key": getattr(img, "view_key", None),
        } for img in request.images]
        doc_id = await db_service.save_floor_plan_generation(
            user_id=user_id,
            client_name=request.client_name,
            images=images_dict,
            prompt_used=request.prompt_used,
            specification=request.specification.model_dump(),
            room_measurements=request.room_measurements,
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
                "video_external_url": result.get("video_external_url", ""),
                "video_internal_url": result.get("video_internal_url", ""),
                "video_external_status": result.get("video_external_status", ""),
                "video_internal_status": result.get("video_internal_status", ""),
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
            "division": result.get("division", ""),
            "outdoor_spaces": result.get("outdoor_spaces", []),
            "key_rooms": result.get("key_rooms", []),
            "construction_standard": result.get("construction_standard"),
            "additional_preferences": result.get("additional_preferences"),
            "images": images,
            "prompt_used": result.get("prompt_used", ""),
            "created_at": result.get("created_at", ""),
            "video_external_url": result.get("video_external_url", ""),
            "video_internal_url": result.get("video_internal_url", ""),
            "video_external_status": result.get("video_external_status", ""),
            "video_internal_status": result.get("video_internal_status", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch shared generation: {str(e)}")


@router.post("/generate/floor-plan/room", response_model=GenerationImage)
async def regenerate_floor_plan_view(request: SingleFloorPlanViewRequest, user=Depends(verify_token)):
    try:
        spec = request.specification

        if spec and request.view_type in _FLOOR_PLAN_VIEW_RENDERERS:
            layout = await generate_floor_plan_layout(
                num_bedrooms=spec.num_bedrooms,
                num_bathrooms=spec.num_bathrooms,
                kitchen_type=spec.kitchen_type,
                extras=spec.extras,
                gross_area=spec.gross_area,
            )
            renderer = _FLOOR_PLAN_VIEW_RENDERERS[request.view_type]
            img_bytes = await renderer(layout)
        else:
            prompt = request.prompt or "Regenerate the floor plan view with the same specifications."
            img_bytes = await ai_service.generate_floor_plan_image(
                prompt,
                view_type=request.view_type or "floor_plan_main",
                overlay_language="en",
            )

        if not img_bytes:
            raise Exception("Failed to generate floor plan image.")
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


@router.get("/images/proxy")
async def proxy_image(url: str = Query(...)):
    """Proxy image requests to bypass browser CORS restrictions on Firebase Storage."""
    from app.db.firebase import settings
    bucket = settings.FIREBASE_STORAGE_BUCKET
    gcs_name = bucket.replace(".firebasestorage.app", ".appspot.com")
    allowed_prefixes = [
        f"https://storage.googleapis.com/{bucket}/",
        f"https://storage.googleapis.com/{gcs_name}/",
        f"https://firebasestorage.googleapis.com/v0/b/{bucket}/",
        f"https://firebasestorage.googleapis.com/v0/b/{gcs_name}/",
    ]
    if not any(url.startswith(p) for p in allowed_prefixes):
        raise HTTPException(status_code=400, detail="Invalid image URL origin")

    import httpx
    headers = {"User-Agent": "7G-House-Proxy/1.0"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/png")
        return Response(content=resp.content, media_type=content_type)


@router.get("/generation/{generation_id}/pdf")
async def download_generation_pdf(generation_id: str, lang: str = Query("en", pattern="^(en|fr)$"), user=Depends(verify_token)):
    """
    Build and stream a branded multi-page PDF for the given generation.
    Images are fetched server-side so there are no browser CORS issues.
    """
    from app.services.pdf_service import build_project_pdf, upload_pdf_to_storage
    from app.repositories.generation_repository import set_telegram_pdf_url
    import httpx

    user_id = user["uid"]
    is_admin = user.get("role") == "admin"

    try:
        result = await db_service.get_generation(generation_id, user_id, is_admin=is_admin)
        if not result:
            raise HTTPException(status_code=404, detail="Generation not found or access denied")

        client_name = result.get("client_name") or result.get("house_style") or "Project"
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in client_name)
        filename = f"7G_House_{safe_name}_Report.pdf"

        cached_pdf_url = result.get("telegram_pdf_url", "")
        if cached_pdf_url:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(cached_pdf_url, follow_redirects=True)
                    resp.raise_for_status()
                    return StreamingResponse(
                        iter([resp.content]),
                        media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                    )
            except Exception as e:
                logger.warning(f"download_generation_pdf: cached PDF fetch failed, rebuilding: {e}")

        pdf_buf = await build_project_pdf(result, lang=lang)
        if not pdf_buf:
            raise HTTPException(status_code=500, detail="Failed to generate PDF")

        try:
            pdf_url = await upload_pdf_to_storage(pdf_buf, generation_id)
            if pdf_url:
                await set_telegram_pdf_url(generation_id, pdf_url)
        except Exception as e:
            logger.warning(f"download_generation_pdf: failed to cache PDF: {e}")

        pdf_buf.seek(0)
        return StreamingResponse(
            pdf_buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.post("/generation/{generation_id}/pdf/upload")
async def upload_generation_pdf(generation_id: str, lang: str = Query("en", pattern="^(en|fr)$"), user=Depends(verify_token)):
    """
    Build a branded PDF, upload it to Firebase Storage, persist its URL,
    and return the public download URL.
    Used by the frontend Telegram quick-share flow.
    """
    from app.services.pdf_service import build_project_pdf, upload_pdf_to_storage
    from app.repositories.generation_repository import set_telegram_pdf_url

    user_id = user["uid"]
    is_admin = user.get("role") == "admin"

    try:
        result = await db_service.get_generation(generation_id, user_id, is_admin=is_admin)
        if not result:
            raise HTTPException(status_code=404, detail="Generation not found or access denied")

        pdf_buf = await build_project_pdf(result, lang=lang)
        if not pdf_buf:
            raise HTTPException(status_code=500, detail="Failed to generate PDF")

        pdf_url = await upload_pdf_to_storage(pdf_buf, generation_id)
        if not pdf_url:
            raise HTTPException(status_code=500, detail="Failed to upload PDF to storage")

        # Persist so the Telegram bot can reuse it without rebuilding
        await set_telegram_pdf_url(generation_id, pdf_url)

        return {"pdf_url": pdf_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF upload failed: {str(e)}")


@router.delete("/generation/{generation_id}/pdf")
async def delete_generation_pdf(generation_id: str, user=Depends(verify_token)):
    """
    Delete the cached PDF for a generation from Firebase Storage and clear
    the pdf_url field in Firestore.
    """
    from app.services.pdf_service import delete_pdf_from_storage
    from app.repositories.generation_repository import delete_generation_pdf as db_delete_pdf

    user_id = user["uid"]
    is_admin = user.get("role") == "admin"

    try:
        result = await db_service.get_generation(generation_id, user_id, is_admin=is_admin)
        if not result:
            raise HTTPException(status_code=404, detail="Generation not found or access denied")

        pdf_url = result.get("telegram_pdf_url", "")
        if not pdf_url:
            return {"ok": True, "message": "No PDF to delete"}

        await delete_pdf_from_storage(pdf_url)
        await db_delete_pdf(generation_id)

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF deletion failed: {str(e)}")

