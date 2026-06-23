import os

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pytgcalls.types import AudioQuality, MediaStream

from bot.utils.music import music
from bot.utils.resolver import resolve

DOWNLOAD_DIR = "/tmp/raiden_downloads"


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


@Client.on_message(filters.command("play"))
async def play_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(
            "👥 The /play command only works in groups with an active voice chat."
        )
        return

    replied_media, replied_label = _replied_media(message)

    if len(message.command) < 2 and not replied_media:
        await message.reply_text(
            "🎵 Please provide a song name or link, or reply to an audio/video message with /play.\n\n"
            "Supported sources:\n"
            "• YouTube (link or text search)\n"
            "• Spotify track link\n"
            "• Resso song link\n"
            "• SoundCloud track link\n"
            "• Uploaded audio/voice/video (reply with /play)"
        )
        return

    if replied_media:
        status = await message.reply_text(f"⬇️ Downloading {replied_label}...")
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            stream_url = await message.reply_to_message.download(
                file_name=os.path.join(DOWNLOAD_DIR, f"{replied_media.file_unique_id}_")
            )
            info = replied_label
        except Exception as exc:
            await status.edit_text(f"❌ Download failed: {exc}")
            return
    else:
        query = " ".join(message.command[1:])
        status = await message.reply_text(f"🔍 Resolving: {query}")
        stream_url, info = await resolve(query)
        if not stream_url:
            await status.edit_text(f"❌ {info}")
            return

    try:
        await music.play(
            message.chat.id,
            MediaStream(stream_url, audio_parameters=AudioQuality.HIGH),
        )
    except Exception as exc:
        await status.edit_text(f"❌ Playback failed: {exc}")
        return

    await status.edit_text(f"🎵 Now Playing: {info}")
