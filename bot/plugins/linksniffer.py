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
from pyrogram.enums import ButtonStyle, ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.downloader import check_size_and_duration, download_audio, download_video
from bot.utils.player import YouTubeAuthRequiredError, _try_extract

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
    # Pinterest: pinterest.<tld>/pin/<id> (any country-code domain), plus
    # the pin.it/<shortcode> mobile-share redirector.
    r"|pinterest\.[a-z.]+/pin/[^\s\"<>/?#]+"
    r"|pin\.it/[^\s\"<>/?#]+"
    r")"
    r"[^\s\"<>]*",
    re.IGNORECASE,
)


_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^&]*&)*v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def _yt_video_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def _is_pinterest(url: str) -> bool:
    u = url.lower()
    return "pinterest." in u or "pin.it/" in u


_MP3_BUTTON_EMOJI_ID = "6030616017569320738"


def _quality_keyboard(vid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "480p",
                    callback_data=f"ydl|480|{vid}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    "720p",
                    callback_data=f"ydl|720|{vid}",
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [
                InlineKeyboardButton(
                    "1080p",
                    callback_data=f"ydl|1080|{vid}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    "MP3 Audio",
                    callback_data=f"ydl|mp3|{vid}",
                    style=ButtonStyle.PRIMARY,
                    icon_custom_emoji_id=_MP3_BUTTON_EMOJI_ID,
                ),
            ],
        ]
    )


def _has_video_stream(probe) -> bool:
    """True if yt-dlp's info dict actually contains a playable video.

    Pinterest image pins have no video formats — the extractor returns
    no direct url and only vcodec=='none' (or no) formats.
    """
    if not isinstance(probe, dict):
        return False
    if isinstance(probe.get("url"), str) and probe["url"].startswith("http"):
        return True
    for fmt in (probe.get("formats") or []):
        if isinstance(fmt, dict) and fmt.get("vcodec") not in (None, "none"):
            return True
    return False

async def _attempt(label, coro, timeout=60):
    """Run an upload coroutine with a forced cancellation timeout.

    asyncio.wait_for occasionally hasn't been firing on this pyrofork
    build's hung media-DC handshake — we wrap it in a task explicitly,
    schedule a cancel, and await the result so the cancel is honoured.
    """
    task = asyncio.create_task(coro)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        logger.info("link_sniffer: %s OK", label)
        return True
    except asyncio.TimeoutError:
        logger.warning("link_sniffer: %s timed out after %ss, cancelling", label, timeout)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return False
    except Exception:
        logger.exception("link_sniffer: %s raised", label)
        return False


def _pick_direct_url(info):
    """Pull a direct CDN URL out of yt-dlp's info dict, if available.

    For Instagram reels yt-dlp returns the resolved video URL straight on
    `info["url"]`. For multi-format sources (YouTube, etc.) the same data
    lives inside the `formats` list — take the last MP4-ish entry as a
    reasonable "best".
    """
    if not isinstance(info, dict):
        return None
    direct = info.get("url")
    if isinstance(direct, str) and direct.startswith("http"):
        return direct
    formats = info.get("formats")
    if isinstance(formats, list):
        for fmt in reversed(formats):
            if not isinstance(fmt, dict):
                continue
            if fmt.get("vcodec") == "none":
                continue
            u = fmt.get("url")
            if isinstance(u, str) and u.startswith("http"):
                return u
    return None


