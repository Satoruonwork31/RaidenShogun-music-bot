"""/aura — random aura check.

Three independent rolls per call: n (0-100), caption template, GIF —
no correlation between them. Reuses /pat's resolver and the full
GIF-delivery chain (URL-direct → userbot download+upload → bot
download+upload → caption-only) via `_send_pat_gif`, which internally
walks `_candidate_urls` → `_download_gif` → `_try_url_send` →
`_try_local_send`. We do NOT rebuild that chain here.

Caption uses pyrofork's <emoji id="..."> tag (same convention as
pat.py / start.py).
"""

import logging
import random

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

# Reuse pat.py's helpers rather than duplicating. `_send_pat_gif`
# delegates to `_candidate_urls`, `_download_gif`, `_try_url_send`,
# `_try_local_send` internally — calling it IS reusing the whole chain.
# `_attacker_mention` is documented in the spec as the reference style
# for the target mention; `_resolve_target` already returns a mention
# string in that same style, which is what we use.
from bot.plugins.pat import (
    _FALLBACK,
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

# tmpfiles.org share-page links — `_candidate_urls` (called inside
# `_send_pat_gif`) auto-rewrites to the /dl/ form. This host is known
# unreliable for both Telegram server-side fetch and direct bot
# download (see pat.py comments). Working starting point, not
# guaranteed-reliable.
_AURA_GIFS = [
    "https://tmpfiles.org/w9wR7lfg4Jpn/sungjinwoo-sung-jin-woo.mp4",
    "https://tmpfiles.org/wuwN76fTmnHo/piccolo-dbz.mp4",
    "https://tmpfiles.org/wnwZ71f7mfbI/sanji-sanji-el-thor.mp4",
    "https://tmpfiles.org/wTwE7gfKmtCS/jujutsu-kaisen-jujutsu.mp4",
    "https://tmpfiles.org/wNwj7yfHPXwP/one-piece-zoro-vs-king.mp4",
    "https://tmpfiles.org/wPwg7xfyPPJJ/jin-woo-anime-jin-woo.mp4",
]


def _render(template: str, target_mention: str, n: int) -> str:
    """Local variant — aura templates use {target}+{n}, not pat's
    {user1}/{user2}/{eN}. Kept separate to avoid changing /pat's
    `_render` signature and risking its behavior.
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
    logger.info(
        "aura_command fired in chat=%s by user=%s reply=%s",
        message.chat.id if message.chat else None,
        message.from_user.id if message.from_user else None,
        bool(message.reply_to_message),
    )

    try:
        _target, target_mention = await _resolve_target(client, message)
    except Exception:
        logger.exception("aura: _resolve_target raised")
        target_mention = None

    if target_mention is None:
        await message.reply_text("Reply to someone with /aura to check their aura.")
        return

    # Three fully independent rolls — no correlation between them.
    n = random.randint(0, 100)
    template = random.choice(_AURA_CAPTIONS)
    gif_url = random.choice(_AURA_GIFS)

    caption = _render(template, target_mention, n)

    # Reuse pat's full delivery chain: URL-direct → userbot upload →
    # bot upload. Don't rebuild it here.
    ok = await _send_pat_gif(client, message.chat.id, gif_url, caption, message.id)
    if ok:
        return
    logger.info("aura: gif send failed across all paths — sending caption only")

    # Graceful degradation — caption-only reply if every GIF path failed.
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
