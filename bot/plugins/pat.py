"""/pat — soft, wholesome headpat command.

Triggers:
  /pat                — reply-mode: target is the replied-to user
  /pat @username
  /pat <user_id>
  /pat <text_mention> — Telegram text-mention entity

Each call picks a random caption from a curated pool and renders it
with the attacker and target user mentions. Captions embed Telegram
premium custom emoji via pyrofork's <emoji id="..."> tag; non-premium
clients see the fallback glyph between the tags.

No media is attached — pat is a tiny gesture; a single styled text
reply is the point.
"""

import logging
import random

from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType, ParseMode

logger = logging.getLogger("RaidenShogun.pat")


# Each entry: (list of premium custom emoji ids, caption template).
# The template uses {e0}, {e1}, … for emoji slots and {user1} / {user2}
# for the attacker and target mentions.
_CAPTIONS = [
    (
        ["5386414139130260061", "4956436416142771580"],
        "{e0} {e1} {user1} gently headpats {user2}.\n\n"
        "A tiny moment of peace in the middle of the chaos.",
    ),
    (
        ["5830278651026873081"],
        "{e0} {user1} gives {user2} a soft headpat.\n\n"
        "+10 Comfort\n"
        "+100 Serotonin.",
    ),
    (
        ["5911493248483859403"],
        "{e0} {user1} reaches over and headpats {user2}.\n\n"
        "Mission accomplished: Emotional support delivered.",
    ),
    (
        ["5222179653497670288"],
        "{e0} {user1} headpats {user2}.\n\n"
        "A rare gesture. Handle with care.",
    ),
    (
        ["5215226264654213464"],
        "{e0} {user1} gently pats {user2}'s head.\n\n"
        "Achievement Unlocked:\n"
        "Certified Comfort Provider.",
    ),
    (
        ["5818719339255176305", "5962830584551052132"],
        "{e0} {e1} {user1} gently headpats {user2}.\n\n"
        "\"You're doing better than you think.\"",
    ),
]

# Single fallback glyph used inside every <emoji id=...> tag. Non-premium
# clients see this character; premium clients see the animated custom emoji.
_FALLBACK = "🤚"


def _render(template: str, emoji_ids: list[str], user1_mention: str, user2_mention: str) -> str:
    emoji_tags = {
        f"e{i}": f'<emoji id="{eid}">{_FALLBACK}</emoji>'
        for i, eid in enumerate(emoji_ids)
    }
    return template.format(user1=user1_mention, user2=user2_mention, **emoji_tags)


async def _resolve_target(client, message):
    """Return (user, mention_html) for the /pat target, or (None, None).

    Same shape as /kill's resolver — reply > text_mention entity >
    @username > numeric id.
    """
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

    # Self-pat: still allowed but with a tiny twist so it doesn't look broken.
    if target and message.from_user and target.id == message.from_user.id:
        await message.reply_text(
            f'<emoji id="5215226264654213464">{_FALLBACK}</emoji> '
            f"{attacker_mention} pats their own head.\n\n"
            f"Self-care counts.",
            parse_mode=ParseMode.HTML,
        )
        return

    emoji_ids, template = random.choice(_CAPTIONS)
    text = _render(template, emoji_ids, attacker_mention, target_mention)

    try:
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("pat: sent ok")
    except Exception:
        logger.exception("pat: send failed")
        # Plain-text fallback without the <emoji> tags so a parse-mode
        # problem can't lock us out.
        plain = template.format(
            user1=attacker_mention, user2=target_mention,
            **{f"e{i}": _FALLBACK for i in range(len(emoji_ids))},
        )
        try:
            await message.reply_text(plain, parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("pat: plain-fallback also failed")
