"""/aura — random aura check.

Three independent rolls per call: n (0-100), caption template, GIF.
Reuses /pat's resolver and full GIF-delivery chain (URL-direct →
userbot download+upload → bot download+upload → caption-only).
"""

import logging
import random

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

from bot.plugins.pat import (
    _FALLBACK,
    _attacker_mention,
    _resolve_target,
    _send_pat_gif,
)

logger = logging.getLogger("RaidenShogun.aura")


_AURA_CAPTIONS = [
    '<emoji id="6116352966480895996">📡</emoji> {target} has been scanned... aura level: {n}%',
    '<emoji id="6178978331300467171">✨</emoji> Aura check complete — {target} is sitting at {n}%',
    '<emoji id="5271810272640643747">🔮</emoji> The universe has spoken: {target}\'s aura is {n}%',
    '<emoji id="6170427231802757303">⚡</emoji> {target}\'s aura reading just came in at {n}%',
    '<emoji id="6233510010639355761">🌌</emoji> Cosmic aura levels for {target}: {n}%',
    '<emoji id="5409242916805696077">🧿</emoji> {target} radiates exactly {n}% aura right now',
    '<emoji id="5978835896143714365">💫</emoji> Aura sensors confirm {target} is at {n}%',
    '<emoji id="6115889410660638621">🎴</emoji> Fate has assigned {target} an aura of {n}%',
    '<emoji id="5427206638996037048">🌀</emoji> {target}\'s current aura output: {n}%',
    '<emoji id="5269617691836058799">🪄</emoji> Mystic reading: {target} carries {n}% aura today',
]

_AURA_GIFS = [
    "https://tmpfiles.org/w9wR7lfg4Jpn/sungjinwoo-sung-jin-woo.mp4",
    "https://tmpfiles.org/wuwN76fTmnHo/piccolo-dbz.mp4",
    "https://tmpfiles.org/wnwZ71f7mfbI/sanji-sanji-el-thor.mp4",
    "https://tmpfiles.org/wTwE7gfKmtCS/jujutsu-kaisen-jujutsu.mp4",
    "https://tmpfiles.org/wNwj7yfHPXwP/one-piece-zoro-vs-king.mp4",
    "https://tmpfiles.org/wPwg7xfyPPJJ/jin-woo-anime-jin-woo.mp4",
]


def _render(template: str, target_mention: str, n: int) -> str:
    """Aura templates use {target} + {n}, not pat's {user1}/{user2}/{eN}."""
    return template.format(target=target_mention, n=n)


def _strip_emoji_tags(template: str) -> str:
    import re
    return re.sub(r'<emoji id="\d+">([^<]*)</emoji>', lambda m: m.group(1) or _FALLBACK, template)


@Client.on_message(filters.command("aura"))
async def aura_command(client, message):
    logger.info(
        "aura_command fired in chat=%s by user=%s reply=%s",
        message.chat.id if message.chat else None,
        message.from_user.id if message.from_user else None,
        bool(message.reply_to_message),
    )

    try:
        target, target_mention = await _resolve_target(client, message)
    except Exception:
        logger.exception("aura: _resolve_target raised")
        target, target_mention = None, None

    # No reply, no @user, no user_id → default to the sender themselves.
    if target_mention is None:
        sender = message.from_user
        if sender is not None:
            target = sender
            target_mention = sender.mention or sender.first_name or str(sender.id)
        else:
            await message.reply_text("📡 Couldn't figure out whose aura to check.")
            return

    # Three fully independent rolls.
    n = random.randint(0, 100)
    template = random.choice(_AURA_CAPTIONS)
    gif_url = random.choice(_AURA_GIFS)

    caption = _render(template, target_mention, n)

    ok = await _send_pat_gif(client, message.chat.id, gif_url, caption, message.id)
    if ok:
        return
    logger.info("aura: gif send failed across all paths — sending caption only")

    try:
        await message.reply_text(
            caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("aura: HTML caption reply failed, retrying plain")
        try:
            await message.reply_text(
                _render(_strip_emoji_tags(template), target_mention, n),
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("aura: plain caption reply failed too")
