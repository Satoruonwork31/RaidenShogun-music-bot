import logging
import os
import re

from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode

from bot.utils import queue as q
from bot.utils.np_ui import nowplaying_keyboard, render_for_chat
from bot.utils.playback import ensure_userbot_in_chat, play_track
from bot.utils.resolver import resolve

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

logger = logging.getLogger("RaidenShogun.play")

DOWNLOAD_DIR = "/tmp/raiden_downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _replied_media(message):
    """Return (media object, label) for a replied audio/voice/video message."""
    reply = message.reply_to_message
    if not reply:
        return None, None
    for attr in ("audio", "voice", "video", "video_note"):
        media = getattr(reply, attr, None)
        if media:
            label = (
                getattr(media, "file_name", None)
                or getattr(media, "title", None)
                or attr
            )
            return media, label
    document = reply.document
    if document and document.mime_type and (
        document.mime_type.startswith("audio/")
        or document.mime_type.startswith("video/")
    ):
        return document, document.file_name or "uploaded file"
    return None, None


def _replied_url(message):
    """First URL in the replied message's text or caption, or None."""
    reply = message.reply_to_message
    if not reply:
        return None
    body = reply.text or reply.caption or ""
    if not body:
        return None
    m = _URL_RE.search(str(body))
    return m.group(0) if m else None


def _requester_name(message) -> str:
    user = message.from_user
    if not user:
        return "someone"
    return user.first_name or user.username or str(user.id)


async def _do_play(client, message, *, is_video: bool):
    label_cmd = "/vplay" if is_video else "/play"
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(
            f"👥 The {label_cmd} command only works in groups with an active voice chat."
        )
        return

    replied_media, replied_label = _replied_media(message)
    # Reply-to-link: only used when no command args and no replied media,
    # so explicit args still win.
    replied_url = (
        _replied_url(message)
        if (len(message.command) < 2 and not replied_media)
        else None
    )

    if len(message.command) < 2 and not replied_media and not replied_url:
        await message.reply_text(
            f"🎵 Please provide a song name or link, or reply to an audio/video "
            f"message with {label_cmd}.\n\n"
            "Supported sources:\n"
            "• YouTube (link or text search)\n"
            "• Spotify track link\n"
            "• Resso song link\n"
            "• SoundCloud track link\n"
            "• Uploaded audio/voice/video (reply with the command)\n"
            "• Reply to any message containing a link with the command"
        )
        return

    if replied_media:
        status = await message.reply_text(f"⬇️ Downloading {replied_label}...")
        try:
            stream_url = await message.reply_to_message.download(
                file_name=os.path.join(
                    DOWNLOAD_DIR, f"{replied_media.file_unique_id}_"
                )
            )
            info = replied_label
        except Exception as exc:
            logger.exception("download of replied media failed")
            await status.edit_text(f"❌ Download failed: {exc}")
            return
    else:
        query = replied_url if replied_url else " ".join(message.command[1:])
        status = await message.reply_text(f"🔍 Resolving: {query}")
        logger.info("resolve(%r, video=%s) for chat=%s", query, is_video, message.chat.id)
        stream_url, info = await resolve(query, video=is_video)
        if not stream_url:
            logger.warning("resolve returned no stream_url for %r — %s", query, info)
            await status.edit_text(f"❌ {info}")
            return
        logger.info(
            "resolved %r → label=%r url_len=%s url_head=%s",
            query, info, len(stream_url or ""), (stream_url or "")[:80],
        )

    track = q.Track(
        stream_url=stream_url,
        title=info,
        requested_by=_requester_name(message),
        is_video=is_video,
    )

    # If something is already playing in this chat, just enqueue.
    if q.is_active(message.chat.id):
        position = q.enqueue(message.chat.id, track)
        await status.edit_text(
            f"➕ Added to queue at position {position}: {info}"
        )
        return

    # Fresh playback — make sure the assistant userbot is in the group.
    # It auto-leaves after each session, so we may need to invite it back.
    await status.edit_text("🤝 Preparing assistant…")
    ok, detail = await ensure_userbot_in_chat(client, message.chat.id)
    if not ok:
        await status.edit_text(f"❌ {detail}")
        return

    logger.info("calling play_track for chat=%s title=%r", message.chat.id, info)
    try:
        await play_track(message.chat.id, track)
    except Exception as exc:
        # TelegramServerError / RPCError subclasses carry .ID and .MESSAGE
        # — surface those so the operator sees CALL_OCCUPY_FAILED /
        # GROUPCALL_INVALID / etc. instead of the bare class name.
        exc_id = getattr(exc, "ID", None)
        exc_msg = getattr(exc, "MESSAGE", None)
        logger.exception(
            "play_track raised: type=%s id=%s message=%s repr=%r",
            type(exc).__name__, exc_id, exc_msg, exc,
        )
        ui_id = f" [{exc_id}]" if exc_id else ""
        await status.edit_text(
            f"❌ Playback failed: {type(exc).__name__}{ui_id}: {exc_msg or exc}"
        )
        return

    # Render the Now Playing card. Old short reply is gone — the
    # boxed UI doubles as the "we started" confirmation.
    try:
        await status.edit_text(
            render_for_chat(message.chat.id, track),
            parse_mode=ParseMode.HTML,
            reply_markup=nowplaying_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception as exc:
        # Rendering issues (e.g. an unsupported emoji tag on a fork) must
        # not kill playback. Fall back to a plain confirmation.
        logger.exception("now-playing render failed: %s", exc)
        icon = "🎬" if is_video else "🎵"
        await status.edit_text(f"{icon} Now Playing: {info}")
    logger.info("play_track returned cleanly for chat=%s", message.chat.id)


@Client.on_message(filters.command("play"))
async def play_command(client, message):
    await _do_play(client, message, is_video=False)
