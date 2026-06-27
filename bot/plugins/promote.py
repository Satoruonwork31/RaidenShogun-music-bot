import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType, MessageEntityType
from pyrogram.types import ChatAdministratorRights

from bot.client import userbot

logger = logging.getLogger("RaidenShogun.promote")

_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


async def _resolve_target(client, message):
    text = message.text or ""

    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            return ent.user, None

    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user, None

    if len(message.command) < 2:
        return None, None

    raw = message.command[1].lstrip("@")
    try:
        if raw.lstrip("-").isdigit():
            return await client.get_users(int(raw)), None
        try:
            return await userbot.get_users(raw), None
        except Exception:
            return await client.get_users(raw), None
    except Exception as exc:
        return None, f"Couldn't resolve `{raw}`: {exc}"


@Client.on_message(filters.command(["promote", "feature"]))
async def promote_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /promote only works in groups.")
        return
    if not message.from_user or not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🔒 Only group admins can /promote.")
        return

    me = await client.get_me()
    try:
        me_member = await client.get_chat_member(message.chat.id, me.id)
    except Exception:
        me_member = None
    if me_member is None or me_member.status != ChatMemberStatus.ADMINISTRATOR:
        await message.reply_text("⚠️ I need to be an admin with **Add New Admins** rights.")
        return
    privs = getattr(me_member, "privileges", None)
    if not privs or not getattr(privs, "can_promote_members", False):
        await message.reply_text("⚠️ I'm missing the **Add New Admins** admin right.")
        return

    target, err = await _resolve_target(client, message)
    if target is None:
        await message.reply_text(
            err or
            "Usage:\n"
            "• Reply to a message with /promote\n"
            "• /promote <user_id>\n"
            "• /promote @username"
        )
        return

    if target.id == me.id:
        await message.reply_text("🙃 Can't promote myself.")
        return

    rights = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=True,
        can_restrict_members=True,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True,
    )

    try:
        await client.promote_chat_member(message.chat.id, target.id, privileges=rights)
    except Exception as exc:
        logger.exception("promote failed: id=%s message=%s", getattr(exc, "ID", None), getattr(exc, "MESSAGE", None))
        await message.reply_text(
            f"❌ Promote failed: {type(exc).__name__}"
            + (f" [{exc.ID}]" if getattr(exc, "ID", None) else "")
            + f": {getattr(exc, 'MESSAGE', None) or exc}"
        )
        return

    await message.reply_text(
        f"⭐ {target.mention} promoted to admin by {message.from_user.mention}."
    )
