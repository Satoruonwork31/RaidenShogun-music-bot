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
    """Return (user, title, error).

    title rules:
      • reply + /<cmd> tail → tail is the title
      • /<cmd> <user> <tail…> → tail is the title
      • title is None if nothing followed
    Telegram caps admin titles at 16 chars; longer strings get truncated.
    """
    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            title = " ".join(message.command[1:]).strip() or None
            text_mention = (message.text or "")[ent.offset:ent.offset + ent.length]
            if title:
                title = title.replace(text_mention, "", 1).strip() or None
            return ent.user, (title[:16] if title else None), None

    reply = message.reply_to_message
    if reply and reply.from_user:
        title = " ".join(message.command[1:]).strip() or None
        return reply.from_user, (title[:16] if title else None), None

    if len(message.command) < 2:
        return None, None, None

    raw = message.command[1].lstrip("@")
    title = " ".join(message.command[2:]).strip() or None
    title = title[:16] if title else None
    try:
        if raw.lstrip("-").isdigit():
            return await client.get_users(int(raw)), title, None
        try:
            return await userbot.get_users(raw), title, None
        except Exception:
            return await client.get_users(raw), title, None
    except Exception as exc:
        return None, None, f"Couldn't resolve `{raw}`: {exc}"


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

    target, title, err = await _resolve_target(client, message)
    if target is None:
        await message.reply_text(
            err or
            "Usage:\n"
            "• Reply with /promote [title]\n"
            "• /promote <user_id> [title]\n"
            "• /promote @username [title]"
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

    title_note = ""
    if title:
        try:
            await client.set_administrator_title(message.chat.id, target.id, title)
            title_note = f"\n🏷 Title: {title}"
        except Exception as exc:
            # Promotion succeeded; just the title set failed.
            logger.exception("set_administrator_title failed")
            title_note = (
                f"\n⚠️ Title not set: {type(exc).__name__}: "
                f"{getattr(exc, 'MESSAGE', None) or exc}"
            )

    await message.reply_text(
        f"⭐ {target.mention} promoted to admin by {message.from_user.mention}.{title_note}"
    )


@Client.on_message(filters.command(["demote", "unpromote"]))
async def demote_command(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("👥 /demote only works in groups.")
        return
    if not message.from_user or not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🔒 Only group admins can /demote.")
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

    target, _title, err = await _resolve_target(client, message)
    if target is None:
        await message.reply_text(
            err or
            "Usage:\n"
            "• Reply with /demote\n"
            "• /demote <user_id>\n"
            "• /demote @username"
        )
        return

    if target.id == me.id:
        await message.reply_text("🙃 Can't demote myself.")
        return

    # All-False privilege set demotes an admin back to plain member.
    zero = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=False,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
    )

    try:
        await client.promote_chat_member(message.chat.id, target.id, privileges=zero)
    except Exception as exc:
        logger.exception("demote failed: id=%s message=%s", getattr(exc, "ID", None), getattr(exc, "MESSAGE", None))
        await message.reply_text(
            f"❌ Demote failed: {type(exc).__name__}"
            + (f" [{exc.ID}]" if getattr(exc, "ID", None) else "")
            + f": {getattr(exc, 'MESSAGE', None) or exc}"
        )
        return

    await message.reply_text(
        f"💤 {target.mention} demoted by {message.from_user.mention}."
    )
