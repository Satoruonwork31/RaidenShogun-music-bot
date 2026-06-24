"""/addsudo, /delsudo, /sudolist — owner-managed delegation of privileges.

The bot's OWNER (env OWNER_ID, defaults to the userbot.id) is implicit
sudo and can never be removed. Sudoers granted here can run commands
gated by `is_sudo` (currently /broadcast, /seeddm).

Resolution rules for target user (same shape as /ban):
- text_mention entity in the command message
- reply to a user's message
- /addsudo <user_id>
- /addsudo @username (resolved via the userbot since the bot API can't
  always resolve arbitrary @usernames)
"""

from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType, ParseMode

from bot.utils import sudo as sudo_store
from bot.utils.owner import is_owner, is_sudo


async def _resolve_user(client, message):
    """Return (user_id, mention_html) for the addsudo/delsudo target."""
    text = message.text or ""

    # text-mention entity (covers usernameless tagged users)
    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            return ent.user.id, ent.user.mention

    # reply
    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user.id, reply.from_user.mention

    if len(message.command) < 2:
        return None, None

    raw = message.command[1].lstrip("@")

    from bot.client import userbot
    try:
        if raw.isdigit():
            u = await client.get_users(int(raw))
        else:
            try:
                u = await userbot.get_users(raw)
            except Exception:
                u = await client.get_users(raw)
        return u.id, u.mention
    except Exception:
        # Last-resort: trust the id we were given even if we can't fetch
        # a User object for the pretty-print.
        if raw.isdigit():
            return int(raw), f'<a href="tg://user?id={raw}">user {raw}</a>'
        return None, None


@Client.on_message(filters.command("addsudo"))
async def addsudo_command(client, message):
    if not message.from_user or not await is_owner(message.from_user.id):
        await message.reply_text("🔒 /addsudo is owner-only.")
        return

    target_id, mention = await _resolve_user(client, message)
    if target_id is None:
        await message.reply_text(
            "Usage:\n"
            "• Reply to a user's message with `/addsudo`\n"
            "• `/addsudo <user_id>`\n"
            "• `/addsudo @username`"
        )
        return

    if await is_owner(target_id):
        await message.reply_text("ℹ️ The owner is already implicit sudo.")
        return

    if sudo_store.add(target_id):
        await message.reply_text(
            f"✅ {mention} added to sudo.", parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            f"ℹ️ {mention} was already a sudoer.", parse_mode=ParseMode.HTML
        )


@Client.on_message(filters.command(["delsudo", "removesudo", "rmsudo"]))
async def delsudo_command(client, message):
    if not message.from_user or not await is_owner(message.from_user.id):
        await message.reply_text("🔒 /delsudo is owner-only.")
        return

    target_id, mention = await _resolve_user(client, message)
    if target_id is None:
        await message.reply_text(
            "Usage:\n"
            "• Reply to a user's message with `/delsudo`\n"
            "• `/delsudo <user_id>`\n"
            "• `/delsudo @username`"
        )
        return

    if sudo_store.remove(target_id):
        await message.reply_text(
            f"✅ {mention} removed from sudo.", parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            f"ℹ️ {mention} wasn't a sudoer.", parse_mode=ParseMode.HTML
        )


@Client.on_message(filters.command(["sudolist", "sudoers"]))
async def sudolist_command(client, message):
    if not message.from_user or not await is_sudo(message.from_user.id):
        await message.reply_text("🔒 /sudolist is sudo-only.")
        return

    sudoers = sudo_store.all_sudoers()
    if not sudoers:
        await message.reply_text(
            "📜 No additional sudoers yet (owner is implicit sudo)."
        )
        return

    lines = ["📜 <b>Sudoers</b>"]
    for uid in sudoers:
        try:
            u = await client.get_users(uid)
            lines.append(f"• {u.mention} (<code>{uid}</code>)")
        except Exception:
            lines.append(f"• <code>{uid}</code>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
