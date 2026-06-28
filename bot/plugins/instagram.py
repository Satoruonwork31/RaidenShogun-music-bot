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

from pathlib import Path

from yt_dlp import YoutubeDL

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaPhoto, InputMediaVideo

from bot.utils.media_api_client import fetch_via_api, is_enabled as media_api_enabled
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
# Value is a list of (file_id, kind) pairs preserving carousel order;
# kind is "video" or "photo" so the cached replay rebuilds the same
# send_video / send_photo / send_media_group shape it was stored as.
_CACHE_MAX = 512
_file_id_cache: "OrderedDict[str, list[tuple[str, str]]]" = OrderedDict()

# Extension → Telegram media kind. The spec for instagram.py is exactly
# this set; other extensions are ignored when collecting download output.
_VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv")
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _kind_for(path: str) -> str | None:
    """Return 'video', 'photo', or None for unsupported extensions."""
    low = path.lower()
    if low.endswith(_VIDEO_EXTS):
        return "video"
    if low.endswith(_PHOTO_EXTS):
        return "photo"
    return None

# Per-chat dedup window so two pastes of the same link in quick
# succession don't queue two downloads.
_recently_seen: "OrderedDict[tuple[int, str], float]" = OrderedDict()
_DEDUP_WINDOW_S = 8.0

# In-flight lock per chat — at most one IG download running per chat
# at a time. Prevents stampedes when someone pastes 5 reels in a row.
_chat_locks: dict[int, asyncio.Lock] = {}


def _cache_get(url: str) -> list[tuple[str, str]] | None:
    items = _file_id_cache.get(url)
    if items:
        _file_id_cache.move_to_end(url)
    return items


def _cache_put(url: str, items: list[tuple[str, str]]) -> None:
    if not items:
        return
    _file_id_cache[url] = items
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


class _YDLLogger:
    """Bridge yt-dlp's logger contract onto our bot logger so we can
    quiet yt-dlp's stderr noise (quiet=True) but still capture its real
    error lines. Without this, `quiet=True + ignoreerrors=True` swallows
    failures entirely and the operator sees "Couldn't download" with no
    way to tell apart cookies-missing / login-wall / extractor-broken /
    network failure.
    """
    def debug(self, msg):
        if not msg.startswith("[debug]"):
            self.info(msg)
    def info(self, msg):
        logger.info("instagram[yt-dlp]: %s", msg.rstrip())
    def warning(self, msg):
        logger.warning("instagram[yt-dlp]: %s", msg.rstrip())
    def error(self, msg):
        logger.warning("instagram[yt-dlp] ERROR: %s", msg.rstrip())


def _classify_ydl_error(text: str) -> str | None:
    """Map a yt-dlp error string to a short reason code used by the
    handler to pick a user-facing message. Returns None when we don't
    have a more specific story than "generic download failure".
    """
    low = text.lower()
    if "empty media response" in low or "login_required" in low or "rate-limit" in low:
        return "cookies"
    if "video unavailable" in low or "this content isn" in low or "404" in low:
        return "unavailable"
    if "private" in low and "account" in low:
        return "private"
    return None


