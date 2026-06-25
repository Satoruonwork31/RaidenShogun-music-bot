"""/departure on|off — per-chat toggle for the farewell handler.

Default is ON. Use this when a group wants the bot's leave messages
silenced without also turning off welcome cards (which the /greetings
toggle controls).
"""

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType

from bot.utils.departure import is_enabled, set_enabled

_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


@Client.on_message(filters.command(["departure", "farewell", "departures"]))
async def departure_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /departure only works in groups.")
        return

    if not message.from_user or not await _is_admin(
        client, message.chat.id, message.from_user.id
    ):
        await message.reply_text("🔒 Only group admins can toggle departures.")
        return

    if len(message.command) < 2:
        state = "ON ✅" if is_enabled(message.chat.id) else "OFF ❌"
        await message.reply_text(
            f"👋 Departure messages are currently: **{state}**\n\n"
            "Use `/departure on` or `/departure off`."
        )
        return

    arg = message.command[1].lower()
    if arg in ("on", "enable", "enabled", "yes", "true"):
        set_enabled(message.chat.id, True)
        await message.reply_text(
            "✅ Departure messages turned **ON**. "
            "I'll wave goodbye when members leave."
        )
    elif arg in ("off", "disable", "disabled", "no", "false"):
        set_enabled(message.chat.id, False)
        await message.reply_text(
            "❌ Departure messages turned **OFF**. "
            "I'll stay quiet when members leave."
        )
    else:
        await message.reply_text("Use `/departure on` or `/departure off`.")
