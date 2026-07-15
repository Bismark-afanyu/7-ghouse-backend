import os
import io
import logging
import random
import string
import asyncio

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from app.services.pdf_service import build_project_pdf

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram features disabled")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

bot = None
if TOKEN:
    _request = HTTPXRequest(connection_pool_size=8)
    bot = Bot(token=TOKEN, request=_request)
else:
    logger.warning("Telegram bot not initialized (no token)")

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds


async def _send_with_retry(coro_func, *args, **kwargs):
    """Execute a Telegram API call with exponential backoff retry."""
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(f"Telegram send failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
    raise last_exception


def _get_db():
    from app.db.firebase import db
    return db


async def _get_rich_pdf(generation_data: dict) -> io.BytesIO | None:
    """Build a rich branded PDF using pdf_service (cover + image pages)."""
    try:
        buf = await build_project_pdf(generation_data)
        return buf
    except Exception as e:
        logger.warning(f"_get_rich_pdf: pdf_service failed: {e}")
        return None


async def set_telegram_link(uid: str, chat_id: int) -> bool:
    db = _get_db()
    if not db:
        return False
    try:
        db.collection("users").document(uid).update({"telegram_chat_id": chat_id})
        return True
    except Exception as e:
        logger.error(f"Failed to link telegram for {uid}: {e}")
        return False


async def get_telegram_chat_id(uid: str) -> int | None:
    db = _get_db()
    if not db:
        return None
    try:
        doc = db.collection("users").document(uid).get()
        if doc.exists:
            return doc.to_dict().get("telegram_chat_id")
    except Exception as e:
        logger.error(f"Failed to get telegram chat_id for {uid}: {e}")
    return None


async def remove_telegram_link(uid: str) -> bool:
    db = _get_db()
    if not db:
        return False
    try:
        db.collection("users").document(uid).update({"telegram_chat_id": None})
        return True
    except Exception as e:
        logger.error(f"Failed to remove telegram link for {uid}: {e}")
        return False


async def handle_start(update: Update) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text or ""
    parts = text.split()
    payload = parts[1] if len(parts) > 1 else ""

    if payload.startswith("share_"):
        share_token = payload.replace("share_", "", 1)
        await _send_shared_project(chat_id, share_token)
    else:
        await _send_welcome(chat_id)


async def handle_link(update: Update) -> None:
    if not bot:
        return
    from datetime import datetime, timezone
    chat_id = update.effective_chat.id
    code = "".join(random.choices(string.digits, k=6))
    
    db = _get_db()
    if db:
        try:
            db.collection("telegram_link_codes").document(code).set({
                "chat_id": chat_id,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to save link code: {e}")
            await bot.send_message(chat_id=chat_id, text="❌ Failed to generate link code. Please try again.")
            return

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔗 *Link your account*\n\n"
            f"Your linking code: `{code}`\n\n"
            f"Go to your 7G House account settings and enter this code to link your Telegram account."
        ),
        parse_mode="Markdown",
    )


async def _send_welcome(chat_id: int) -> None:
    if not bot:
        return
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "*Welcome to 7G House Bot!*\n\n"
            "I can help you access and share your construction projects.\n\n"
            "*Commands:*\n"
            "/start - Show this message\n"
            "/link - Link your 7G House account\n"
            "/help - Get help\n\n"
            "To view a shared project, use the share link from the 7G House web app."
        ),
        parse_mode="Markdown",
    )


