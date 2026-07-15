import os
import asyncio
import logging
import subprocess
import tempfile
import httpx
import uuid
from urllib.parse import urlparse

from dotenv import load_dotenv
from google.genai import types
from google.cloud import storage

from app.services.genai_client import get_genai_client

load_dotenv()

logger = logging.getLogger(__name__)

VEO_MODEL = os.environ.get("VEO_MODEL", "google/veo-3.1-generate-001").strip()


def _get_veo_client():
    return get_genai_client()


def _find_image(images: list[dict], *labels: str) -> str | None:
    """Find the best matching image URL by label priority."""
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


def build_external_walkthrough_movie(
    images: list[dict],
    spec: dict,
    project_name: str = "",
    client_name: str = "",
) -> tuple[str | None, str]:
    """Return (image_url, prompt) for an exterior walkaround video."""
    img_url = _find_image(images, "3D Exterior", "Elevations", "3D Top-Down View")
    bedrooms = spec.get("num_bedrooms", "X")
    bathrooms = spec.get("num_bathrooms", "Y")
    area = spec.get("gross_area", "Z")
    region = spec.get("region", "Centre")

    prompt = (
        f"A cinematic exterior architectural walkaround of a {bedrooms}-bedroom, "
        f"{bathrooms}-bathroom home in {region}, Cameroon. "
        f"Total area {area} square meters. "
        "Slow camera orbit around the property, showcasing the full building exterior, "
        "elevations, roof, and surrounding landscape. Professional real-estate video style, "
        "warm golden lighting, high-end finish."
    )

    return img_url, prompt


def build_internal_walkthrough_movie(
    images: list[dict],
    spec: dict,
    project_name: str = "",
    client_name: str = "",
) -> tuple[str | None, str]:
    """Return (image_url, prompt) for an interior top-down walkthrough video."""
    img_url = _find_image(images, "3D Top-Down View", "Ground Floor (Top-Down)", "Upper Floor (Top-Down)")
    bedrooms = spec.get("num_bedrooms", "X")
    bathrooms = spec.get("num_bathrooms", "Y")
    area = spec.get("gross_area", "Z")
    region = spec.get("region", "Centre")

    prompt = (
        f"A cinematic top-down flyover of a {bedrooms}-bedroom, "
        f"{bathrooms}-bathroom home in {region}, Cameroon. "
        f"Total area {area} square meters. "
        "Smooth aerial camera gliding above the floor plan, "
        "showcasing the full interior layout, room arrangement, and spatial flow. "
        "Professional real-estate video style, warm ambient lighting, high-end finish."
    )

    return img_url, prompt


async def submit_veo_render(img_url: str, prompt: str) -> str | None:
    """
    Submit a video generation job to Google Veo and return the operation name.

    The operation name acts as the job ID and is stored in Firestore
    so the /status endpoint can poll it later.
    """
    try:
        client = _get_veo_client()
    except RuntimeError as e:
        logger.error(f"Cannot create Veo client: {e}")
        return None

    # Fetch the image bytes from the URL
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(img_url)
            resp.raise_for_status()
            image_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg")
            if "png" in content_type:
                mime_type = "image/png"
            elif "webp" in content_type:
                mime_type = "image/webp"
            else:
                mime_type = "image/jpeg"
    except Exception as e:
        logger.error(f"Failed to download source image from {img_url}: {e}")
        return None

    logger.info(f"Fetched source image ({len(image_bytes)} bytes, {mime_type}) from {img_url}")

    # Submit to Veo — this is a long-running operation
    image = types.Image(image_bytes=image_bytes, mime_type=mime_type)
    operation = None
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            operation = await asyncio.to_thread(
                client.models.generate_videos,
                model=VEO_MODEL,
                prompt=prompt,
                image=image,
                config=types.GenerateVideosConfig(
                    aspect_ratio="16:9",
                    number_of_videos=1,
                ),
            )
            break
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or getattr(e, "code", None) == 429 or getattr(e, "status_code", None) == 429:
                if "prepayment credits are depleted" in err_msg.lower() or "quota exhausted" in err_msg.lower():
                    logger.error(f"Veo billing exhausted: {e}")
                    raise RuntimeError("Billing exhausted")
                    
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"Veo quota exceeded (attempt {attempt}/{max_retries}); retrying in {backoff}s…")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Veo submission failed after {max_retries} attempts (model={VEO_MODEL}, url={img_url[:80]}): {e}")
                    raise RuntimeError(f"Rate limit exceeded: {e}")
            else:
                logger.error(f"Veo submission failed (model={VEO_MODEL}, url={img_url[:80]}): {e}")
                raise RuntimeError(f"API Error: {e}")

    logger.info(f"Veo operation submitted: name={operation.name}")
    return operation.name


FFMPEG_BIN: str | None = None
for _candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", os.path.expanduser("~/bin/ffmpeg")):
    if os.path.isfile(_candidate):
        FFMPEG_BIN = _candidate
        break


async def _apply_video_watermark(video_bytes: bytes) -> bytes:
    """Apply a '7G House' text watermark overlay at bottom-right of the video."""
    if FFMPEG_BIN is None:
        logger.warning("ffmpeg not found — skipping video watermark")
        return video_bytes

    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "app", "assets", "logo.jpeg"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        inp = os.path.join(tmpdir, "in.mp4")
        out = os.path.join(tmpdir, "out.mp4")
        with open(inp, "wb") as f:
            f.write(video_bytes)

        watermark_path = None
        if os.path.exists(logo_path):
            watermark_path = logo_path

        if watermark_path:
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", inp,
                "-i", watermark_path,
                "-filter_complex",
                "[1:v]scale=60:-1[logo];[0:v][logo]overlay=W-w-20:H-h-20:format=auto,drawtext=text='7G House':fontsize=18:fontcolor=white@0.5:x=W-tw-80:y=H-th-30",
                "-c:a", "copy",
                out,
            ]
        else:
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", inp,
                "-vf", "drawtext=text='7G House':fontsize=18:fontcolor=white@0.5:x=W-tw-20:y=H-th-20",
                "-c:a", "copy",
                out,
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"ffmpeg watermark failed (code {proc.returncode}): {stderr.decode(errors='replace')[:300]}")
            return video_bytes

        with open(out, "rb") as f:
            watermarked = f.read()

        logger.info(f"Video watermark applied ({len(video_bytes)} → {len(watermarked)} bytes)")
        return watermarked


