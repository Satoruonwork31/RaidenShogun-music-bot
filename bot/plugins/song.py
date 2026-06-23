from pyrogram import Client, filters

@Client.on_message(filters.command("song"))
async def song_command(client, message):
    await message.reply_text(
        "🎵 Song download system is under development."
    )
