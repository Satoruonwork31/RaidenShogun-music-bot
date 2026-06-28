"""Instagram auto-downloader — proxyless, cookies-enabled.

Inspired by an aiogram-flavored "send sticker → download → swap"
handler from another project. Reimplemented in Pyrogram/kurigram
for this bot. No proxy, no fallback chain — one direct yt-dlp
attempt, an Instagram mobile UA to maximise the chance of success,
and a per-URL file_id cache so re-shared links re-deliver instantly
without re-downloading.

Cookies: uses the existing `INSTAGRAM_COOKIES_FILE` master jar via
`bot.utils.player.cookies_for_url()`, which copies it to a tempfile
per request so yt-dlp's writeback can't degrade the master. Cookies
are required for IG in 2026 — anonymous requests from datacenter
IPs get "empty media response" every time.

Flow:
  1. URL matched (reel / p / tv / stories) → status message
  2. Cache hit? → send file_id, done.
  3. Download with yt-dlp (no cookies, no proxy, IG mobile UA,
     age_limit=100, format=best[ext=mp4]/best, 60s wall-clock cap)
  4. Send video via bot client, reply to the original message,
     caption: ✅ Delivered — <user mention>
  5. Cache the returned file_id by URL
  6. Delete the status message
  7. Any failure → status edited to a generic "couldn't download"
     line, then deleted after a short grace

Plays nice with bot/plugins/linksniffer.py: this handler runs in
group=1, marks the URL on `message.continue_propagation` short-
circuit by leaving it un-set after we've handled it, and we patch
linksniffer to early-return on Instagram URLs.
"""

import asyncio
import logging
import os
import re
import tempfile
from collections import OrderedDict

from yt_dlp import YoutubeDL

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

from bot.utils.player import cookies_for_url

logger = logging.getLogger("RaidenShogun.instagram")

# Match the URL shapes Instagram actually serves: reel/reels/p/tv/stories.
# Same shape as linksniffer's IG branch but standalone so this file is
# self-contained and doesn't import from another plugin.
_IG_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?"
    r"instagram\.com/(?:reel|reels|p|tv|stories)/[^\s\"<>?#]+[^\s\"<>]*",
    re.IGNORECASE,
)

# Instagram Android app UA — IG's web extractor consistently returns
# more usable formats when the request looks like a real mobile client.
# Same UA the inspiration handler used.
_IG_MOBILE_UA = (
    "Instagram 344.0.0.0.0 Android (33/13; 420dpi; 1080x2400; "
    "samsung; SM-S918B; dm3q; qcom; en_US; 605596538)"
)

# Per-URL file_id cache. Keeps the last N entries in insertion order
# and evicts the oldest when full. Lives in the bot process — wiped
# on restart, which is fine: re-downloading a stale URL costs ~3s.
_CACHE_MAX = 512
_file_id_cache: "OrderedDict[str, str]" = OrderedDict()

# Per-chat dedup window so two pastes of the same link in quick
# succession don't queue two downloads.
_recently_seen: "OrderedDict[tuple[int, str], float]" = OrderedDict()
_DEDUP_WINDOW_S = 8.0

# In-flight lock per chat — at most one IG download running per chat
# at a time. Prevents stampedes when someone pastes 5 reels in a row.
_chat_locks: dict[int, asyncio.Lock] = {}


def _cache_get(url: str) -> str | None:
    fid = _file_id_cache.get(url)
    if fid:
        _file_id_cache.move_to_end(url)
    return fid


def _cache_put(url: str, file_id: str) -> None:
    _file_id_cache[url] = file_id
    _file_id_cache.move_to_end(url)
    while len(_file_id_cache) > _CACHE_MAX:
        _file_id_cache.popitem(last=False)


def _seen_recently(chat_id: int, url: str) -> bool:
    loop = asyncio.get_running_loop()
    now = loop.time()
    key = (chat_id, url)
    # Evict expired entries lazily.
    while _recently_seen:
        oldest_key, oldest_at = next(iter(_recently_seen.items()))
        if now - oldest_at > _DEDUP_WINDOW_S:
            _recently_seen.popitem(last=False)
        else:
            break
    if key in _recently_seen and now - _recently_seen[key] < _DEDUP_WINDOW_S:
        return True
    _recently_seen[key] = now
    return False


