"""/purge — bulk message deletion for group admins.

Three modes (auto-detected from args):
  • Reply, no args     → delete replied msg .. command msg (inclusive)
  • /purge <n>         → delete the last n messages + the command
  • /purge <n> min     → delete everything from the last n minutes

Structural pattern mirrors bot/plugins/ban.py. Bot-permission check
inspects can_delete_messages SPECIFICALLY on the bot's own privileges.

IMPORTANT tz note: pyrofork's message.date is a NAIVE datetime
(datetime.fromtimestamp(ts), local time) in this version — confirmed
against pyrogram/utils.timestamp_to_datetime. So the time-window cutoff
is computed with a naive datetime.now(); using datetime.now(timezone.utc)
would raise on the naive/aware comparison.
"""

from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType

_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)

# Telegram per-call delete cap and our own safety cap.
_DELETE_BATCH = 100
_MAX_PER_CALL = 200

_MIN_WORDS = ("min", "mins", "minute", "minutes", "m")


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


async def _bot_can_delete(client, chat_id) -> bool:
    try:
        me = await client.get_me()
        member = await client.get_chat_member(chat_id, me.id)
    except Exception:
        return False
    if member.status == ChatMemberStatus.OWNER:
        return True
    privs = getattr(member, "privileges", None)
    return bool(privs and getattr(privs, "can_delete_messages", False))


async def _delete_ids(client, chat_id, ids: list[int]) -> None:
    """Delete message ids in batches of 100 (Telegram per-call cap)."""
    for i in range(0, len(ids), _DELETE_BATCH):
        batch = ids[i:i + _DELETE_BATCH]
        try:
            await client.delete_messages(chat_id, batch)
        except Exception:
            # Bots can't delete >48h-old messages; those silently no-op or
            # raise per-batch. Swallow so one bad batch doesn't abort the rest.
            pass


@Client.on_message(filters.command("purge"))
async def purge_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /purge only works in groups.")
        return
    if not message.from_user or not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🔒 Only group admins can /purge.")
        return
    if not await _bot_can_delete(client, message.chat.id):
        await message.reply_text(
            "⚠️ I need the **Delete Messages** admin permission specifically. "
            "Enable it in my admin rights and try again."
        )
        return

    chat_id = message.chat.id
    args = message.command[1:]
    reply = message.reply_to_message

    # ── Mode 1: reply-based range ──
    if reply and not args:
        start_id, end_id = reply.id, message.id
        ids = list(range(start_id, end_id + 1))
        if len(ids) > _MAX_PER_CALL:
            await message.reply_text(
                f"⚠️ That range is {len(ids)} messages — over the {_MAX_PER_CALL} "
                f"per-call cap. Purge in smaller chunks."
            )
            return
        await _delete_ids(client, chat_id, ids)
        # Exclude the command message itself from the displayed count.
        await client.send_message(chat_id, f"🧹 Purged {len(ids) - 1} messages.")
        return

    # ── Mode 3: time-window ──  /purge <n> min
    if len(args) >= 2 and args[0].lstrip("-").isdigit() and args[1].lower() in _MIN_WORDS:
        minutes = int(args[0])
        if minutes <= 0:
            await message.reply_text("⚠️ Minutes must be a positive number.")
            return
        cutoff = datetime.now() - timedelta(minutes=minutes)
        ids: list[int] = []
        hit_cap = False
        async for msg in client.get_chat_history(chat_id):
            if msg.date is None:
                continue
            if msg.date < cutoff:
                # History is newest-first — everything past here is older too.
                break
            ids.append(msg.id)
            if len(ids) >= _MAX_PER_CALL:
                hit_cap = True
                break
        await _delete_ids(client, chat_id, ids)
        shown = max(len(ids) - 1, 0)  # command msg falls in-window; don't count it
        if hit_cap:
            await client.send_message(
                chat_id,
                f"🧹 Purged {shown} messages (hit the per-call cap — more messages "
                f"may remain in the last {minutes} min, run /purge again).",
            )
        else:
            await client.send_message(chat_id, f"🧹 Purged {shown} messages.")
        return

    # ── Mode 2: count-based ──  /purge <n>
    if len(args) == 1 and args[0].lstrip("-").isdigit():
        n = int(args[0])
        if n <= 0:
            await message.reply_text("⚠️ Count must be a positive number.")
            return
        n = min(n, _MAX_PER_CALL)
        ids = [message.id]  # the command itself
        async for msg in client.get_chat_history(chat_id, limit=n):
            if msg.id != message.id:
                ids.append(msg.id)
        await _delete_ids(client, chat_id, ids)
        await client.send_message(chat_id, f"🧹 Purged {len(ids) - 1} messages.")
        return

    # ── No recognised form → usage ──
    await message.reply_text(
        "🧹 Usage:\n"
        "• Reply to a message with /purge — delete from there to now\n"
        "• /purge <n> — delete the last n messages\n"
        "• /purge <n> min — delete everything from the last n minutes\n\n"
        f"Max {_MAX_PER_CALL} messages per call. Telegram can't delete "
        "messages older than 48 hours — those are skipped silently."
    )
