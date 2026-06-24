from pyrogram import Client, filters
from pyrogram.enums import ChatType

from bot.utils import queue as q
from bot.utils.music import music


@Client.on_message(filters.command(["stop", "end"]))
async def stop_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /stop only works in groups.")
        return

    was_active = q.is_active(message.chat.id)
    # Clear queue FIRST so the stream-end callback (which fires as a side
    # effect of leave_call on some py-tgcalls versions) doesn't see a track
    # to advance to.
    q.clear(message.chat.id)

    if not was_active:
        await message.reply_text("ℹ️ Nothing was playing.")
        return

    try:
        await music.leave_call(message.chat.id)
    except Exception as exc:
        await message.reply_text(f"❌ Stop failed: {type(exc).__name__}: {exc}")
        return

    await message.reply_text("⏹️ Playback stopped and the queue has been cleared.")
