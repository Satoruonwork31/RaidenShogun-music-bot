import asyncio
import os

from pyrogram import Client, filters

from bot.utils.downloader import (
    check_size_and_duration,
    download_video,
)
from bot.utils.player import _try_extract
from bot.utils.resolver import resolve_url


@Client.on_message(filters.command("video"))
async def video_command(client, message):
    if len(message.command) < 2:
        await message.reply_text(
            "📹 Usage: `/video <name or YouTube/SoundCloud/Spotify/Resso link>`\n\n"
            "I'll download the video (≤720p mp4) and send it here."
        )
        return

    query = " ".join(message.command[1:])
    status = await message.reply_text(f"🔍 Resolving: {query}")

    url, label = await resolve_url(query)
    if not url:
        await status.edit_text(f"❌ {label}")
        return

    await status.edit_text(f"ℹ️ Checking: {label}")
    # Duration is what gates us — it's returned regardless of selected format.
    probe = await asyncio.to_thread(_try_extract, url)
    title = (probe.get("title") if isinstance(probe, dict) else None) or label
    too_big = check_size_and_duration(probe or {})
    if too_big:
        await status.edit_text(f"❌ {too_big}")
        return

    await status.edit_text(f"⬇️ Downloading: {title}")
    try:
        path, info = await asyncio.to_thread(download_video, url)
    except Exception as exc:
        await status.edit_text(f"❌ Download failed: {type(exc).__name__}: {exc}")
        return

    duration = int(info.get("duration") or 0)
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    thumb = info.get("thumbnail") if isinstance(info, dict) else None

    try:
        await status.edit_text(f"📤 Uploading: {title}")
        await client.send_video(
            chat_id=message.chat.id,
            video=path,
            caption=f"🎬 {title}",
            duration=duration,
            width=width,
            height=height,
            thumb=thumb,
            supports_streaming=True,
            reply_to_message_id=message.id,
        )
        await status.delete()
    except Exception as exc:
        await status.edit_text(f"❌ Upload failed: {type(exc).__name__}: {exc}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
