from pyrogram import Client, filters
from bot.utils.player import search_youtube, get_audio_stream
from bot.utils.music import music
from pytgcalls.types import MediaStream, AudioQuality

@Client.on_message(filters.command("play"))
async def play_command(client, message):
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

    await music.play(
        message.chat.id,
        MediaStream(
            stream_url,
            audio_parameters=AudioQuality.HIGH
        )
    )

    await message.reply_text(
        f"🎵 Now Playing: {query}"
    )