async def _try_uploads(bot_client, chat_id, reply_to_id, path, title,
                       duration, width, height, direct_url=None):
    """Try multiple upload code paths. Returns True on success.

    Order matters: the URL-based bot.send_video does not require a
    bot-side upload at all (Telegram fetches the URL server-side), so it
    sidesteps the documented bot.send_video hang on this pyrofork build.
    """
    # Path 0: bot.send_video with a remote URL. Cheapest path — no upload.
    if direct_url:
        if await _attempt(
            "bot.send_video[URL]",
            bot_client.send_video(
                chat_id=chat_id, video=direct_url, caption=title[:1024],
                duration=duration, width=width, height=height,
                supports_streaming=True, reply_to_message_id=reply_to_id,
            ),
        ):
            return True
    # Path 1: bot client send_video — local upload (often hangs).
    if await _attempt(
        "bot.send_video[FILE]",
        bot_client.send_video(
            chat_id=chat_id, video=path, caption=title[:1024],
            duration=duration, width=width, height=height,
            supports_streaming=True, reply_to_message_id=reply_to_id,
        ),
    ):
        return True
    # Path 2: bot client send_document (different code path internally).
    if await _attempt(
        "bot.send_document",
        bot_client.send_document(
            chat_id=chat_id, document=path, caption=title[:1024],
            reply_to_message_id=reply_to_id,
        ),
    ):
        return True
    # Path 3: userbot client send_video — the assistant userbot account
    # doesn't share the bot-client hang. Works only if the userbot is
    # already a member of this chat (otherwise resolve_peer KeyError's).
    try:
        from bot.client import userbot as _ub
        if await _attempt(
            "userbot.send_video",
            _ub.send_video(
                chat_id=chat_id, video=path, caption=title[:1024],
                duration=duration, width=width, height=height,
                supports_streaming=True,
            ),
        ):
            return True
    except Exception:
        logger.exception("link_sniffer: userbot path errored")
    return False


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


# Wide filter on purpose. The earlier compound filter
#   (filters.text | filters.caption) & ~filters.via_bot & ~filters.command([...])
# was silently rejecting messages — pyrofork was loading the handler but
# never dispatching to it on plain URL pastes. Drop the filter to bare
# text-or-caption and do every other check inside the function body so
# the path is easy to trace from the log.
@Client.on_message(filters.text | filters.caption, group=2)
async def link_sniffer(client, message):
    text_raw = str(message.text or message.caption or "")
    logger.info(
        "link_sniffer entered chat=%s user=%s text_head=%r",
        message.chat.id if message.chat else None,
        message.from_user.id if message.from_user else None,
        text_raw[:60],
    )

    # Bots/services shouldn't trigger us, neither should empty text or our
    # own commands (avoid /play <url> double-processing).
    if message.from_user and message.from_user.is_bot:
        return
    if not text_raw or text_raw.lstrip().startswith("/"):
        return
    text = text_raw

    match = _URL_RE.search(text)
    if not match:
        return

    url = _normalise(match.group(0))
    chat_id = message.chat.id

    # YouTube links → ask for quality; the actual download happens in the
    # callback handler below. Pinterest/Instagram fall through to the
    # original auto-download path (single quality, no choice to make).
    yt_id = _yt_video_id(url)
    if yt_id:
        caption = (
            '<tg-emoji emoji-id="5866262183385501783">🎬</tg-emoji> '
            "Pick a quality:"
        )
        try:
            await message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=_quality_keyboard(yt_id),
                quote=True,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("link_sniffer: posting quality picker failed")
        return

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

        is_pin = _is_pinterest(url)

        # video=True so yt-dlp picks a video format (not bestaudio). Without
        # this, the resolved info["url"] is the audio stream, which Telegram
        # then renders as an audio file when send_video[URL] fetches it.
        # Pinterest uses the same video=True path — its extractor returns a
        # video stream for video pins and nothing usable for image pins.
        try:
            probe = await asyncio.to_thread(_try_extract, url, None, video=True)
        except YouTubeAuthRequiredError:
            await status.edit_text(YouTubeAuthRequiredError.USER_MESSAGE)
            return
        except Exception as exc:
            if is_pin:
                # Pinterest intermittently serves fake 404s to yt-dlp as an
                # anti-scraping measure — a known unfixable upstream issue.
                # Give an honest message rather than the generic failure.
                logger.warning("link_sniffer: Pinterest extraction failed: %s", exc)
                await status.edit_text(
                    "❌ Pinterest blocked this request — their anti-bot "
                    "measures are inconsistent. Try again later or download "
                    "manually."
                )
                return
            raise

        # Pinterest image pins have no video stream — say so clearly instead
        # of falling into the generic "couldn't download" path.
        if is_pin and not _has_video_stream(probe):
            await status.edit_text("🖼️ That's an image pin — nothing to download.")
            return

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
        direct_url = _pick_direct_url(probe) or _pick_direct_url(info)
        logger.info(
            "link_sniffer: starting upload path=%s title=%r direct_url=%s",
            path, title, "yes" if direct_url else "no",
        )
        sent_ok = await _try_uploads(client, chat_id, message.id, path, title,
                                     duration, width, height,
                                     direct_url=direct_url)
        if not sent_ok:
            await status.edit_text(
                f"❌ Downloaded but Telegram upload kept timing out.\n"
                f"Title: {title}"
            )
            return
        try:
            await status.delete()
        except Exception:
            pass

    except Exception as exc:
        logger.exception("link_sniffer failed for %s", url)
        if status is not None:
            try:
                if _is_pinterest(url):
                    await status.edit_text(
                        "❌ Pinterest blocked this request — their anti-bot "
                        "measures are inconsistent. Try again later or download "
                        "manually."
                    )
                    return
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


