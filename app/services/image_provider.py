"""Provider-agnostic image generation.

Selects the image engine via the IMAGE_PROVIDER env var so engines can be
A/B-compared on identical prompts without code changes:

  IMAGE_PROVIDER=gemini        -> gemini-2.5-flash-image via Vertex AI (default, current production)
  IMAGE_PROVIDER=nano-banana-2 -> Gemini 3.1 Flash Image ("Nano Banana 2") via Vertex AI
  IMAGE_PROVIDER=gpt           -> GPT Images 2.5 via the OpenAI API (flare variant)

IMAGE_MODEL overrides the model id for whichever provider is active.
All functions raise on failure and return PNG/JPEG bytes on success; retry,
backoff and per-view logging stay in ai_service so every provider shares the
same resilience behaviour.
"""
import asyncio
import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_MODELS = ("gemini", "google")
NANO_BANANA_MODELS = ("nano-banana-2", "nano_banana_2", "nano-banana")
GPT_MODELS = ("gpt", "gpt-2.5", "gpt2.5", "openai")

DEFAULT_MODEL_BY_PROVIDER = {
    "gemini": "gemini-2.5-flash-image",
    "nano-banana-2": "gemini-3.1-flash-image",
    "gpt": "gpt-image-2.5-flare",
}

CALL_TIMEOUT_S = float(os.environ.get("IMAGE_CALL_TIMEOUT", "180"))


def get_provider() -> str:
    if _RUNTIME_OVERRIDE:
        return _RUNTIME_OVERRIDE["provider"]
    raw = os.environ.get("IMAGE_PROVIDER", "gemini").strip().lower()
    if raw in GEMINI_MODELS:
        return "gemini"
    if raw in NANO_BANANA_MODELS:
        return "nano-banana-2"
    if raw in GPT_MODELS:
        return "gpt"
    logger.warning("Unknown IMAGE_PROVIDER %r; falling back to gemini", raw)
    return "gemini"


def get_image_model() -> str:
    if _RUNTIME_OVERRIDE and _RUNTIME_OVERRIDE.get("model"):
        return _RUNTIME_OVERRIDE["model"]
    explicit = os.environ.get("IMAGE_MODEL", "").strip()
    if explicit:
        return explicit
    return DEFAULT_MODEL_BY_PROVIDER[get_provider()]


def describe() -> str:
    return f"provider={get_provider()} model={get_image_model()}"


# ── Runtime engine switching (admin UI) ──────────────────────────────────────
# Presets let the admin switch engines from the UI without a redeploy.
# In-memory: resets to the env-configured engine on process restart.
ENGINE_PRESETS: dict[str, dict] = {
    "gemini": {"provider": "gemini", "model": "gemini-2.5-flash-image"},
    "nano-banana-2": {"provider": "nano-banana-2", "model": "gemini-3.1-flash-image"},
    "flare": {"provider": "gpt", "model": "gpt-image-2.5-flare",
              "size": "1536x1024", "quality": "high"},
    "sunburst": {"provider": "gpt", "model": "gpt-image-2.5-sunburst",
                 "size": "1536x1024", "quality": "high"},
}

_RUNTIME_OVERRIDE: Optional[dict] = None


def set_engine(choice: str) -> dict:
    """Activate an engine preset at runtime. Raises on unknown choice."""
    global _RUNTIME_OVERRIDE
    key = (choice or "").strip().lower()
    if key == "default":
        _RUNTIME_OVERRIDE = None
    elif key in ENGINE_PRESETS:
        _RUNTIME_OVERRIDE = dict(ENGINE_PRESETS[key])
    else:
        raise ValueError(f"Unknown engine choice: {choice!r}")
    return get_active_config()


def get_active_config() -> dict:
    if _RUNTIME_OVERRIDE:
        cfg = dict(_RUNTIME_OVERRIDE)
        cfg["choice"] = next(
            (k for k, v in ENGINE_PRESETS.items() if v == _RUNTIME_OVERRIDE), "custom")
        cfg["source"] = "runtime"
        return cfg
    return {
        "choice": "default",
        "provider": get_provider(),
        "model": get_image_model(),
        "size": _openai_size() if get_provider() == "gpt" else None,
        "quality": _openai_quality() if get_provider() == "gpt" else None,
        "source": "env",
    }


def _openai_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set (required for IMAGE_PROVIDER=gpt)")
    return api_key


def _mime_to_ext(mime_type: str) -> str:
    mime = (mime_type or "").lower()
    if "png" in mime:
        return "png"
    if "webp" in mime:
        return "webp"
    return "jpg"


