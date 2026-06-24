from pyrogram import Client, filters
from pyrogram.enums import ChatType

from bot.utils import queue as q
from bot.utils.music import music


@Client.on_message(filters.command("resume"))
async def resume_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /resume only works in groups.")
        return

    if not q.is_active(message.chat.id):
        await message.reply_text("ℹ️ Nothing is paused — use /play to start a song.")
        return

    try:
        await music.resume(message.chat.id)
    except Exception as exc:
        await message.reply_text(f"❌ Resume failed: {type(exc).__name__}: {exc}")
        return

    await message.reply_text("▶️ Playback resumed.")