def _download_blocking(url: str, out_dir: str) -> tuple[list[str], str | None]:
    """Run yt-dlp synchronously; return (paths, reason).

    paths: ALL downloaded media files in out_dir (sorted by filename so
    carousel order is preserved). Empty list = failure.
    reason: short classification of why the download failed (None on
    success, or when failure cause isn't recognised). The handler uses
    this to pick a more useful user-facing message than the generic
    "Couldn't download".
    """
    captured_errors: list[str] = []

    class _Capture(_YDLLogger):
        def error(self, msg):
            captured_errors.append(msg)
            super().error(msg)

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
        # ignoreerrors=True so yt-dlp returns instead of raising — we
        # detect failure by checking for downloaded files and inspect
        # captured_errors for the real reason.
        "ignoreerrors": True,
        "logger": _Capture(),
    }
    # Tempfile copy of instagram_cookies.txt — yt-dlp will write its
    # post-request jar to the tempfile, master stays pristine.
    ck = cookies_for_url(url)
    if ck:
        opts["cookiefile"] = ck
    else:
        logger.warning(
            "instagram: no cookies for %s — INSTAGRAM_COOKIES_FILE unset "
            "or path missing on disk. IG blocks datacenter IPs without "
            "a logged-in cookies jar; the download is likely to fail.",
            url,
        )
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.info("instagram: yt-dlp raised %s: %s", type(exc).__name__, str(exc)[:200])
        return [], _classify_ydl_error(str(exc))
    # Collect ALL media files (videos + images), sorted by name for
    # carousel order. A carousel whose first item is a photo previously
    # tripped the video-only filter and reported total failure.
    found: list[str] = []
    for name in sorted(os.listdir(out_dir)):
        low = name.lower()
        if low.endswith(_VIDEO_EXTS) or low.endswith(_PHOTO_EXTS):
            found.append(os.path.join(out_dir, name))
    if found:
        return found, None
    # No files but no raised exception either — yt-dlp ate the error.
    # Look at the captured error strings to classify.
    reason = None
    for err in captured_errors:
        reason = _classify_ydl_error(err)
        if reason:
            break
    return [], reason


