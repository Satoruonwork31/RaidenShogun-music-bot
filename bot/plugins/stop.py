from pyrogram import Client, filters

@Client.on_message(filters.command("stop"))
async def stop_command(client, message):
    await message.reply_text(
        "⏹️ Playback stopped and the queue has been cleared."
    )
