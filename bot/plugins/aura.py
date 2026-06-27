"""/aura — random aura check.

Three independent rolls per call: n (0-100), caption template, GIF —
no correlation between them. Reuses the resolver + GIF-delivery chain
from `bot.utils.social_commands` (URL-direct → userbot
download+upload → bot download+upload → caller handles caption-only
fallback).

Plugin-to-plugin imports are banned in this repo (pyrofork's
plugins-root scanner gets confused by nested re-entrant imports of
other plugin modules during handler registration). Anything shared
with /pat goes through `bot.utils.social_commands` instead.
"""

import logging
import random

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

from bot.utils.social_commands import (
    _FALLBACK,
    attacker_mention,
    resolve_target,
    send_media_gif,
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

# tmpfiles.org share-page links — `_candidate_urls` (called inside
# `send_media_gif`) auto-rewrites to the /dl/ form. This host is
# known unreliable for both Telegram server-side fetch and direct bot
# download. Working starting point, not guaranteed-reliable.
_AURA_GIFS = [
    "https://tmpfiles.org/w9wR7lfg4Jpn/sungjinwoo-sung-jin-woo.mp4",
    "https://tmpfiles.org/wuwN76fTmnHo/piccolo-dbz.mp4",
    "https://tmpfiles.org/wnwZ71f7mfbI/sanji-sanji-el-thor.mp4",
    "https://tmpfiles.org/wTwE7gfKmtCS/jujutsu-kaisen-jujutsu.mp4",
    "https://tmpfiles.org/wNwj7yfHPXwP/one-piece-zoro-vs-king.mp4",
    "https://tmpfiles.org/wPwg7xfyPPJJ/jin-woo-anime-jin-woo.mp4",
]


def _render(template: str, target_mention: str, n: int) -> str:
    """Local — aura templates use {target}+{n}, intentionally separate
    from social_commands since pat's slots ({user1}/{user2}/{eN}) differ.
    """
    return template.format(target=target_mention, n=n)


def _strip_emoji_tags(template: str) -> str:
    """Last-resort plain-text fallback: replace <emoji id="X">Y</emoji>
    with Y (or _FALLBACK if empty) so the line still reads if HTML
    parsing fails.
    """
    import re
    return re.sub(
        r'<emoji id="\d+">([^<]*)</emoji>',
        lambda m: m.group(1) or _FALLBACK,
        template,
    )


@Client.on_message(filters.command("aura"))
async def aura_command(client, message):
    # Trip-wire: if this line doesn't appear in logs when /aura is sent,
    # the handler isn't being bound at all (pyrofork scan issue, not a
    # bug in the body below).
    logger.info(
        "aura_command fired in chat=%s by user=%s reply=%s",
        message.chat.id if message.chat else None,
        message.from_user.id if message.from_user else None,
        bool(message.reply_to_message),
    )

    try:
        _target, target_mention = await resolve_target(client, message)
    except Exception:
        logger.exception("aura: resolve_target raised")
        target_mention = None

    # No reply / no resolvable target → check the sender's own aura.
    if target_mention is None:
        target_mention = attacker_mention(message)

    # Three fully independent rolls — no correlation between them.
    n = random.randint(0, 100)
    template = random.choice(_AURA_CAPTIONS)
    gif_url = random.choice(_AURA_GIFS)

    caption = _render(template, target_mention, n)

    # Full delivery chain: URL-direct → userbot upload → bot upload.
    try:
        ok = await send_media_gif(client, message.chat.id, gif_url, caption, message.id)
    except Exception:
        logger.exception("aura: send_media_gif raised")
        ok = False
    if ok:
        return
    logger.info("aura: gif send failed across all paths — sending caption only")

    # Caption-only fallback (HTML first).
    try:
        await message.reply_text(
            caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )
        return
    except Exception:
        logger.exception("aura: HTML caption reply failed, retrying plain")

    # Last resort: strip <emoji> tags, send plain text.
    try:
        await message.reply_text(
            _render(_strip_emoji_tags(template), target_mention, n),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("aura: plain caption reply failed too")
