import secrets

from pyrogram import Client, filters


@Client.on_message(filters.command("toss"))
async def toss_command(client, message):
    result = "Heads 🪙" if secrets.randbelow(2) == 0 else "Tails 🪙"
    await message.reply_text(f"🎲 {result}")