def _normalise(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    # Strip Telegram-pasted trailing punctuation that isn't part of the URL.
    return url.rstrip(").,;]")


def _mention_html(user) -> str:
    if not user:
        return "someone"
    name = user.first_name or user.username or str(user.id)
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def _download_blocking(url: str, out_dir: str) -> str | None:
    """Run yt-dlp synchronously; return the first downloaded media path
    or None. Proxyless, cookies-via-tempfile, age_limit=100, IG mobile UA.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "http_headers": {"User-Agent": _IG_MOBILE_UA},
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "format": "best[ext=mp4]/best",
        "age_limit": 100,
        # ignoreerrors=True so yt-dlp prints errors instead of raising —
        # we detect failure by checking for downloaded files.
        "ignoreerrors": True,
    }
    # Tempfile copy of instagram_cookies.txt — yt-dlp will write its
    # post-request jar to the tempfile, master stays pristine.
    ck = cookies_for_url(url)
    if ck:
        opts["cookiefile"] = ck
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.info("instagram: yt-dlp raised %s: %s", type(exc).__name__, str(exc)[:200])
        return None
    # Find the first media file in out_dir.
    for name in sorted(os.listdir(out_dir)):
        if name.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
            return os.path.join(out_dir, name)
    return None


async def _download(url: str) -> str | None:
    """Async wrapper with a 60s wall-clock cap. Returns the path or None.
    Caller owns the temp directory lifetime.
    """
    tmp_dir = tempfile.mkdtemp(prefix="ig_dl_")
    try:
        path = await asyncio.wait_for(
            asyncio.to_thread(_download_blocking, url, tmp_dir),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.info("instagram: download timed out after 60s for %s", url)
        path = None
    if not path:
        # Clean the now-empty tmp dir — nothing to send.
        try:
            for n in os.listdir(tmp_dir):
                os.remove(os.path.join(tmp_dir, n))
            os.rmdir(tmp_dir)
        except OSError:
            pass
        return None
    return path


async def _delete_silently(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


# Runs in group=1, before linksniffer (group=2). If we match an IG URL
# we handle it here and linksniffer's IG branch is patched out, so no
# double-fire.
@Client.on_message(filters.text | filters.caption, group=1)
async def instagram_auto_download(client, message):
    if message.from_user and message.from_user.is_bot:
        return

    text = str(message.text or message.caption or "")
    if not text or text.lstrip().startswith("/"):
        return

    match = _IG_URL_RE.search(text)
    if not match:
        return

    url = _normalise(match.group(0))
    chat_id = message.chat.id if message.chat else 0

    if _seen_recently(chat_id, url):
        return

    logger.info(
        "instagram: matched url=%s chat=%s user=%s",
        url, chat_id, message.from_user.id if message.from_user else None,
    )

    mention = _mention_html(message.from_user)
    delivered_caption = f"✅ Delivered — {mention}"

    # Cache hit: re-deliver the same file_id, instant, no re-download.
    cached = _cache_get(url)
    if cached:
        try:
            await client.send_video(
                chat_id=chat_id,
                video=cached,
                caption=delivered_caption,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id,
                supports_streaming=True,
            )
            logger.info("instagram: cache hit, file_id served for %s", url)
            return
        except Exception as exc:
            # Stale file_id (asset deleted on Telegram side) — fall through
            # to a fresh download. Drop the bad cache entry.
            logger.info("instagram: cache file_id rejected (%s) — re-downloading", type(exc).__name__)
            _file_id_cache.pop(url, None)

    lock = _chat_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        status = None
        try:
            status = await message.reply_text(
                "📥 Downloading from Instagram…",
                quote=True,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.info("instagram: status reply failed, continuing without it")

        path = await _download(url)

        if not path:
            if status:
                try:
                    await status.edit_text(
                        "❌ Couldn't download that Instagram link."
                    )
                except Exception:
                    pass
                await asyncio.sleep(4)
                await _delete_silently(status)
            return

        try:
            sent = await client.send_video(
                chat_id=chat_id,
                video=path,
                caption=delivered_caption,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id,
                supports_streaming=True,
            )
            if sent and getattr(sent, "video", None):
                _cache_put(url, sent.video.file_id)
                logger.info("instagram: delivered + cached file_id for %s", url)
            else:
                logger.info("instagram: delivered (no file_id captured)")
        except Exception as exc:
            logger.warning("instagram: send_video failed: %s", type(exc).__name__)
            if status:
                try:
                    await status.edit_text("❌ Couldn't send that Instagram video.")
                except Exception:
                    pass
                await asyncio.sleep(4)
                await _delete_silently(status)
            return
        finally:
            # Always clean the tempdir.
            try:
                d = os.path.dirname(path)
                for n in os.listdir(d):
                    os.remove(os.path.join(d, n))
                os.rmdir(d)
            except OSError:
                pass

        # Success: drop the status message.
        if status:
            await _delete_silently(status)
