from pyrogram import Client, filters

@Client.on_message(filters.command("vskip"))
async def vskip_command(client, message):
    await message.reply_text(
        "⏭ Video skip system is under development."
    )
