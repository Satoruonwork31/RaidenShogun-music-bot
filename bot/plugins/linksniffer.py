"""Passive YouTube / Instagram link auto-downloader.

If a non-command message contains a YouTube or Instagram link, the bot
downloads the media via yt-dlp (using the same client-fallback chain as
/video) and posts it back in the same chat. Works in groups AND DMs.

Per-chat dedup: the same URL is only processed once per chat to dodge
re-trigger loops if someone forwards the bot's own upload back into the
chat. Cap is best-effort, in-memory.

The hard size/duration caps from bot.utils.downloader.check_size_and_duration
apply (currently 20 minutes / 1.5 GB).
"""

import asyncio
import logging
import os
import re

from pyrogram import Client, filters

from bot.utils.downloader import check_size_and_duration, download_video
from bot.utils.player import _try_extract

logger = logging.getLogger("RaidenShogun.linksniffer")

# A pragmatic URL matcher. Doesn't try to be exhaustive — just covers the
# shapes people actually paste.
_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:"
    # YouTube watch, shorts, live, embed; youtu.be short links.
    r"youtube\.com/(?:watch\?[^\s\"<>]+|shorts/[^\s\"<>/?]+|live/[^\s\"<>/?]+|embed/[^\s\"<>/?]+)"
    r"|youtu\.be/[^\s\"<>/?#]+"
    # Instagram reels, posts, IGTV.
    r"|instagram\.com/(?:reel|reels|p|tv)/[^\s\"<>/?#]+"
    r")"
    r"[^\s\"<>]*",
    re.IGNORECASE,
)

# Per-chat URL-recently-seen set. Trimmed to RECENT_CAP entries each.
_RECENT: dict[int, list[str]] = {}
_RECENT_CAP = 30

# Per-chat "currently downloading" guard so a spammed chat doesn't stack
# 50 yt-dlp jobs in parallel.
_BUSY: set[int] = set()
_BUSY_LOCK = asyncio.Lock()


def _normalise(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return "https://" + url
    return url


def _seen_recently(chat_id: int, url: str) -> bool:
    bucket = _RECENT.setdefault(chat_id, [])
    if url in bucket:
        return True
    bucket.append(url)
    if len(bucket) > _RECENT_CAP:
        del bucket[: len(bucket) - _RECENT_CAP]
    return False


# Run AFTER command handlers (group=0) and AFTER the broadcast chat tracker
# (group=-1). group=2 means: command plugins win first, this fires only if
# nobody else consumed the event. The `~filters.command(...)` guard belt-and-
# braces against /play <url> double-processing.
@Client.on_message(
    (filters.text | filters.caption)
    & ~filters.via_bot
    & ~filters.command(["play", "vplay", "cplay", "song", "video", "broadcast"]),
    group=2,
)
async def link_sniffer(client, message):
    # Defensive — bots/services shouldn't trigger us.
    if message.from_user and message.from_user.is_bot:
        return

    text = str(message.text or message.caption or "")
    if not text or text.lstrip().startswith("/"):
        return

    match = _URL_RE.search(text)
    if not match:
        return

    url = _normalise(match.group(0))
    chat_id = message.chat.id

    if _seen_recently(chat_id, url):
        return

    async with _BUSY_LOCK:
        if chat_id in _BUSY:
            return
        _BUSY.add(chat_id)

    status = None
    path = None
    try:
        status = await message.reply_text(
            "📥 Detected a link — pulling it down…",
            quote=True,
            disable_web_page_preview=True,
        )

        probe = await asyncio.to_thread(_try_extract, url)
        too_big = check_size_and_duration(probe or {})
        if too_big:
            await status.edit_text(f"❌ {too_big}")
            return

        title = (
            (probe.get("title") if isinstance(probe, dict) else None) or "video"
        )

        await status.edit_text(f"⬇️ Downloading: {title}")
        path, info = await asyncio.to_thread(download_video, url)

        duration = int((info or {}).get("duration") or 0)
        width = int((info or {}).get("width") or 0)
        height = int((info or {}).get("height") or 0)
        # yt-dlp gives `thumbnail` as a remote URL — pyrofork's send_video
        # tries to open that as a LOCAL path and FileNotFoundError's. Drop
        # the thumb entirely; Telegram will autogenerate from the video.
        # (If you ever want one, aiohttp-download it first to a tmp path.)
        await status.edit_text(f"📤 Uploading: {title}")
        await client.send_video(
            chat_id=chat_id,
            video=path,
            caption=title[:1024],
            duration=duration,
            width=width,
            height=height,
            supports_streaming=True,
            reply_to_message_id=message.id,
        )
        try:
            await status.delete()
        except Exception:
            pass

    except Exception as exc:
        logger.exception("link_sniffer failed for %s", url)
        if status is not None:
            try:
                await status.edit_text(
                    f"❌ Auto-download failed: {type(exc).__name__}: {exc}"
                )
            except Exception:
                pass
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
        async with _BUSY_LOCK:
            _BUSY.discard(chat_id)