async def _compress_video(video_bytes: bytes, max_size: int = 48 * 1024 * 1024) -> bytes:
    """Compress video if it exceeds max_size (48MB). Returns compressed or original bytes."""
    if len(video_bytes) <= max_size:
        return video_bytes

    if FFMPEG_BIN is None:
        logger.warning("ffmpeg not found on system — skipping video compression")
        return video_bytes

    target_fs = max_size - 1_000_000
    with tempfile.TemporaryDirectory() as tmpdir:
        inp = os.path.join(tmpdir, "in.mp4")
        out = os.path.join(tmpdir, "out.mp4")
        with open(inp, "wb") as f:
            f.write(video_bytes)

        cmd = [
            FFMPEG_BIN, "-y",
            "-i", inp,
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "medium",
            "-fs", str(target_fs),
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            out,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"ffmpeg compression failed (code {proc.returncode}): {stderr.decode(errors='replace')[:300]}")
            return video_bytes

        with open(out, "rb") as f:
            compressed = f.read()

        if len(compressed) > len(video_bytes):
            logger.info(f"ffmpeg made video larger ({len(video_bytes)} → {len(compressed)}), keeping original")
            return video_bytes

        logger.info(f"Video compressed {len(video_bytes)} → {len(compressed)} bytes ({len(video_bytes) / 1024 / 1024:.1f}M → {len(compressed) / 1024 / 1024:.1f}M)")
        return compressed


def _download_from_gcs(gcs_uri: str, project: str = "g-house-d458c") -> bytes:
    """Download bytes from a GCS URI (gs://bucket/path or https://storage.googleapis.com/...)."""
    if gcs_uri.startswith("gs://"):
        parsed = urlparse(gcs_uri)
        bucket_name = parsed.netloc
        blob_path = parsed.path.lstrip("/")
    elif "storage.googleapis.com" in gcs_uri:
        parts = gcs_uri.split("/")
        try:
            idx = parts.index("storage.googleapis.com")
            bucket_name = parts[idx + 1]
            blob_path = "/".join(parts[idx + 2:])
        except (ValueError, IndexError):
            raise ValueError(f"Cannot parse storage.googleapis.com URI: {gcs_uri}")
    else:
        raise ValueError(f"Unrecognized GCS URI format: {gcs_uri}")

    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.download_as_bytes()


async def poll_veo_render(
    operation_name: str,
    generation_id: str,
    video_type: str,
) -> tuple[str, str | None, str | None]:
    """
    Poll a Veo operation and, if complete, upload the video to Firebase Storage.

    Returns:
        ("done", video_url, None)       — generation succeeded and video is uploaded
        ("processing", None, None)      — still in progress
        ("error", None, message)        — generation failed with error message
    """
    try:
        client = _get_veo_client()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        msg = f"Veo polling error for {operation_name}: {e}\n{tb}"
        logger.error(msg)
        return "error", None, f"Veo polling error for {operation_name}: {e}"

    try:
        operation_obj = types.GenerateVideosOperation(name=operation_name)
        operation = await asyncio.to_thread(
            client.operations.get,
            operation_obj,
        )

        if not operation.done:
            logger.info(f"Veo operation {operation_name} still processing")
            return "processing", None, None

        # Retrieve the generated video
        response = operation.response
        generated_videos = getattr(response, "generated_videos", None)

        if not generated_videos:
            msg = f"Veo operation {operation_name} done but no videos in response"
            logger.error(msg)
            return "error", None, msg

        video_obj = generated_videos[0].video

        # The video might be returned directly as bytes (Developer API) or via GCS URI (Vertex AI)
        video_bytes = getattr(video_obj, "video_bytes", None)
        
        if video_bytes:
            logger.info(f"Veo operation {operation_name} returned video_bytes directly ({len(video_bytes)} bytes)")
        else:
            gcs_uri = getattr(video_obj, "uri", None)
            if not gcs_uri:
                msg = f"Veo operation {operation_name} done but video has no GCS URI or video_bytes"
                logger.error(msg)
                return "error", None, msg
            logger.info(f"Downloading Veo video from GCS: {gcs_uri}")
            video_bytes = await asyncio.to_thread(_download_from_gcs, gcs_uri)

        # Apply 7G House watermark overlay
        video_bytes = await _apply_video_watermark(video_bytes)

        # Compress if over 48MB (Telegram's 50MB limit with headroom)
        video_bytes = await _compress_video(video_bytes)

        # Upload to Firebase Storage
        from app.services.storage_service import upload_file
        filename = f"video_{video_type}_{uuid.uuid4().hex}.mp4"
        result = await upload_file(
            file_bytes=bytes(video_bytes),
            user_id="system",
            generation_id=generation_id,
            filename=filename,
            content_type="video/mp4",
        )

        video_url = result["url"]
        logger.info(f"Veo video uploaded for generation {generation_id} ({video_type}): {video_url}")
        return "done", video_url, None

    except Exception as e:
        import traceback; msg = f"Veo polling error for {operation_name}: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        return "error", None, msg
