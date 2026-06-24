from pyrogram import Client, filters
from pyrogram.enums import ChatType

from bot.utils import queue as q
from bot.utils.music import music


@Client.on_message(filters.command("pause"))
async def pause_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /pause only works in groups.")
        return

    if not q.is_active(message.chat.id):
        await message.reply_text("ℹ️ Nothing is playing right now.")
        return

    try:
        await music.pause(message.chat.id)
    except Exception as exc:
        await message.reply_text(f"❌ Pause failed: {type(exc).__name__}: {exc}")
        return

    await message.reply_text("⏸️ Playback paused.\n\nUse /resume to continue.")
