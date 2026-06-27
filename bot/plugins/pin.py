"""/pin, /unpin, /unpinall — message pinning for group admins.

Structural pattern mirrors bot/plugins/ban.py:
  chat-type check → caller-admin check → bot-permission check →
  perform action → confirmation reply.

The bot-permission check inspects can_pin_messages SPECIFICALLY on the
bot's own ChatMember.privileges — generic admin status does not imply
that right (same lesson as the invite-link rights in playback.py).
"""

import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType

logger = logging.getLogger("RaidenShogun.pin")

_ADMIN_STATUSES = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def _is_admin(client, chat_id, user_id) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in _ADMIN_STATUSES


async def _bot_can_pin(client, chat_id) -> bool:
    """True iff the bot's own chat-member privileges include can_pin_messages."""
    try:
        me = await client.get_me()
        member = await client.get_chat_member(chat_id, me.id)
    except Exception:
        return False
    if member.status == ChatMemberStatus.OWNER:
        return True
    privs = getattr(member, "privileges", None)
    return bool(privs and getattr(privs, "can_pin_messages", False))


async def _guard(client, message, *, action: str) -> bool:
    """Shared chat-type + caller-admin + bot-permission gate. Returns True
    if all checks pass (caller may proceed), False after replying otherwise.
    """
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(f"👥 /{action} only works in groups.")
        return False
    if not message.from_user or not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text(f"🔒 Only group admins can /{action}.")
        return False
    if not await _bot_can_pin(client, message.chat.id):
        await message.reply_text(
            "⚠️ I need the **Pin Messages** admin permission specifically. "
            "Open my admin rights and enable \"Pin Messages\", then try again."
        )
        return False
    return True


@Client.on_message(filters.command("pin"))
async def pin_command(client, message):
    if not await _guard(client, message, action="pin"):
        return

    reply = message.reply_to_message
    if not reply:
        await message.reply_text(
            "📌 Reply to a message with /pin to pin it.\n\n"
            "• /pin — silent pin\n"
            "• /pin loud — pin and notify members"
        )
        return

    args = [a.lower() for a in message.command[1:]]
    loud = any(a in ("loud", "notify") for a in args)

    logger.info(
        "pin attempt: chat=%s reply_msg_id=%s reply_thread=%s loud=%s reply_repr=%r",
        message.chat.id, reply.id,
        getattr(reply, "message_thread_id", None),
        loud, reply,
    )
    try:
        result = await client.pin_chat_message(
            chat_id=message.chat.id,
            message_id=reply.id,
            disable_notification=not loud,
        )
        logger.info("pin_chat_message returned type=%s value=%r", type(result).__name__, result)
    except Exception as exc:
        logger.exception(
            "pin failed: type=%s id=%s message=%s",
            type(exc).__name__, getattr(exc, "ID", None), getattr(exc, "MESSAGE", None),
        )
        await message.reply_text(
            f"❌ Pin failed: {type(exc).__name__}"
            + (f" [{exc.ID}]" if getattr(exc, "ID", None) else "")
            + f": {getattr(exc, 'MESSAGE', None) or exc}"
        )
        return

    await message.reply_text(f"📌 Pinned by {message.from_user.mention}.")


@Client.on_message(filters.command("unpin"))
async def unpin_command(client, message):
    if not await _guard(client, message, action="unpin"):
        return

    reply = message.reply_to_message
    try:
        if reply:
            await client.unpin_chat_message(message.chat.id, reply.id)
            await message.reply_text(f"📌 Unpinned by {message.from_user.mention}.")
        else:
            # No reply → unpin the most recent pin.
            await client.unpin_chat_message(message.chat.id)
            await message.reply_text(
                f"📌 Unpinned the latest pin (reply to a specific message to "
                f"target it) — by {message.from_user.mention}."
            )
    except Exception as exc:
        await message.reply_text(f"❌ Unpin failed: {exc}")


@Client.on_message(filters.command("unpinall"))
async def unpinall_command(client, message):
    if not await _guard(client, message, action="unpinall"):
        return

    # Destructive — require explicit confirmation.
    args = [a.lower() for a in message.command[1:]]
    if "confirm" not in args:
        await message.reply_text(
            "⚠️ This clears ALL pinned messages in the chat.\n"
            "Re-run as `/unpinall confirm` to proceed."
        )
        return

    try:
        await client.unpin_all_chat_messages(message.chat.id)
    except Exception as exc:
        await message.reply_text(f"❌ Unpin-all failed: {exc}")
        return

    await message.reply_text(f"📌 Cleared all pins — by {message.from_user.mention}.")
