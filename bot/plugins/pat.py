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
import os
import random
import tempfile

import aiohttp
from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType, ParseMode

logger = logging.getLogger("RaidenShogun.pat")

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)
_gif_path_cache: dict[str, str] = {}
_gif_cache_lock = asyncio.Lock()

# Single fallback glyph for every <emoji id=...> tag. Non-premium clients
# see this; premium clients see the animated custom emoji.
_FALLBACK = "🤚"

# Per-caption send timeout. tmpfiles.org via the /dl/ direct path
# typically resolves in ~1s; 25s is room for both the fetch and the
# Telegram-side ingest.
_SEND_TIMEOUT = 25


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


async def _download_gif(url: str) -> str | None:
    """Download a GIF to /tmp once and cache the local path."""
    async with _gif_cache_lock:
        cached = _gif_path_cache.get(url)
        if cached and os.path.exists(cached):
            return cached
        for try_url in _candidate_urls(url):
            try:
                async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as s:
                    async with s.get(try_url, allow_redirects=True) as resp:
                        if resp.status != 200:
                            continue
                        ctype = (resp.headers.get("Content-Type") or "").lower()
                        if "text/html" in ctype:
                            continue
                        data = await resp.read()
                        if not data or len(data) < 512:
                            continue
                fd, path = tempfile.mkstemp(suffix=".mp4", prefix="pat_gif_")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                _gif_path_cache[url] = path
                logger.info("pat: cached %s → %s (%d bytes)", url, path, len(data))
                return path
            except Exception as exc:
                logger.info("pat: download %s failed: %s", try_url, exc)
        return None


async def _try_url_send(client, chat_id, url, caption, reply_to_id) -> bool:
    """Attempt URL-direct send_animation (Telegram fetches the URL).
    Cheapest path; fails fast with WEBPAGE_CURL_FAILED for hosts Telegram
    can't reach (tmpfiles.org returns that). 15s wait_for cap.
    """
    for try_url in _candidate_urls(url):
        try:
            await asyncio.wait_for(
                client.send_animation(
                    chat_id=chat_id, animation=try_url, caption=caption,
                    parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id,
                ),
                timeout=15,
            )
            logger.info("pat: URL send OK via %s", try_url)
            return True
        except asyncio.TimeoutError:
            logger.warning("pat: URL send timed out for %s", try_url)
        except Exception as exc:
            logger.info("pat: URL send failed for %s: %s", try_url, type(exc).__name__)
    return False


async def _try_local_send(client, chat_id, path, caption, reply_to_id,
                           label: str, timeout: int = 20) -> bool:
    """Upload a local file via send_animation, with a forced-cancel
    timeout so a media-DC hang surfaces fast instead of stalling the
    user's reply.
    """
    task = asyncio.create_task(client.send_animation(
        chat_id=chat_id, animation=path, caption=caption,
        parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id,
    ))
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        logger.info("pat: %s upload OK", label)
        return True
    except asyncio.TimeoutError:
        logger.warning("pat: %s upload timed out after %ss, cancelling", label, timeout)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return False
    except Exception as exc:
        logger.info("pat: %s upload failed: %s", label, type(exc).__name__)
        return False


async def _send_pat_gif(bot_client, chat_id, gif_url, caption, reply_to_id) -> bool:
    """Send the GIF via the best available path. Returns True on success.

    Order:
      1. URL-direct via bot client. Skipped for tmpfiles.org because it
         consistently returns WEBPAGE_CURL_FAILED.
      2. Download once, upload via userbot (works in chats where the
         assistant userbot is a member).
      3. Download once, upload via bot client (subject to the
         pyrofork+ntgcalls bot-client media-DC hang).
    """
    if "tmpfiles.org" not in gif_url:
        if await _try_url_send(bot_client, chat_id, gif_url, caption, reply_to_id):
            return True

    local_path = await _download_gif(gif_url)
    if not local_path:
        return False

    try:
        from bot.client import userbot as _ub
        # Prime the userbot peer cache. Without this, the FIRST
        # send_animation call for a previously-unseen chat raises
        # KeyError 'ID not found: <chat>' (pyrofork's resolve_peer lookup
        # only knows chats it's seen updates for during the session).
        # get_chat populates the cache, so the actual send below works
        # on the first attempt instead of having to wait for some
        # unrelated update to warm it.
        try:
            await _ub.get_chat(chat_id)
        except Exception as exc:
            logger.info("pat: userbot.get_chat(%s) failed: %s — userbot may not be in this chat", chat_id, exc)
        if await _try_local_send(_ub, chat_id, local_path, caption, None,
                                  label="userbot", timeout=15):
            return True
    except Exception:
        logger.exception("pat: userbot path errored")

    # Bot-client fallback. Short timeout (10s) because this path almost
    # always hangs on this pyrofork+ntgcalls build — we don't want to
    # make the user wait a minute for a failure we've seen before.
    return await _try_local_send(bot_client, chat_id, local_path, caption,
                                  reply_to_id, label="bot", timeout=10)


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

    # Single random pick — gif_url and caption stay bonded.
    gif_url, emoji_ids, template = random.choice(_RESPONSES)
    caption = _render(template, emoji_ids, attacker_mention, target_mention)

    ok = await _send_pat_gif(client, message.chat.id, gif_url, caption, message.id)
    if ok:
        return
    logger.info("pat: gif send failed across all paths — sending caption only (no URL)")

    # CAPTION-ONLY fallback. Under no circumstances does this path include
    # the gif URL in the message body — the user must never see the raw
    # tmpfiles link as plain text.
    try:
        await message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("pat: caption-only reply ok")
    except Exception:
        logger.exception("pat: HTML caption reply failed, retrying plain")
        # Last-ditch: strip emoji tags. Still no URL.
        plain = template.format(
            user1=attacker_mention, user2=target_mention,
            **{f"e{i}": _FALLBACK for i in range(len(emoji_ids))},
        )
        try:
            await message.reply_text(plain, disable_web_page_preview=True)
        except Exception:
            logger.exception("pat: plain caption reply failed too")
