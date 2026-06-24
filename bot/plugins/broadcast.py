"""/broadcast — owner-only fan-out of a message to every known chat.

Two forms:
  /broadcast <text>                  — sends the text to every chat
  reply to a message + /broadcast    — copies the replied message verbatim

In groups and supergroups, the sent message is pinned silently. DMs are
not pinned (Telegram allows it but users find it intrusive).

Chats are tracked as they message the bot — see bot/utils/chats.py. A
passive group=-1 handler in this module records every chat_id we see.
"""

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    ChatAdminRequired,
    ChatWriteForbidden,
    FloodWait,
    PeerIdInvalid,
    UserIsBlocked,
    UserIsBot,
)

from bot.utils import chats
from bot.utils.owner import is_sudo

logger = logging.getLogger("RaidenShogun.broadcast")

# Bots can comfortably do ~30 unique-target sends per second before
# Telegram throttles. 0.05s = 20/s, leaves headroom for retries.
_DELAY_BETWEEN_SENDS = 0.05


def _flood_seconds(exc: FloodWait) -> int:
    # pyrofork 2.x uses .value, older releases used .x. Cover both.
    return int(getattr(exc, "value", None) or getattr(exc, "x", 30))


async def _send_one(client, chat_id: int, *, reply, text_content: str):
    """Returns (sent_message, error_class_name_or_None).

    sent_message is the Message we placed; caller will try to pin it.
    """
    if reply is not None:
        return await reply.copy(chat_id), None
    return await client.send_message(chat_id, text_content), None


async def _maybe_pin(client, message) -> bool:
    """Pin silently if the destination is a group/supergroup. Returns
    True on a successful pin, False otherwise (including non-group
    chats — they intentionally aren't pinned).
    """
    if message is None or message.chat is None:
        return False
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    try:
        await client.pin_chat_message(
            chat_id=message.chat.id,
            message_id=message.id,
            disable_notification=True,
        )
        return True
    except ChatAdminRequired:
        logger.info("Skip pin in %s: not admin", message.chat.id)
    except Exception as exc:
        logger.info("Pin failed in %s: %s", message.chat.id, exc)
    return False


@Client.on_message(filters.command("broadcast"))
async def broadcast_command(client, message):
    if not message.from_user:
        return
    if not await is_sudo(message.from_user.id):
        await message.reply_text("🔒 /broadcast is sudo-only.")
        return

    reply = message.reply_to_message
    text_content = (
        " ".join(message.command[1:]).strip()
        if len(message.command) > 1
        else ""
    )

    if reply is None and not text_content:
        await message.reply_text(
            "Usage:\n"
            "• `/broadcast <text>` — send text to every known chat\n"
            "• Reply to a message with `/broadcast` — copy that message verbatim\n\n"
            "Groups: pinned silently. DMs: just sent (not pinned)."
        )
        return

    targets = chats.all_chats()
    if not targets:
        await message.reply_text(
            "📭 Don't know about any chats yet. The bot tracks chats as it sees "
            "messages — let it run for a bit, or have a user DM it / send a "
            "message in a group with the bot."
        )
        return

    status = await message.reply_text(
        f"📣 Broadcasting to {len(targets)} chat(s)…"
    )

    sent = 0
    pinned = 0
    failed = 0
    forgotten = 0

    for chat_id in targets:
        try:
            bcast, _ = await _send_one(
                client, chat_id, reply=reply, text_content=text_content
            )
            sent += 1
            if await _maybe_pin(client, bcast):
                pinned += 1
        except FloodWait as fw:
            wait = _flood_seconds(fw)
            logger.warning(
                "FloodWait %ss while broadcasting to %s — sleeping then retrying",
                wait, chat_id,
            )
            await asyncio.sleep(wait + 1)
            try:
                bcast, _ = await _send_one(
                    client, chat_id, reply=reply, text_content=text_content
                )
                sent += 1
                if await _maybe_pin(client, bcast):
                    pinned += 1
            except Exception as exc2:
                failed += 1
                logger.info("Retry-after-flood failed for %s: %s", chat_id, exc2)
        except (
            PeerIdInvalid,
            UserIsBlocked,
            UserIsBot,
            ChannelInvalid,
        ) as exc:
            # Permanently dead: bot was kicked, user blocked us, chat or
            # channel id no longer resolves. Drop from registry.
            forgotten += 1
            chats.forget(chat_id)
            logger.info("Forgetting %s: %s: %s", chat_id, type(exc).__name__, exc)
        except (ChatWriteForbidden, ChannelPrivate) as exc:
            # Recoverable: bot lost write/pin permission in this chat, or
            # the channel is currently private/admin-only. Keep the chat
            # in the registry so the next broadcast tries again once
            # permissions are restored.
            failed += 1
            logger.info(
                "Broadcast to %s blocked (kept in registry): %s: %s",
                chat_id, type(exc).__name__, exc,
            )
        except Exception as exc:
            failed += 1
            logger.info("Broadcast to %s failed: %s: %s", chat_id, type(exc).__name__, exc)

        await asyncio.sleep(_DELAY_BETWEEN_SENDS)

    summary = (
        f"📣 Broadcast complete.\n\n"
        f"✅ Sent: {sent}\n"
        f"📌 Pinned: {pinned}\n"
        f"❌ Failed: {failed}\n"
        f"🗑️ Forgotten (kicked/blocked/dead): {forgotten}"
    )
    try:
        await status.edit_text(summary)
    except Exception:
        await message.reply_text(summary)


# Track the bot's OWN membership changes — fires when the bot is added to
# a group, removed, promoted, or restricted. Registers the chat on join,
# drops it on leave. Future-proofs the broadcast registry against the
# /broadcast-only-hits-my-DM symptom.
_PRESENT = (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
_GONE = (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)


@Client.on_chat_member_updated()
async def _track_self_membership(client, update):
    new = getattr(update, "new_chat_member", None)
    if new is None or new.user is None:
        return
    if not getattr(new.user, "is_self", False):
        # Some other member changed — not our concern; welcome.py handles that.
        return
    chat_id = update.chat.id if update.chat else None
    if chat_id is None:
        return
    if new.status in _PRESENT:
        if chats.remember(chat_id):
            logger.info("self added to chat %s (status=%s)", chat_id, new.status)
    elif new.status in _GONE:
        if chats.forget(chat_id):
            logger.info("self removed from chat %s (status=%s)", chat_id, new.status)


# Passive: record every chat the bot sees a message in. group=-1 runs
# before the command handlers in group=0 but doesn't consume the message
# — different groups all fire independently.
@Client.on_message(filters.all, group=-1)
async def _track_chat(client, message):
    chat = message.chat
    user = message.from_user
    text = (message.text or message.caption or "")[:60]
    logger.info(
        "saw msg in chat=%s (type=%s) from user=%s (id=%s) text=%r",
        chat.id if chat else None,
        chat.type.value if chat and chat.type else None,
        user.username if user else None,
        user.id if user else None,
        text,
    )
    if chat is not None:
        added = chats.remember(chat.id)
        if added:
            logger.info("registered new chat %s in registry", chat.id)
