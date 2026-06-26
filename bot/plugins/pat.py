"""/pat — soft, wholesome headpat command.

Triggers:
  /pat                — reply-mode: target is the replied-to user
  /pat @username
  /pat <user_id>
  /pat <text_mention> — Telegram text-mention entity

Each call picks a random entry from `_CAPTIONS`. Each entry carries:
  - a list of premium custom emoji ids (rendered as <emoji id="..."> tags)
  - a caption template using {e0}/{e1}/... slots and {user1}/{user2}
  - an optional gif URL — Telegram fetches it server-side (we do NOT
    upload from the bot, which hangs on this pyrofork build, same
    issue /kill hit)

If the gif URL fails, we fall back to a plain text reply with the
same caption.

Captions 1-5 are the original text-only set. Captions 6-10 add GIFs.
"""

import asyncio
import logging
import random

from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType, ParseMode

logger = logging.getLogger("RaidenShogun.pat")

# Single fallback glyph for every <emoji id=...> tag. Non-premium clients
# see this; premium clients see the animated custom emoji.
_FALLBACK = "🤚"

# Per-caption send timeout. tmpfiles.org via the /dl/ direct path
# typically resolves in ~1s; 25s is room for both the fetch and the
# Telegram-side ingest.
_SEND_TIMEOUT = 25


# Each entry: (emoji_ids, template, gif_url_or_None)
# Templates use {e0}, {e1}, ... in the order emojis appear in the line.
_CAPTIONS = [
    # ── Caption 1 ──
    (
        ["5386414139130260061", "4956436416142771580"],
        "{e0} {e1} {user1} gently headpats {user2}.\n\n"
        "A tiny moment of peace in the middle of the chaos.",
        None,
    ),
    # ── Caption 2 ──
    (
        ["5830278651026873081"],
        "{e0} {user1} gives {user2} a soft headpat.\n\n"
        "+10 Comfort\n"
        "+100 Serotonin.",
        None,
    ),
    # ── Caption 3 ──
    (
        ["5911493248483859403"],
        "{e0} {user1} reaches over and headpats {user2}.\n\n"
        "Mission accomplished: Emotional support delivered.",
        None,
    ),
    # ── Caption 4 ──
    (
        ["5222179653497670288"],
        "{e0} {user1} headpats {user2}.\n\n"
        "A rare gesture. Handle with care.",
        None,
    ),
    # ── Caption 5 ──
    (
        ["5215226264654213464"],
        "{e0} {user1} gently pats {user2}'s head.\n\n"
        "Achievement Unlocked:\n"
        "Certified Comfort Provider.",
        None,
    ),
    # ── Caption 6 ──
    (
        ["5818719339255176305", "5962830584551052132", "4958577444454925201"],
        "{e0} {e1} {user1} gently headpats {user2}.\n\n"
        "\"You're doing better than you think.\" {e2}",
        "https://tmpfiles.org/wlwt01UyeFY0/kobayashi-dragon.mp4",
    ),
    # ── Caption 7 ──
    (
        ["5366472202248009747", "5386414139130260061",
         "5341695605364244563", "6181428412574339821"],
        "{e0} {e1} {user1} softly pats {user2}'s head.\n\n"
        "For just a moment, the world feels a little lighter. {e2} {e3}",
        "https://tmpfiles.org/wZwA0GUlffqV/senpai-ga-uzai-kouhai-no-hanashi-futaba.mp4",
    ),
    # ── Caption 8 ──
    (
        ["5445278980909310899", "5235513242029139973",
         "5440716467215540650", "5460724202996773009"],
        "{e0} {e1} {user1} gives {user2} a warm headpat.\n\n"
        "+1 Happy Thought {e2}\n"
        "+1 Safe Feeling {e3}",
        "https://tmpfiles.org/wuwJ0SUxfnck/spy-x-family-anya-forger.mp4",
    ),
    # ── Caption 9 ──
    (
        ["5769543759012303026", "5460858729962421671",
         "5215226264654213464", "4956468890390496140"],
        "{e0} {e1} {user1} carefully headpats {user2}.\n\n"
        "No words needed. Just a quiet reminder that someone cares. {e2} {e3}",
        "https://tmpfiles.org/wKwd0EULgca0/fern-headpats-stark-fern.mp4",
    ),
    # ── Caption 10 ──
    (
        ["4956708038464504901", "5818976758120067408",
         "5969733271305588971", "4958577444454925201"],
        "{e0} {e1} {user1} gives {user2} the gentlest headpat imaginable.\n\n"
        "May your worries shrink, your smile grow, and your day become a "
        "little brighter. {e2} {e3}",
        "https://tmpfiles.org/wVwb0LL7j0bL/sakuta-azusagawa-mai-sakurajima.mp4",
    ),
    # The 6th supplied gif URL (gawr-gura-head-pat.mp4) is currently
    # unassigned. Tell the operator which caption to attach it to and
    # add a new entry referencing it.
]


