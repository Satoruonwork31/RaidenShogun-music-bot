from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType


_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


async def _resolve_target(client, message):
    """Return (target_user, leftover_args_as_reason). target_user is a User object."""
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
            user = await client.get_users(raw)
        return user, reason
    except Exception:
        return None, reason


@Client.on_message(filters.command("ban"))
async def ban_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /ban only works in groups.")
        return

    if not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🔒 Only group admins can /ban.")
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
            "• Reply to a message with /ban [reason]\n"
            "• /ban <user_id> [reason]\n"
            "• /ban @username [reason]"
        )
        return

    if target.id == me.id:
        await message.reply_text("🙃 I'm not going to ban myself.")
        return
    if target.id == message.from_user.id:
        await message.reply_text("🙃 You can't ban yourself.")
        return
    if await _is_admin(client, message.chat.id, target.id):
        await message.reply_text("🔒 I can't ban another admin.")
        return

    try:
        await client.ban_chat_member(message.chat.id, target.id)
    except Exception as exc:
        await message.reply_text(f"❌ Ban failed: {exc}")
        return

    banner_name = message.from_user.mention
    target_name = target.mention
    if reason:
        text = (
            f"🚫 {target_name} got banned by admin = {banner_name}\n"
            f"Reason: {reason}"
        )
    else:
        text = f"🚫 {target_name} got banned by admin = {banner_name}"
    await message.reply_text(text)
