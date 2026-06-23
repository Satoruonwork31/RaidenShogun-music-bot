from pyrogram import Client, filters

@Client.on_message(filters.command("vplay"))
async def vplay_command(client, message):
    await message.reply_text(
        "🎬 Video playback system is under development."
    )
