"""Shared helpers for social/fun commands (/pat, /aura, future
/vibe etc.).

Lives in `bot/utils/` rather than `bot/plugins/` deliberately:
`plugins=dict(root="bot.plugins")` auto-scans every module under
plugins for `@Client.on_message` handlers. If one plugin top-level-
imports another plugin module, that nested re-entrant import can
interact badly with the scanner's handler registration. Rule for
this repo: **plugin files must never import from other plugin
files at module level.** Shared logic lives here instead.

What's here:
- `_FALLBACK`        — single fallback glyph for every <emoji id=...> tag
- `resolve_target()` — text-mention → reply → @username/user_id arg
- `send_media_gif()` — URL-direct → userbot upload → bot upload chain
- the helpers `send_media_gif` walks internally:
  `_candidate_urls`, `_download_gif`, `_try_url_send`, `_try_local_send`
"""

import asyncio
import logging
import os
import tempfile

import aiohttp
from pyrogram.enums import MessageEntityType, ParseMode

logger = logging.getLogger("RaidenShogun.social")

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
                fd, path = tempfile.mkstemp(suffix=".mp4", prefix="social_gif_")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                _gif_path_cache[url] = path
                logger.info("social: cached %s → %s (%d bytes)", url, path, len(data))
                return path
            except Exception as exc:
                logger.info("social: download %s failed: %s", try_url, exc)
        return None


async def _try_url_send(client, chat_id, url, caption, reply_to_id) -> bool:
    """URL-direct send_animation (Telegram fetches the URL).
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
            logger.info("social: URL send OK via %s", try_url)
            return True
        except asyncio.TimeoutError:
            logger.warning("social: URL send timed out for %s", try_url)
        except Exception as exc:
            logger.info("social: URL send failed for %s: %s", try_url, type(exc).__name__)
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
        logger.info("social: %s upload OK", label)
        return True
    except asyncio.TimeoutError:
        logger.warning("social: %s upload timed out after %ss, cancelling", label, timeout)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return False
    except Exception as exc:
        logger.info("social: %s upload failed: %s", label, type(exc).__name__)
        return False


async def send_media_gif(bot_client, chat_id, gif_url, caption, reply_to_id) -> bool:
    """Send the GIF via the best available path. Returns True on success.

    Order:
      0. If `gif_url` is a Telegram file_id (not an http URL), send it
         directly — instant, no external host, no download. THIS is the
         recommended permanent fix: re-upload each GIF once via the bot
         to capture a bot-usable file_id and put that string in the
         caller's response table instead of a tmpfiles URL.
      1. URL-direct via bot client. Skipped for tmpfiles.org because it
         consistently returns WEBPAGE_CURL_FAILED.
      2. Download once, upload via userbot (works in chats where the
         assistant userbot is a member).
      3. Download once, upload via bot client (subject to the
         pyrofork+ntgcalls bot-client media-DC hang).
    """
    # Path 0 — file_id direct. A file_id is not an http(s) URL.
    if not gif_url.lower().startswith(("http://", "https://")):
        try:
            await asyncio.wait_for(
                bot_client.send_animation(
                    chat_id=chat_id, animation=gif_url, caption=caption,
                    parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id,
                ),
                timeout=15,
            )
            logger.info("social: file_id send OK")
            return True
        except Exception as exc:
            logger.warning("social: file_id send failed (%s) — asset may be deleted", type(exc).__name__)
            return False

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
            logger.info("social: userbot.get_chat(%s) failed: %s — userbot may not be in this chat", chat_id, exc)
        if await _try_local_send(_ub, chat_id, local_path, caption, None,
                                  label="userbot", timeout=15):
            return True
    except Exception:
        logger.exception("social: userbot path errored")

    # Bot-client fallback. Short timeout (10s) because this path almost
    # always hangs on this pyrofork+ntgcalls build — we don't want to
    # make the user wait a minute for a failure we've seen before.
    return await _try_local_send(bot_client, chat_id, local_path, caption,
                                  reply_to_id, label="bot", timeout=10)


async def resolve_target(client, message):
    """Return (user, mention_html) for a social-command target, or
    (None, None). Resolution order matches /pat's original behavior:
    text-mention entity → reply-to-message → @username/user_id arg.
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


def attacker_mention(message) -> str:
    """The sender's display mention — used for templates that show the
    invoker (e.g. `/pat`'s "{user1} headpats {user2}"). /aura doesn't
    use this, but `/pat` and any future similar command do.
    """
    user = message.from_user
    if not user:
        return "someone"
    return user.mention or (user.first_name or str(user.id))
