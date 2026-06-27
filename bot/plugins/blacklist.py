import logging

from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType

from bot.client import userbot
from bot.utils import blacklist as bl
from bot.utils.owner import get_owner_ids, is_sudo

logger = logging.getLogger("RaidenShogun.blacklist")


async def _resolve_target(client, message):
    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            text_mention = (message.text or "")[ent.offset:ent.offset + ent.length]
            reason = " ".join(message.command[1:]).replace(text_mention, "", 1).strip()
            return ent.user, reason, None

    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user, " ".join(message.command[1:]).strip(), None

    if len(message.command) < 2:
        return None, "", None

    raw = message.command[1].lstrip("@")
    reason = " ".join(message.command[2:]).strip()
    try:
        if raw.lstrip("-").isdigit():
            return await client.get_users(int(raw)), reason, None
        try:
            return await userbot.get_users(raw), reason, None
        except Exception:
            return await client.get_users(raw), reason, None
    except Exception as exc:
        return None, "", f"Couldn't resolve `{raw}`: {exc}"


# group=-3 runs before broadcast tracker (group=-1) and every command
# handler (group=0). Catches messages from blacklisted users and stops
# propagation so the bot ignores them entirely — no command response,
# no linksniffer auto-download, no chat-registry track.
@Client.on_message(filters.all, group=-3)
async def _intercept_blacklisted(client, message):
    user = message.from_user
    if user is None or not bl.is_blacklisted(user.id):
        return
    # Don't block owner/sudo even if accidentally added.
    if await is_sudo(user.id):
        return
    logger.info("blacklist: dropped message from user=%s chat=%s",
                user.id, message.chat.id if message.chat else None)
    message.stop_propagation()


@Client.on_message(filters.command("blist"))
async def blist_command(client, message):
    if not message.from_user or not await is_sudo(message.from_user.id):
        owners = await get_owner_ids()
        await message.reply_text(
            "🔒 /blist is sudo-only.\n"
            f"Your ID: <code>{message.from_user.id}</code>\n"
            f"Owners: <code>{', '.join(str(i) for i in sorted(owners)) or '(none)'}</code>"
        )
        return

    target, reason, err = await _resolve_target(client, message)
    if target is None:
        await message.reply_text(
            err or
            "Usage:\n"
            "• Reply with /blist [reason]\n"
            "• /blist <user_id> [reason]\n"
            "• /blist @username [reason]"
        )
        return

    me = await client.get_me()
    if target.id == me.id:
        await message.reply_text("🙃 Can't blacklist myself.")
        return
    if await is_sudo(target.id):
        await message.reply_text("🔒 Can't blacklist a sudo user.")
        return

    was_new = bl.add(target.id, reason=reason, by_user=message.from_user.id)
    verb = "blacklisted" if was_new else "blacklist updated for"
    tail = f"\nReason: {reason}" if reason else ""
    await message.reply_text(
        f"⛔ {target.mention} {verb} by {message.from_user.mention}.{tail}\n"
        f"Total blacklisted: {bl.count()}"
    )


@Client.on_message(filters.command(["unblist", "removeblist"]))
async def unblist_command(client, message):
    if not message.from_user or not await is_sudo(message.from_user.id):
        await message.reply_text("🔒 /unblist is sudo-only.")
        return

    target, _reason, err = await _resolve_target(client, message)
    if target is None:
        await message.reply_text(
            err or
            "Usage:\n"
            "• Reply with /unblist\n"
            "• /unblist <user_id>\n"
            "• /unblist @username"
        )
        return

    removed = bl.remove(target.id)
    if not removed:
        await message.reply_text(f"➖ {target.mention} wasn't blacklisted.")
        return
    await message.reply_text(
        f"✅ {target.mention} removed from blacklist by {message.from_user.mention}.\n"
        f"Total blacklisted: {bl.count()}"
    )
