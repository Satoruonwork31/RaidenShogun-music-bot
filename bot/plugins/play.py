from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pytgcalls.types import AudioQuality, MediaStream

from bot.utils.music import music
from bot.utils.resolver import resolve


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
            "Supported sources:\n"
            "• YouTube (link or text search)\n"
            "• Spotify track link\n"
            "• Resso song link\n"
            "• SoundCloud track link\n\n"
            "Example:\n"
            "`/play Believer`\n"
            "`/play https://open.spotify.com/track/...`"
        )
        return

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
