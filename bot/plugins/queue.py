from pyrogram import Client, filters
from pyrogram.enums import ChatType

from bot.utils import queue as q

# How many upcoming tracks to render in the message. Telegram's 4096-char
# limit makes a full render risky for long playlists; truncate and tell
# the user how many more are pending.
_MAX_RENDER = 15


def _line(idx: int, track: q.Track) -> str:
    icon = "🎬" if track.is_video else "🎵"
    return f"{idx}. {icon} {track.title} — by {track.requested_by}"


@Client.on_message(filters.command("queue"))
async def queue_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /queue only works in groups.")
        return

    current = q.now_playing(message.chat.id)
    upcoming = q.upcoming(message.chat.id)

    if not current and not upcoming:
        await message.reply_text(
            "📜 The queue is currently empty.\n\n"
            "🎵 Use /play <song name> to add music."
        )
        return

    lines = ["📜 **Queue**"]
    if current:
        icon = "🎬" if current.is_video else "🎵"
        lines.append(
            f"\n▶️ Now playing: {icon} {current.title} — by {current.requested_by}"
        )
    if upcoming:
        lines.append("\n⏭️ Up next:")
        for i, track in enumerate(upcoming[:_MAX_RENDER], start=1):
            lines.append(_line(i, track))
        extra = len(upcoming) - _MAX_RENDER
        if extra > 0:
            lines.append(f"… and {extra} more.")
    else:
        lines.append("\n(nothing else in the queue)")

    await message.reply_text("\n".join(lines))
