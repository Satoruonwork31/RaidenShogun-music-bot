"""/pat — soft, wholesome headpat command.

Triggers:
  /pat                — reply-mode: target is the replied-to user
  /pat @username
  /pat <user_id>
  /pat <text_mention> — Telegram text-mention entity

Each call picks a random entry from `_RESPONSES`. Each entry carries:
  - a list of premium custom emoji ids (rendered as <emoji id="..."> tags)
  - a caption template using {e0}/{e1}/... slots and {user1}/{user2}
  - a gif URL — Telegram fetches it server-side (we do NOT
    upload from the bot, which hangs on this pyrofork build, same
    issue /kill hit)

If the gif URL fails, we fall back to a plain text reply with the
same caption.

Captions 1-5 are the original text-only set. Captions 6-10 add GIFs.

Helpers (target resolution + GIF delivery chain) live in
`bot.utils.social_commands` so /aura and any future similar command
can reuse them without one plugin importing another. Plugin-to-plugin
imports are banned in this repo.
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

logger = logging.getLogger("RaidenShogun.pat")


# Fixed (gif, caption) pairs — the unit /pat samples from. random.choice
# picks ONE entry; gif_url and caption stay bonded for that response.
# With 10 captions and 6 operator-supplied GIFs, the 4 surplus captions
# reuse GIFs 1-4 (so gifs 1-4 appear twice in the pool, 5-6 once).
#
# Each entry: (gif_url, emoji_ids, template).
# Templates use {e0}, {e1}, ... in the order emojis appear in the line.

_GIF_KOBAYASHI = "https://tmpfiles.org/wlwt01UyeFY0/kobayashi-dragon.mp4"
_GIF_SENPAI = "https://tmpfiles.org/wZwA0GUlffqV/senpai-ga-uzai-kouhai-no-hanashi-futaba.mp4"
_GIF_ANYA = "https://tmpfiles.org/wuwJ0SUxfnck/spy-x-family-anya-forger.mp4"
_GIF_FERN = "https://tmpfiles.org/wKwd0EULgca0/fern-headpats-stark-fern.mp4"
_GIF_SAKUTA = "https://tmpfiles.org/wVwb0LL7j0bL/sakuta-azusagawa-mai-sakurajima.mp4"
_GIF_GURA = "https://tmpfiles.org/wRwS0yL2v9Q7/gawr-gura-head-pat.mp4"

_RESPONSES = [
    # ── 1 / kobayashi ──
    (
        _GIF_KOBAYASHI,
        ["5386414139130260061", "4956436416142771580"],
        "{e0} {e1} {user1} gently headpats {user2}.\n\n"
        "A tiny moment of peace in the middle of the chaos.",
    ),
    # ── 2 / senpai ──
    (
        _GIF_SENPAI,
        ["5830278651026873081"],
        "{e0} {user1} gives {user2} a soft headpat.\n\n"
        "+10 Comfort\n"
        "+100 Serotonin.",
    ),
    # ── 3 / anya ──
    (
        _GIF_ANYA,
        ["5911493248483859403"],
        "{e0} {user1} reaches over and headpats {user2}.\n\n"
        "Mission accomplished: Emotional support delivered.",
    ),
    # ── 4 / fern ──
    (
        _GIF_FERN,
        ["5222179653497670288"],
        "{e0} {user1} headpats {user2}.\n\n"
        "A rare gesture. Handle with care.",
    ),
    # ── 5 / sakuta-mai ──
    (
        _GIF_SAKUTA,
        ["5215226264654213464"],
        "{e0} {user1} gently pats {user2}'s head.\n\n"
        "Achievement Unlocked:\n"
        "Certified Comfort Provider.",
    ),
    # ── 6 / gawr-gura ──
    (
        _GIF_GURA,
        ["5818719339255176305", "5962830584551052132", "4958577444454925201"],
        "{e0} {e1} {user1} gently headpats {user2}.\n\n"
        "\"You're doing better than you think.\" {e2}",
    ),
    # ── 7 / kobayashi (reused) ──
    (
        _GIF_KOBAYASHI,
        ["5366472202248009747", "5386414139130260061",
         "5341695605364244563", "6181428412574339821"],
        "{e0} {e1} {user1} softly pats {user2}'s head.\n\n"
        "For just a moment, the world feels a little lighter. {e2} {e3}",
    ),
    # ── 8 / senpai (reused) ──
    (
        _GIF_SENPAI,
        ["5445278980909310899", "5235513242029139973",
         "5440716467215540650", "5460724202996773009"],
        "{e0} {e1} {user1} gives {user2} a warm headpat.\n\n"
        "+1 Happy Thought {e2}\n"
        "+1 Safe Feeling {e3}",
    ),
    # ── 9 / anya (reused) ──
    (
        _GIF_ANYA,
        ["5769543759012303026", "5460858729962421671",
         "5215226264654213464", "4956468890390496140"],
        "{e0} {e1} {user1} carefully headpats {user2}.\n\n"
        "No words needed. Just a quiet reminder that someone cares. {e2} {e3}",
    ),
    # ── 10 / fern (reused) ──
    (
        _GIF_FERN,
        ["4956708038464504901", "5818976758120067408",
         "5969733271305588971", "4958577444454925201"],
        "{e0} {e1} {user1} gives {user2} the gentlest headpat imaginable.\n\n"
        "May your worries shrink, your smile grow, and your day become a "
        "little brighter. {e2} {e3}",
    ),
]


def _render(template: str, emoji_ids: list[str], user1_mention: str, user2_mention: str) -> str:
    tags = {
        f"e{i}": f'<emoji id="{eid}">{_FALLBACK}</emoji>'
        for i, eid in enumerate(emoji_ids)
    }
    return template.format(user1=user1_mention, user2=user2_mention, **tags)


@Client.on_message(filters.command(["pat", "headpat"]))
async def pat_command(client, message):
    logger.info(
        "pat_command fired in chat=%s by user=%s reply=%s args=%s",
        message.chat.id if message.chat else None,
        message.from_user.id if message.from_user else None,
        bool(message.reply_to_message),
        message.command[1:] if message.command else [],
    )

    try:
        target, target_mention = await resolve_target(client, message)
    except Exception:
        logger.exception("pat: resolve_target raised")
        await message.reply_text("🤚 Couldn't resolve the target — try a different form.")
        return

    if target_mention is None:
        await message.reply_text(
            "🤚 Usage:\n"
            "• Reply to a user's message with `/pat`\n"
            "• `/pat <user_id>`\n"
            "• `/pat @username`"
        )
        return

    sender_mention = attacker_mention(message)

    # Self-pat: still allowed but with a dedicated string so it doesn't look broken.
    if target and message.from_user and target.id == message.from_user.id:
        await message.reply_text(
            f'<emoji id="5215226264654213464">{_FALLBACK}</emoji> '
            f"{sender_mention} pats their own head.\n\n"
            f"Self-care counts.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Single random pick — caption stays bonded to its GIF for this response.
    gif_url, emoji_ids, template = random.choice(_RESPONSES)
    caption = _render(template, emoji_ids, sender_mention, target_mention)

    # Send as actual animation media with the caption merged on top —
    # `send_media_gif` walks URL-direct → userbot upload → bot upload.
    if gif_url:
        ok = await send_media_gif(client, message.chat.id, gif_url, caption, message.id)
        if ok:
            logger.info("pat: gif+caption reply ok")
            return
        logger.info("pat: gif send failed across all paths — sending caption only")

    # Text-only fallback: caption alone, no URL paste.
    try:
        await message.reply_text(
            caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("pat: HTML caption reply failed, retrying plain")
        plain = template.format(
            user1=sender_mention, user2=target_mention,
            **{f"e{i}": _FALLBACK for i in range(len(emoji_ids))},
        )
        try:
            await message.reply_text(plain, disable_web_page_preview=True)
        except Exception:
            logger.exception("pat: plain caption reply failed too")
