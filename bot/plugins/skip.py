from pyrogram import Client, filters

@Client.on_message(filters.command("skip"))
async def skip_command(client, message):
    await message.reply_text(
        "⏭️ Skipped to the next track."
    )
