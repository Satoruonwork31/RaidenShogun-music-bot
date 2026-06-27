from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType, MessageEntityType

from bot.client import userbot


_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


async def _resolve_target(client, message):
    """Return (target_user, leftover_args_as_reason)."""
    text = message.text or ""

    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            mention_text = text[ent.offset:ent.offset + ent.length]
            after_cmd = text.split(maxsplit=1)
            after_cmd = after_cmd[1] if len(after_cmd) > 1 else ""
            reason = after_cmd.replace(mention_text, "", 1).strip()
            return ent.user, reason

    reply = message.reply_to_message
    if reply and reply.from_user:
        reason = " ".join(message.command[1:]).strip()
        return reply.from_user, reason

    if len(message.command) < 2:
        return None, ""

    raw = message.command[1].lstrip("@")
    reason = " ".join(message.command[2:]).strip()

    try:
        if raw.isdigit():
            user = await client.get_users(int(raw))
        else:
            try:
                user = await userbot.get_users(raw)
            except Exception:
                user = await client.get_users(raw)
        return user, reason
    except Exception:
        return None, reason


@Client.on_message(filters.command("unban"))
async def unban_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /unban only works in groups.")
        return

    if not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🔒 Only group admins can /unban.")
        return

    me = await client.get_me()
    if not await _is_admin(client, message.chat.id, me.id):
        await message.reply_text(
            "⚠️ Make me an admin with **Ban Users** permission so I can do that."
        )
        return

    target, reason = await _resolve_target(client, message)
    if target is None:
        await message.reply_text(
            "Usage:\n"
            "• Reply to a message with /unban [reason]\n"
            "• /unban <user_id> [reason]\n"
            "• /unban @username [reason]"
        )
        return

    try:
        await client.unban_chat_member(message.chat.id, target.id)
    except Exception as exc:
        await message.reply_text(f"❌ Unban failed: {exc}")
        return

    unbanner = message.from_user.mention
    target_name = target.mention
    if reason:
        text = (
            f"✅ {target_name} got unbanned by admin = {unbanner}\n"
            f"Reason: {reason}"
        )
    else:
        text = f"✅ {target_name} got unbanned by admin = {unbanner}"
    await message.reply_text(text)
