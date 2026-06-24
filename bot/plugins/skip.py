from pyrogram import Client, filters
from pyrogram.enums import ChatType

from bot.utils import queue as q
from bot.utils.music import music
from bot.utils.playback import play_track


async def _skip(message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /skip only works in groups.")
        return

    if not q.is_active(message.chat.id):
        await message.reply_text("ℹ️ Nothing is playing right now.")
        return

    nxt = q.pop_next(message.chat.id)
    if nxt is None:
        # Queue exhausted — leave the call cleanly.
        try:
            await music.leave_call(message.chat.id)
        except Exception as exc:
            await message.reply_text(
                f"⏭️ Skipped — but leaving the call failed: {exc}"
            )
            return
        await message.reply_text("⏭️ Skipped. Queue is now empty — leaving the call.")
        return

    try:
        await play_track(message.chat.id, nxt)
    except Exception as exc:
        await message.reply_text(
            f"❌ Skip failed mid-switch: {type(exc).__name__}: {exc}"
        )
        return

    icon = "🎬" if nxt.is_video else "🎵"
    await message.reply_text(f"⏭️ Skipped. {icon} Now Playing: {nxt.title}")


@Client.on_message(filters.command("skip"))
async def skip_command(client, message):
    await _skip(message)
