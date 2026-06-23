from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType

from bot.utils.greetings import is_enabled, set_enabled

_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


@Client.on_message(filters.command("greetings"))
async def greetings_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /greetings only works in groups.")
        return

    if not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🔒 Only group admins can toggle greetings.")
        return

    if len(message.command) < 2:
        state = "ON ✅" if is_enabled(message.chat.id) else "OFF ❌"
        await message.reply_text(
            f"👋 Greetings are currently: **{state}**\n\n"
            "Use `/greetings on` or `/greetings off`."
        )
        return

    arg = message.command[1].lower()
    if arg in ("on", "enable", "enabled", "yes", "true"):
        set_enabled(message.chat.id, True)
        await message.reply_text("✅ Greetings turned **ON**. New members will be welcomed.")
    elif arg in ("off", "disable", "disabled", "no", "false"):
        set_enabled(message.chat.id, False)
        await message.reply_text("❌ Greetings turned **OFF**. New members will not be welcomed.")
    else:
        await message.reply_text("Use `/greetings on` or `/greetings off`.")