def _openai_size() -> str:
    if _RUNTIME_OVERRIDE and _RUNTIME_OVERRIDE.get("size"):
        return _RUNTIME_OVERRIDE["size"]
    size = os.environ.get("OPENAI_IMAGE_SIZE", "1536x1024").strip()
    return size if size in ("1024x1024", "1536x1024", "1024x1536", "auto") else "1536x1024"


def _openai_quality() -> str:
    if _RUNTIME_OVERRIDE and _RUNTIME_OVERRIDE.get("quality"):
        return _RUNTIME_OVERRIDE["quality"]
    quality = os.environ.get("OPENAI_IMAGE_QUALITY", "high").strip().lower()
    return quality if quality in ("low", "medium", "high", "auto") else "high"


async def _generate_gemini_family(
    prompt_text: str,
    ref_image: Optional[bytes],
    ref_mime_type: str,
    view_label: str,
) -> bytes:
    from google.genai import types
    from app.services.genai_client import get_genai_client

    client = get_genai_client()
    contents_parts = [types.Part(text=prompt_text)]
    if ref_image:
        contents_parts.append(
            types.Part(inline_data=types.Blob(mime_type=ref_mime_type, data=ref_image))
        )

    def call():
        return client.models.generate_content(
            model=get_image_model(),
            contents=types.Content(parts=contents_parts, role="user"),
            config=types.GenerateContentConfig(response_modalities=["Image", "Text"]),
        )

    response = await asyncio.wait_for(asyncio.to_thread(call), timeout=CALL_TIMEOUT_S)

    candidates = getattr(response, "candidates", None) or []
    parts = getattr(getattr(candidates[0] if candidates else None, "content", None), "parts", None) or []
    for part in parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            return part.inline_data.data

    text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]
    detail = text_parts[:1] if text_parts else "(none)"
    raise RuntimeError(f"no_image_in_response: {detail}")


async def _generate_gpt(
    prompt_text: str,
    ref_image: Optional[bytes],
    ref_mime_type: str,
    view_label: str,
) -> bytes:
    # Raw HTTP against the OpenAI images API: gpt-image-2.5 rejects the
    # `response_format` parameter (b64_json is the only and default output).
    import httpx

    api_key = _openai_key()
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = get_image_model()
    size = _openai_size()
    quality = _openai_quality()
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as client:
        if ref_image:
            # Reference-image conditioning via multipart images/edits; falls
            # back to plain generation if the edit call is rejected.
            try:
                fname = f"reference.{_mime_to_ext(ref_mime_type)}"
                mime = "image/png" if fname.endswith("png") else (
                    "image/webp" if fname.endswith("webp") else "image/jpeg")
                r = await client.post(
                    f"{base_url}/images/edits",
                    headers=headers,
                    files={"image": (fname, ref_image, mime)},
                    data={"model": model, "prompt": prompt_text, "n": "1",
                          "size": size, "quality": quality},
                )
                r.raise_for_status()
            except httpx.HTTPStatusError as edit_err:
                logger.warning(
                    "[ImageProvider] %s: images.edit failed (%s); retrying as plain generate",
                    view_label, edit_err,
                )
                r = await client.post(
                    f"{base_url}/images/generations",
                    headers=headers,
                    json={"model": model, "prompt": prompt_text, "n": 1,
                          "size": size, "quality": quality},
                )
                r.raise_for_status()
        else:
            r = await client.post(
                f"{base_url}/images/generations",
                headers=headers,
                json={"model": model, "prompt": prompt_text, "n": 1,
                      "size": size, "quality": quality},
            )
            r.raise_for_status()

    payload = r.json()
    data = payload.get("data") or []
    b64 = (data[0] or {}).get("b64_json") if data else None
    if not b64:
        raise RuntimeError(f"no_image_in_response: {str(payload)[:200]}")
    return base64.b64decode(b64)


async def generate_image_once(
    prompt_text: str,
    ref_image: Optional[bytes] = None,
    ref_mime_type: str = "image/jpeg",
    view_label: str = "",
) -> bytes:
    """One image-generation attempt. Raises on failure; returns image bytes."""
    provider = get_provider()
    logger.info("[ImageProvider] %s: %s", view_label, describe())
    if provider == "gpt":
        return await _generate_gpt(prompt_text, ref_image, ref_mime_type, view_label)
    return await _generate_gemini_family(prompt_text, ref_image, ref_mime_type, view_label)
