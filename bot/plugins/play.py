from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pytgcalls.types import AudioQuality, MediaStream

from bot.utils.music import music
from bot.utils.player import get_audio_stream, search_youtube


@Client.on_message(filters.command("play"))
async def play_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(
            "👥 The /play command only works in groups with an active voice chat."
        )
        return

    if len(message.command) < 2:
        await message.reply_text(
            "🎵 Please provide a song name or link.\n\n"
            "Example:\n"
            "`/play Believer`\n"
            "`/play https://youtu.be/example`"
        )
        return

    query = " ".join(message.command[1:])

    url = search_youtube(query)
    if not url:
        await message.reply_text("❌ No results found.")
        return

    stream_url = get_audio_stream(url)
    if not stream_url:
        await message.reply_text("❌ Could not extract an audio stream for that result.")
        return

    try:
        await music.play(
            message.chat.id,
            MediaStream(stream_url, audio_parameters=AudioQuality.HIGH),
        )
    except Exception as exc:
        await message.reply_text(f"❌ Playback failed: {exc}")
        return

    await message.reply_text(f"🎵 Now Playing: {query}")
