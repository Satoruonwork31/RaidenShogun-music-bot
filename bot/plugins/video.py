from pyrogram import Client, filters

@Client.on_message(filters.command("video"))
async def video_command(client, message):
    await message.reply_text(
        "📹 Video download system is under development."
    )
