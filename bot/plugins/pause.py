from pyrogram import Client, filters

@Client.on_message(filters.command("pause"))
async def pause_command(client, message):
    await message.reply_text(
        "⏸️ Playback paused.\n\n"
        "Use /resume to continue."
    )