async def _send_video_helper(chat_id: int, video_url: str, caption: str) -> None:
    if not bot or not video_url:
        return

    # Try downloading and sending as a file buffer (bypasses 20MB URL limit, up to 50MB limit)
    try:
        import httpx
        logger.info(f"Downloading video from {video_url} to send to Telegram...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(video_url, follow_redirects=True)
            resp.raise_for_status()
            video_bytes = io.BytesIO(resp.content)
            video_bytes.name = "walkthrough.mp4"
            await _send_with_retry(
                bot.send_video,
                chat_id=chat_id,
                video=video_bytes,
                caption=caption,
                parse_mode="Markdown",
            )
            return
    except Exception as e:
        logger.warning(f"Failed to download and send video by bytes: {e}. Falling back to URL.")

    # Fallback to direct URL sending (limited to 20MB by Telegram)
    try:
        await _send_with_retry(
            bot.send_video,
            chat_id=chat_id,
            video=video_url,
            caption=caption,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send video by URL: {e}")
        raise e


async def _send_shared_project(chat_id: int, share_token: str) -> None:
    if not bot:
        return
    from app.repositories.generation_repository import get_generation_by_share_token

    result = await get_generation_by_share_token(share_token)
    if not result:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Project not found or the share link has expired.",
        )
        return

    images = result.get("images", [])
    video_external_url = result.get("video_external_url", "")
    video_internal_url = result.get("video_internal_url", "")
    share_url = f"{FRONTEND_URL}/shared?token={share_token}"

    pdf_sent = False

    # 1. Try a pre-generated PDF stored on Firebase Storage
    pdf_url = result.get("telegram_pdf_url", "")
    if pdf_url:
        try:
            import httpx
            headers = {"User-Agent": "7G-House-Bot/1.0"}
            async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
                resp = await client.get(pdf_url, follow_redirects=True)
                resp.raise_for_status()
                pdf_bytes = io.BytesIO(resp.content)
                pdf_bytes.name = "Project_Report.pdf"
                await bot.send_document(
                    chat_id=chat_id,
                    document=pdf_bytes,
                    filename="Project_Report.pdf",
                    caption="📄 *7G House Project Report*",
                    parse_mode="Markdown",
                )
                pdf_sent = True
        except Exception as e:
            logger.warning(f"_send_shared_project: stored PDF failed, building fresh: {e}")

    # 2. Build a rich branded PDF on-the-fly
    if not pdf_sent:
        pdf_buf = await _get_rich_pdf(result)
        if pdf_buf:
            try:
                await bot.send_document(
                    chat_id=chat_id,
                    document=pdf_buf,
                    filename="Project_Report.pdf",
                    caption="📄 *7G House Project Report*",
                    parse_mode="Markdown",
                )
                pdf_sent = True
            except Exception as e:
                logger.warning(f"_send_shared_project: PDF send failed, falling back to images: {e}")

    # 3. Last-resort: send images individually
    if not pdf_sent:
        sent_count = 0
        for img in images[:8]:
            url = img.get("url", "")
            if not url:
                continue
            try:
                caption = img.get("label", "") if sent_count == 0 else None
                await bot.send_photo(chat_id=chat_id, photo=url, caption=caption)
                sent_count += 1
            except Exception as e:
                logger.warning(f"_send_shared_project: image send failed {url[:60]}: {e}")

        if len(images) > 8:
            await bot.send_message(
                chat_id=chat_id,
                text=f"📸 *+{len(images) - 8} more images* — view them in the browser: {share_url}",
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )

    # 4. Send videos next if present
    if video_external_url:
        try:
            await _send_video_helper(chat_id, video_external_url, "🎬 *Exterior Walkthrough*")
        except Exception as e:
            logger.warning(f"_send_shared_project: failed to send exterior video: {e}")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🎬 *Exterior Walkthrough*\n📹 [Open Video]({video_external_url})",
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            except Exception:
                pass

    if video_internal_url:
        try:
            await _send_video_helper(chat_id, video_internal_url, "🎬 *Interior Walkthrough*")
        except Exception as e:
            logger.warning(f"_send_shared_project: failed to send interior video: {e}")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🎬 *Interior Walkthrough*\n📹 [Open Video]({video_internal_url})",
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            except Exception:
                pass


async def send_project_to_chat(chat_id: int, generation_id: str) -> bool:
    if not bot:
        return False
    from app.repositories.generation_repository import get_generation_by_id_for_telegram

    result = await get_generation_by_id_for_telegram(generation_id)
    if not result:
        return False

    images = result.get("images", [])
    video_external_url = result.get("video_external_url", "")
    video_internal_url = result.get("video_internal_url", "")
    pdf_url = result.get("telegram_pdf_url", "")

    logger.info(
        f"Sending project {generation_id} to chat {chat_id}: "
        f"ext_video={'yes' if video_external_url else 'no'}, "
        f"int_video={'yes' if video_internal_url else 'no'}, "
        f"pdf={'yes' if pdf_url else 'no'}"
    )

    pdf_sent = False

    # 1. Try sending pre-generated PDF
    if pdf_url:
        try:
            import httpx
            headers = {"User-Agent": "7G-House-Bot/1.0"}
            async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
                resp = await client.get(pdf_url, follow_redirects=True)
                resp.raise_for_status()
                pdf_bytes = io.BytesIO(resp.content)
                pdf_bytes.name = "Project_Report.pdf"
                await _send_with_retry(
                    bot.send_document,
                    chat_id=chat_id,
                    document=pdf_bytes,
                    filename="Project_Report.pdf",
                    caption="📄 *7G House Project Report*",
                    parse_mode="Markdown",
                )
                pdf_sent = True
        except Exception as e:
            logger.warning(f"Failed to send pre-generated PDF after retries, falling back: {e}")

    # 2. Try sending rich PDF built on-the-fly
    if not pdf_sent:
        pdf_buf = await _get_rich_pdf(result)
        if pdf_buf:
            try:
                await _send_with_retry(
                    bot.send_document,
                    chat_id=chat_id,
                    document=pdf_buf,
                    filename="Project_Report.pdf",
                    caption="📄 *7G House Project Report*",
                    parse_mode="Markdown",
                )
                pdf_sent = True
            except Exception as e:
                logger.warning(f"Failed to send PDF after retries, falling back: {e}")

    # 3. Fallback: individual images if PDF failed
    if not pdf_sent:
        for img in images[:8]:
            url = img.get("url", "")
            if not url:
                continue
            try:
                await _send_with_retry(bot.send_photo, chat_id=chat_id, photo=url)
            except Exception as e:
                logger.warning(f"Failed to send image after retries: {e}")

    # 4. Send videos next if present
    if video_external_url:
        try:
            await _send_video_helper(chat_id, video_external_url, "🎬 *Exterior Walkthrough*")
        except Exception as e:
            logger.warning(f"Failed to send exterior video after retries: {e}")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🎬 *Exterior Walkthrough*\n📹 [Open Video]({video_external_url})",
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            except Exception:
                pass

    if video_internal_url:
        try:
            await _send_video_helper(chat_id, video_internal_url, "🎬 *Interior Walkthrough*")
        except Exception as e:
            logger.warning(f"Failed to send interior video after retries: {e}")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🎬 *Interior Walkthrough*\n📹 [Open Video]({video_internal_url})",
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            except Exception:
                pass

    return True
