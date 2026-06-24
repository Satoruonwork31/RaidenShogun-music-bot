"""Populate the chat registry from the userbot's perspective.

Bots can't enumerate their own dialogs over MTProto. The userbot (the
assistant account in STRING_SESSION) CAN — and because it has to be in
every group where the bot streams voice chat, the userbot's dialog list
is a near-complete source of truth for the bot's group memberships.

`messages.GetCommonChats` is the most direct way: it returns the chats
both the userbot and the bot are members of. We add each returned chat id
to the registry.

DMs aren't covered by this — Telegram doesn't expose a "users who started
the bot" enumeration. Those still come from the passive _track_chat
handler as people interact with the bot.
"""

from __future__ import annotations

import logging

from bot.client import app, userbot
from bot.utils import chats

logger = logging.getLogger("RaidenShogun.discover")


async def backfill_common_chats() -> int:
    """Ask the userbot for chats it shares with the bot and add each to the
    registry. Returns the number of NEW chats added.
    """
    try:
        bot_me = await app.get_me()
    except Exception as exc:
        logger.warning("backfill: app.get_me failed: %s", exc)
        return 0

    added = 0
    seen = 0
    try:
        common = await userbot.get_common_chats(bot_me.id)
    except Exception as exc:
        logger.warning("backfill: userbot.get_common_chats failed: %s", exc)
        return 0

    for chat in common or []:
        seen += 1
        chat_id = getattr(chat, "id", None)
        if chat_id is None:
            continue
        if chats.remember(chat_id):
            added += 1
            logger.info("backfill: added chat %s (%s)", chat_id, getattr(chat, "title", "?"))

    logger.info(
        "backfill: scanned %s common chats, added %s new (registry size now %s)",
        seen, added, chats.count(),
    )
    return added
