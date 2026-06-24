"""/seeddm — owner-only command to manually add user IDs to the broadcast
chat registry.

Bots can't enumerate users who've started them — there's no Telegram API
for that. So if you know specific user IDs that have already /started the
bot, you can seed them here and /broadcast will include their DMs.

Usage:
  /seeddm 123456789 987654321 ...
  (reply to a forwarded message from the user) /seeddm

The user MUST have already done /start with the bot — Telegram bots can't
initiate conversations with strangers, so seeding a user who hasn't
started the bot just produces a "Forbidden: bot can't initiate
conversation" error during /broadcast (and we'll auto-drop them).
"""

import logging

from pyrogram import Client, filters

from bot.utils import chats
from bot.utils.owner import is_owner

logger = logging.getLogger("RaidenShogun.seeddm")


def _parse_ids_from_args(args) -> list[int]:
    out = []
    for a in args:
        a = a.strip().lstrip("@")
        if a.lstrip("-").isdigit():
            out.append(int(a))
    return out


@Client.on_message(filters.command("seeddm"))
async def seeddm_command(client, message):
    if not message.from_user or not await is_owner(message.from_user.id):
        await message.reply_text("🔒 /seeddm is owner-only.")
        return

    ids: list[int] = []

    # Mode 1: reply to a forwarded message — pick up forward_from.id.
    reply = message.reply_to_message
    if reply is not None:
        fwd = getattr(reply, "forward_from", None)
        if fwd is not None and getattr(fwd, "id", None):
            ids.append(fwd.id)
        elif reply.from_user is not None:
            ids.append(reply.from_user.id)

    # Mode 2: positional args.
    if len(message.command) > 1:
        ids.extend(_parse_ids_from_args(message.command[1:]))

    if not ids:
        await message.reply_text(
            "Usage:\n"
            "• `/seeddm 123 456 789` — seed by user ID(s)\n"
            "• Reply to a forwarded message with `/seeddm` to add that user\n\n"
            "Note: the user must have already started the bot. Telegram won't "
            "let bots send to strangers — un-started seeds will be auto-dropped "
            "from the registry on the next failed broadcast."
        )
        return

    added = 0
    skipped = 0
    for uid in ids:
        if chats.remember(uid):
            added += 1
            logger.info("/seeddm: added user %s to registry", uid)
        else:
            skipped += 1

    await message.reply_text(
        f"📥 Seeded.\n\n"
        f"✅ Added: {added}\n"
        f"➖ Already known: {skipped}\n"
        f"📊 Registry size: {chats.count()}"
    )
