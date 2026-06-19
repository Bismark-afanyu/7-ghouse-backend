import os
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth_middleware import verify_token
from app.repositories.generation_repository import set_telegram_pdf_url
from app.services.telegram_bot import (
    bot,
    handle_start,
    handle_link,
    set_telegram_link,
    get_telegram_chat_id,
    send_project_to_chat,
    remove_telegram_link,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telegram"])

# Simple in-memory rate limiter
_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window


def _check_rate_limit(uid: str) -> bool:
    """Check if user has exceeded rate limit. Returns True if allowed."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    _rate_limits[uid] = [t for t in _rate_limits[uid] if t > cutoff]
    if len(_rate_limits[uid]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    _rate_limits[uid].append(now)
    return True


class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None
    edited_message: dict | None = None
    channel_post: dict | None = None
    inline_query: dict | None = None
    callback_query: dict | None = None


class LinkRequest(BaseModel):
    code: str


class SendProjectRequest(BaseModel):
    generation_id: str


class PdfUrlRequest(BaseModel):
    generation_id: str
    pdf_url: str


@router.post("/telegram/webhook")
async def telegram_webhook(update: TelegramUpdate):
    from telegram import Update as TgUpdate

    tg_update = TgUpdate.de_json(update.model_dump(), bot)

    try:
        if tg_update.message and tg_update.message.text:
            text = tg_update.message.text.strip()
            if text.startswith("/start"):
                await handle_start(tg_update)
            elif text.startswith("/link"):
                await handle_link(tg_update)
            elif text.startswith("/help"):
                from app.services.telegram_bot import _send_welcome
                await _send_welcome(tg_update.effective_chat.id)
            else:
                await bot.send_message(
                    chat_id=tg_update.effective_chat.id,
                    text="Unknown command. Use /help to see available commands.",
                )
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")

    return {"ok": True}


@router.post("/telegram/link")
async def link_telegram(request: LinkRequest, user=Depends(verify_token)):
    code = request.code.strip()
    chat_id = None
    
    from app.db.firebase import db
    if db:
        doc_ref = db.collection("telegram_link_codes").document(code)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            chat_id = data.get("chat_id")
            created_at = data.get("created_at")
            doc_ref.delete()

            if created_at:
                try:
                    code_time = datetime.fromisoformat(created_at)
                    if code_time.tzinfo is None:
                        code_time = code_time.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - code_time > timedelta(minutes=5):
                        raise HTTPException(status_code=400, detail="Link code has expired. Please request a new one.")
                except (ValueError, TypeError):
                    pass

    if not chat_id:
        raise HTTPException(status_code=400, detail="Invalid or expired linking code.")

    uid = user["uid"]
    success = await set_telegram_link(uid, chat_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to link account.")

    await bot.send_message(
        chat_id=chat_id,
        text="✅ *Account linked successfully!*\n\nYou can now receive your projects directly here.",
        parse_mode="Markdown",
    )

    return {"ok": True}


@router.post("/telegram/send")
async def send_to_telegram(request: SendProjectRequest, user=Depends(verify_token)):
    uid = user["uid"]

    if not _check_rate_limit(uid):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    chat_id = await get_telegram_chat_id(uid)

    if not chat_id:
        raise HTTPException(status_code=400, detail="Telegram account not linked. Use /link in the bot first.")

    try:
        success = await send_project_to_chat(chat_id, request.generation_id)
    except Exception as e:
        logger.error(f"send_to_telegram: unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send project to Telegram. Please try again.")

    if not success:
        raise HTTPException(status_code=404, detail="Project not found or images could not be sent.")

    return {"ok": True}


@router.post("/telegram/set-pdf-url")
async def set_pdf_url(request: PdfUrlRequest, user=Depends(verify_token)):
    uid = user["uid"]
    ok = await set_telegram_pdf_url(request.generation_id, request.pdf_url)
    if not ok:
        raise HTTPException(status_code=404, detail="Generation not found.")
    return {"ok": True}


@router.post("/telegram/unlink")
async def unlink_telegram(user=Depends(verify_token)):
    uid = user["uid"]
    await remove_telegram_link(uid)
    return {"ok": True}


@router.get("/telegram/status")
async def telegram_status(user=Depends(verify_token)):
    uid = user["uid"]
    chat_id = await get_telegram_chat_id(uid)
    return {"linked": chat_id is not None}