async def _download(url: str) -> tuple[list[str], str | None]:
    """Async wrapper. Tries the external media API first (if configured),
    falls back to in-process yt-dlp. Returns (paths, reason) — empty
    paths means failure, reason classifies why for the user-facing
    message. Caller owns the temp directory lifetime.
    """
    tmp_dir = tempfile.mkdtemp(prefix="ig_dl_")

    # External media API first — when configured. Unset = silently skip.
    if media_api_enabled():
        try:
            api_paths = await fetch_via_api(url, Path(tmp_dir))
        except Exception:
            logger.exception("instagram: media_api raised — falling back to yt-dlp")
            api_paths = []
        if api_paths:
            logger.info("instagram: served via media API: %d file(s)", len(api_paths))
            return [str(p) for p in api_paths], None

    # In-process yt-dlp fallback (also the only path when API is disabled).
    reason: str | None = None
    try:
        paths, reason = await asyncio.wait_for(
            asyncio.to_thread(_download_blocking, url, tmp_dir),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.info("instagram: download timed out after 60s for %s", url)
        paths = []
        reason = "timeout"
    if not paths:
        try:
            for n in os.listdir(tmp_dir):
                os.remove(os.path.join(tmp_dir, n))
            os.rmdir(tmp_dir)
        except OSError:
            pass
        return [], reason
    return paths, reason


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

    # Cache hit: re-deliver the same file_ids in the same shape they
    # were stored as (single send_video / send_photo, or media group).
    cached = _cache_get(url)
    if cached:
        try:
            if len(cached) == 1:
                fid, kind = cached[0]
                if kind == "photo":
                    await client.send_photo(
                        chat_id=chat_id,
                        photo=fid,
                        caption=delivered_caption,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=message.id,
                    )
                else:
                    await client.send_video(
                        chat_id=chat_id,
                        video=fid,
                        caption=delivered_caption,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=message.id,
                        supports_streaming=True,
                    )
            else:
                media = []
                for i, (fid, kind) in enumerate(cached):
                    cap = delivered_caption if i == 0 else None
                    pm = ParseMode.HTML if i == 0 else None
                    if kind == "photo":
                        media.append(InputMediaPhoto(media=fid, caption=cap, parse_mode=pm))
                    else:
                        media.append(InputMediaVideo(media=fid, caption=cap, parse_mode=pm))
                await client.send_media_group(
                    chat_id=chat_id,
                    media=media,
                    reply_to_message_id=message.id,
                )
            logger.info("instagram: cache hit, %d file_id(s) served for %s", len(cached), url)
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

        paths, reason = await _download(url)

        if not paths:
            user_msg = {
                "cookies": (
                    "🍪 Instagram needs a login to serve this from the bot's "
                    "IP. The owner must set INSTAGRAM_COOKIES_FILE to a "
                    "valid cookies.txt exported from a logged-in browser."
                ),
                "private": "🔒 That post is from a private account.",
                "unavailable": "❌ That post is gone or geo-blocked.",
                "timeout": "⌛ Instagram timed out — try again in a moment.",
            }.get(reason, "❌ Couldn't download that Instagram link.")
            if status:
                try:
                    await status.edit_text(user_msg)
                except Exception:
                    pass
                await asyncio.sleep(6)
                await _delete_silently(status)
            return

        try:
            # Drop any files with unsupported extensions; spec restricts
            # to the 8 video+image types. _download_blocking already
            # filters, but the media-API path may include other ones.
            typed_paths: list[tuple[str, str]] = []
            for p in paths:
                k = _kind_for(p)
                if k:
                    typed_paths.append((p, k))
            if not typed_paths:
                # Treat "downloaded nothing supported" the same as a
                # download failure — same error UX, no new states.
                raise RuntimeError("no supported media in download")

            cache_entries: list[tuple[str, str]] = []

            if len(typed_paths) == 1:
                p, kind = typed_paths[0]
                if kind == "photo":
                    sent = await client.send_photo(
                        chat_id=chat_id,
                        photo=p,
                        caption=delivered_caption,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=message.id,
                    )
                    if sent and getattr(sent, "photo", None):
                        cache_entries.append((sent.photo.file_id, "photo"))
                else:
                    sent = await client.send_video(
                        chat_id=chat_id,
                        video=p,
                        caption=delivered_caption,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=message.id,
                        supports_streaming=True,
                    )
                    if sent and getattr(sent, "video", None):
                        cache_entries.append((sent.video.file_id, "video"))
            else:
                media = []
                for i, (p, kind) in enumerate(typed_paths):
                    cap = delivered_caption if i == 0 else None
                    pm = ParseMode.HTML if i == 0 else None
                    if kind == "photo":
                        media.append(InputMediaPhoto(media=p, caption=cap, parse_mode=pm))
                    else:
                        media.append(InputMediaVideo(
                            media=p, caption=cap, parse_mode=pm,
                            supports_streaming=True,
                        ))
                sent_list = await client.send_media_group(
                    chat_id=chat_id,
                    media=media,
                    reply_to_message_id=message.id,
                )
                for i, m in enumerate(sent_list or []):
                    expected_kind = typed_paths[i][1] if i < len(typed_paths) else None
                    if expected_kind == "photo" and getattr(m, "photo", None):
                        cache_entries.append((m.photo.file_id, "photo"))
                    elif expected_kind == "video" and getattr(m, "video", None):
                        cache_entries.append((m.video.file_id, "video"))

            if cache_entries and len(cache_entries) == len(typed_paths):
                _cache_put(url, cache_entries)
                logger.info("instagram: delivered + cached %d file_id(s) for %s", len(cache_entries), url)
            else:
                logger.info("instagram: delivered (cache skipped: got %d file_id(s) for %d item(s))",
                            len(cache_entries), len(typed_paths))
        except Exception as exc:
            logger.warning("instagram: send failed: %s", type(exc).__name__)
            if status:
                try:
                    await status.edit_text("❌ Couldn't send that Instagram video.")
                except Exception:
                    pass
                await asyncio.sleep(4)
                await _delete_silently(status)
            return
        finally:
            # Always clean the tempdir — same listdir+remove guarantee as
            # before, just iterated over every file in the download.
            for p in paths:
                try:
                    d = os.path.dirname(p)
                    if not d or not os.path.isdir(d):
                        continue
                    for n in os.listdir(d):
                        try:
                            os.remove(os.path.join(d, n))
                        except OSError:
                            pass
                    try:
                        os.rmdir(d)
                    except OSError:
                        pass
                except OSError:
                    pass

        # Success: drop the status message.
        if status:
            await _delete_silently(status)
