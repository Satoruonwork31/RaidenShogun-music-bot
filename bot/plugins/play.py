from pyrogram import Client, filters

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

    await message.reply_text(
        f"🔍 Searching for: **{query}**\n\n"
        "⚠️ Music playback is not implemented yet."
    )