# Picker callback: (chat_id, message_id) we've already started downloading for.
_PICK_DONE: set[tuple[int, int]] = set()


@Client.on_callback_query(filters.regex(r"^ydl\|(480|720|1080|mp3)\|([A-Za-z0-9_-]{11})$"))
async def ydl_callback(client, cq):
    parts = cq.data.split("|")
    quality, vid = parts[1], parts[2]
    msg = cq.message
    if msg is None or msg.chat is None:
        await cq.answer("Lost the message — paste the link again.", show_alert=True)
        return

    key = (msg.chat.id, msg.id)
    if key in _PICK_DONE:
        await cq.answer("Already processing.", show_alert=False)
        return
    _PICK_DONE.add(key)

    is_audio = quality == "mp3"
    label = "MP3 Audio" if is_audio else f"{quality}p"
    await cq.answer(f"Downloading {label}…")

    status_box = (
        f'<tg-emoji emoji-id="5866262183385501783">🎬</tg-emoji> {label}\n'
        "\n"
        "╭──────────────╮\n"
        '<tg-emoji emoji-id="5818687127000452892">🔍</tg-emoji> ʀᴇsᴏʟᴠɪɴɢ sᴛʀᴇᴀᴍ...\n'
        '<tg-emoji emoji-id="5443127283898405358">⬇️</tg-emoji> ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ\n'
        "╰──────────────╯"
    )

    url = f"https://www.youtube.com/watch?v={vid}"
    path = None
    reply_to_id = msg.reply_to_message.id if msg.reply_to_message else None
    try:
        try:
            await msg.edit_text(status_box, parse_mode=ParseMode.HTML, reply_markup=None)
        except Exception:
            pass

        try:
            probe = await asyncio.to_thread(_try_extract, url, None, video=not is_audio)
        except YouTubeAuthRequiredError:
            await msg.edit_text(YouTubeAuthRequiredError.USER_MESSAGE)
            return

        title = (probe.get("title") if isinstance(probe, dict) else None) or "video"
        too_big = check_size_and_duration(probe or {})
        if too_big:
            await msg.edit_text(f"❌ {too_big}")
            return

        if is_audio:
            path, info = await asyncio.to_thread(download_audio, url)
        else:
            path, info = await asyncio.to_thread(download_video, url, quality)

        info = info or {}
        await msg.edit_text(f"📤 Uploading: {title}")

        if is_audio:
            await client.send_audio(
                chat_id=msg.chat.id,
                audio=path,
                caption=f"🎵 {title}",
                title=title,
                performer=info.get("uploader") or info.get("channel") or "Unknown",
                duration=int(info.get("duration") or 0),
                reply_to_message_id=reply_to_id,
            )
        else:
            await client.send_video(
                chat_id=msg.chat.id,
                video=path,
                caption=f"🎬 {title} ({label})",
                duration=int(info.get("duration") or 0),
                width=int(info.get("width") or 0),
                height=int(info.get("height") or 0),
                supports_streaming=True,
                reply_to_message_id=reply_to_id,
            )
        try:
            await msg.delete()
        except Exception:
            pass

    except Exception as exc:
        logger.exception("ydl_callback failed vid=%s quality=%s", vid, quality)
        try:
            await msg.edit_text(f"❌ Failed: {type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
        _PICK_DONE.discard(key)