def _render(template: str, emoji_ids: list[str], user1_mention: str, user2_mention: str) -> str:
    tags = {
        f"e{i}": f'<emoji id="{eid}">{_FALLBACK}</emoji>'
        for i, eid in enumerate(emoji_ids)
    }
    return template.format(user1=user1_mention, user2=user2_mention, **tags)


def _candidate_urls(url: str) -> list[str]:
    """For tmpfiles.org, the share URL returns an HTML preview page;
    the actual media is at /dl/<id>/<name>. Try both.
    """
    if not url:
        return []
    out = []
    if "tmpfiles.org/" in url and "/dl/" not in url:
        out.append(url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1))
    out.append(url)
    return out


async def _send_animation_url(client, chat_id, gif_url, caption, reply_to_id) -> bool:
    """Try send_animation with a remote URL. Returns True on success."""
    for try_url in _candidate_urls(gif_url):
        try:
            await asyncio.wait_for(
                client.send_animation(
                    chat_id=chat_id,
                    animation=try_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=reply_to_id,
                ),
                timeout=_SEND_TIMEOUT,
            )
            logger.info("pat: send_animation OK via %s", try_url)
            return True
        except asyncio.TimeoutError:
            logger.warning("pat: send_animation timed out for %s", try_url)
        except Exception:
            logger.exception("pat: send_animation raised for %s", try_url)
    return False


async def _resolve_target(client, message):
    """Return (user, mention_html) for the /pat target, or (None, None)."""
    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            return ent.user, ent.user.mention

    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user, reply.from_user.mention

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
        return u, u.mention
    except Exception:
        if raw.isdigit():
            uid = int(raw)
            return None, f'<a href="tg://user?id={uid}">user {uid}</a>'
        return None, None


def _attacker_mention(message) -> str:
    user = message.from_user
    if not user:
        return "someone"
    return user.mention or (user.first_name or str(user.id))


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
        target, target_mention = await _resolve_target(client, message)
    except Exception:
        logger.exception("pat: _resolve_target raised")
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

    attacker_mention = _attacker_mention(message)

    # Self-pat: still allowed but with a dedicated string so it doesn't look broken.
    if target and message.from_user and target.id == message.from_user.id:
        await message.reply_text(
            f'<emoji id="5215226264654213464">{_FALLBACK}</emoji> '
            f"{attacker_mention} pats their own head.\n\n"
            f"Self-care counts.",
            parse_mode=ParseMode.HTML,
        )
        return

    emoji_ids, template, gif_url = random.choice(_CAPTIONS)
    text = _render(template, emoji_ids, attacker_mention, target_mention)

    if gif_url:
        ok = await _send_animation_url(
            client, message.chat.id, gif_url, text, message.id
        )
        if ok:
            return
        # Fall through to text-only if the gif send failed.
        logger.info("pat: gif send failed, falling back to text")

    try:
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("pat: text reply ok")
    except Exception:
        logger.exception("pat: text reply failed")
        # Last-ditch: strip emoji tags entirely.
        plain = template.format(
            user1=attacker_mention, user2=target_mention,
            **{f"e{i}": _FALLBACK for i in range(len(emoji_ids))},
        )
        try:
            await message.reply_text(plain)
        except Exception:
            logger.exception("pat: plain fallback failed too")
