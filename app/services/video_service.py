import os
import logging
import httpx
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

FAL_API_KEY = os.getenv("FAL_API_KEY", "")
FAL_MODEL_ID = "fal-ai/kling-video/v3/pro/image-to-video"
FAL_QUEUE_BASE = "https://queue.fal.run"
HEADERS = {
    "Authorization": f"Key {FAL_API_KEY}",
    "Content-Type": "application/json",
}


def _find_image(images: list[dict], *labels: str) -> str | None:
    for label in labels:
        for img in images:
            if img.get("label") == label:
                return img.get("url")
    for label in labels:
        for img in images:
            img_label = img.get("label") or ""
            if label in img_label:
                return img.get("url")
    return images[0]["url"] if images else None


def build_walkthrough_movie(
    images: list[dict],
    spec: dict,
    project_name: str = "",
    client_name: str = "",
) -> dict:
    """Build a fal.ai Kling video generation request from the generation data."""
    img_url = _find_image(images)
    bedrooms = spec.get("num_bedrooms", "X")
    bathrooms = spec.get("num_bathrooms", "Y")
    area = spec.get("gross_area", "Z")
    region = spec.get("region", "Centre")

    prompt = (
        f"A cinematic architectural walkthrough of a {bedrooms}-bedroom, "
        f"{bathrooms}-bathroom home in {region}, Cameroon. "
        f"Total area {area} square meters. "
        "Slow camera movement around the property, showcasing the building design, "
        "elevations, and surrounding landscape. Professional real-estate video style, "
        "warm golden lighting, high-end finish."
    )

    return {
        "start_image_url": img_url,
        "prompt": prompt,
        "duration": "10",
        "generate_audio": True,
        "aspect_ratio": "16:9",
        "negative_prompt": "blur, distort, and low quality",
        "cfg_scale": 0.5,
    }


async def submit_render(request: dict) -> str | None:
    """Submit a video generation job to fal.ai."""
    if not FAL_API_KEY:
        logger.error("FAL_API_KEY not set")
        return None

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}",
                headers=HEADERS,
                json=request,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            request_id = data.get("request_id")
            if request_id:
                logger.info(f"fal.ai video job submitted, request_id={request_id}")
                return request_id
            else:
                logger.error(f"Unexpected response: {data}")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error submitting video: {e.response.status_code} {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error submitting video: {e}")
            return None


async def get_render_status(job_id: str) -> dict:
    """Check the status of a fal.ai video job."""
    if not FAL_API_KEY:
        return {"status": "error", "message": "FAL_API_KEY not set"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}/requests/{job_id}/status",
                headers=HEADERS,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "unknown")

            if status == "COMPLETED":
                if data.get("error"):
                    return {"status": "error", "message": data["error"]}

                result_resp = await client.get(
                    f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}/requests/{job_id}",
                    headers=HEADERS,
                    timeout=15.0,
                )
                result_resp.raise_for_status()
                result_data = result_resp.json()
                video_url = result_data.get("video", {}).get("url", "")
                if video_url:
                    return {"status": "done", "url": video_url}
                else:
                    return {"status": "error", "message": "No video URL in response"}

            elif status in ("IN_QUEUE", "IN_PROGRESS"):
                return {"status": "processing"}

            else:
                return {"status": "error", "message": f"Unknown status: {status}"}

        except httpx.HTTPStatusError as e:
            return {"status": "error", "message": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
