import asyncio
import os

from pyrogram import Client, filters

from bot.utils.downloader import (
    check_size_and_duration,
    download_audio,
)
from bot.utils.player import YouTubeAuthRequiredError, _try_extract
from bot.utils.resolver import resolve_url


@Client.on_message(filters.command("song"))
async def song_command(client, message):
    if len(message.command) < 2:
        await message.reply_text(
            "🎵 Usage: `/song <song name or YouTube/Spotify/Resso/SoundCloud link>`\n\n"
            "I'll download the audio as an mp3 and send it here."
        )
        return

    query = " ".join(message.command[1:])
    status = await message.reply_text(f"🔍 Resolving: {query}")

    url, label = await resolve_url(query)
    if not url:
        await status.edit_text(f"❌ {label}")
        return

    await status.edit_text(f"ℹ️ Checking: {label}")
    try:
        probe = await asyncio.to_thread(_try_extract, url)
    except YouTubeAuthRequiredError as exc:
        await status.edit_text(YouTubeAuthRequiredError.USER_MESSAGE)
        return
    title = (probe.get("title") if isinstance(probe, dict) else None) or label
    too_big = check_size_and_duration(probe or {})
    if too_big:
        await status.edit_text(f"❌ {too_big}")
        return

    await status.edit_text(f"⬇️ Downloading: {title}")
    try:
        path, info = await asyncio.to_thread(download_audio, url)
    except Exception as exc:
        await status.edit_text(f"❌ Download failed: {type(exc).__name__}: {exc}")
        return

    duration = int(info.get("duration") or 0)
    performer = info.get("uploader") or info.get("channel") or "Unknown"
    thumb = info.get("thumbnail") if isinstance(info, dict) else None

    try:
        await status.edit_text(f"📤 Uploading: {title}")
        await client.send_audio(
            chat_id=message.chat.id,
            audio=path,
            caption=f"🎵 {title}",
            title=title,
            performer=performer,
            duration=duration,
            thumb=thumb,
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
