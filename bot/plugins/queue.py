from pyrogram import Client, filters

@Client.on_message(filters.command("queue"))
async def queue_command(client, message):
    await message.reply_text(
        "📜 The queue is currently empty.\n\n"
        "🎵 Use /play <song name> to add music."
    )
