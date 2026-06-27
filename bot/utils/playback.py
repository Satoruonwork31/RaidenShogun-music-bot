"""Single entry point that hands a `Track` to py-tgcalls and reacts to
stream-end events by advancing the per-chat queue.

The PyTgCalls instance is constructed lazily inside the running event
loop (see bot.utils.music.init). This module therefore:
- Accesses `music` via the module attribute (`music_mod.music`) instead
  of name-binding it at import time — so it always sees the live
  instance.
- Registers the @on_update stream-end handler in `register_handlers()`,
  which is called from bot.start._run AFTER init.
"""

from __future__ import annotations

import logging

from pytgcalls.types import AudioQuality, MediaStream

try:
    from pytgcalls.types import VideoQuality  # type: ignore
except Exception:  # pragma: no cover
    VideoQuality = None  # type: ignore

from bot.client import userbot
from bot.utils import music as music_mod
from bot.utils import queue as q

logger = logging.getLogger("RaidenShogun.playback")


async def end_session(chat_id: int) -> None:
    """Tear down the VC session for `chat_id` and pull the assistant
    out of the group.

    Steps:
      1. Clear the per-chat queue.
      2. Tell py-tgcalls to leave the call (ignore errors — we might
         already be out).
      3. Have the userbot leave the group entirely — anti-misuse:
         once playback is done the assistant should not linger.

    Best-effort throughout. Logs but never raises.
    """
    try:
        q.clear(chat_id)
    except Exception:
        logger.exception("end_session: queue.clear failed for %s", chat_id)

    if music_mod.music is not None:
        try:
            await music_mod.music.leave_call(chat_id)
        except Exception as exc:
            # Most common: NotInGroupCallError — VC already ended on its own.
            logger.info("end_session: leave_call(%s) noop/err: %s", chat_id, exc)

    try:
        await userbot.leave_chat(chat_id)
        # WARNING level on purpose: this is the prime suspect for
        # greetings/departure not firing. Once the userbot leaves, the
        # userbot-side ChatMemberUpdated dispatch (bot/start.py) stops
        # seeing member events for this chat until /play re-invites it.
        logger.warning(
            "end_session: userbot LEFT chat %s — it will no longer receive "
            "ChatMemberUpdated (join/leave) events here until re-invited via /play",
            chat_id,
        )
    except Exception as exc:
        logger.info("end_session: userbot.leave_chat(%s) failed: %s", chat_id, exc)


async def ensure_userbot_in_chat(client_app, chat_id: int) -> tuple[bool, str]:
    """Make sure the userbot is a member of `chat_id`. Returns (ok, detail).

    Two paths, picked by chat visibility:
      • Public chat (chat.username set) → userbot.join_chat(username).
        No dependence on the BOT's invite-link rights — a username is a
        public address any account can use to walk in.
      • Private chat (no username) → bot exports an invite link, userbot
        joins via the link. Requires the bot to be admin with invite
        rights, hence the older code's failure mode.

    Public-path failures get logged with exc type+message so we can tell
    a Telegram per-account cap (TooManyChannels, FloodWait) apart from a
    chat-side restriction (CHAT_INVALID, USERNAME_INVALID).
    """
    from pyrogram.enums import ChatMemberStatus

    try:
        me = await userbot.get_me()
        member = await userbot.get_chat_member(chat_id, me.id)
        if member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            return True, "already a member"
    except Exception as exc:
        logger.debug("ensure_userbot_in_chat: presence probe failed: %s", exc)

    username = None
    try:
        chat = await client_app.get_chat(chat_id)
        username = getattr(chat, "username", None)
    except Exception as exc:
        logger.debug("ensure_userbot_in_chat: get_chat(%s) failed: %s", chat_id, exc)

    if username:
        try:
            await userbot.join_chat(username)
            logger.info("ensure_userbot_in_chat: userbot joined %s via username @%s", chat_id, username)
            return True, "joined via username"
        except Exception as exc:
            logger.warning(
                "ensure_userbot_in_chat: username join failed for %s (@%s): %s: %s",
                chat_id, username, type(exc).__name__, exc,
            )
            # Don't fall through to invite link for public chats — if the
            # username path failed, the cause is almost certainly per-
            # account (rate limit, channel cap, ban) and inviting via a
            # link won't help. Surface that to the operator.
            return False, (
                f"Assistant couldn't join @{username}: {type(exc).__name__}: {exc}\n"
                "Likely cause: the assistant account is rate-limited, "
                "hit the per-account group cap, or is banned from this chat."
            )

    try:
        link = await client_app.export_chat_invite_link(chat_id)
        await userbot.join_chat(link)
        logger.info("ensure_userbot_in_chat: userbot joined %s via invite link", chat_id)
        return True, "joined via invite link"
    except Exception as exc:
        logger.warning(
            "ensure_userbot_in_chat: invite-link join failed for %s: %s: %s",
            chat_id, type(exc).__name__, exc,
        )
        return False, (
            "Assistant isn't in the group and I couldn't auto-invite it.\n"
            "Either make me a group admin with invite rights, or invite the assistant account manually."
        )


def _build_stream(track: q.Track) -> MediaStream:
    if track.is_video and VideoQuality is not None:
        return MediaStream(
            track.stream_url,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
        )
    if track.is_video:
        return MediaStream(track.stream_url, audio_parameters=AudioQuality.HIGH)
    return MediaStream(track.stream_url, audio_parameters=AudioQuality.HIGH)


async def play_track(chat_id: int, track: q.Track) -> None:
    """Start or replace playback for this chat. Primes the userbot peer
    cache, builds a MediaStream, hands off to music.play, updates queue.
    """
    try:
        await userbot.get_chat(chat_id)
    except Exception as exc:
        logger.warning("userbot.get_chat(%s) failed before play: %s", chat_id, exc)

    stream = _build_stream(track)
    logger.info(
        "music.play(chat=%s) video=%s url_head=%s",
        chat_id, track.is_video, (track.stream_url or "")[:80],
    )
    try:
        await music_mod.music.play(chat_id, stream)
    except Exception:
        logger.exception("music.play raised in chat=%s", chat_id)
        raise
    logger.info("music.play returned cleanly for chat=%s", chat_id)
    q.set_current(chat_id, track)


def _is_stream_end(update) -> bool:
    """Version-tolerant check for py-tgcalls stream-end events.

    py-tgcalls renames these types across minor versions; the class name
    is stable enough for routing.
    """
    name = type(update).__name__
    return name in ("StreamAudioEnded", "StreamVideoEnded", "StreamEnded")


async def _on_pytgcalls_update(_, update) -> None:
    if not _is_stream_end(update):
        return
    chat_id = getattr(update, "chat_id", None)
    if chat_id is None:
        return

    # Repeat-current short-circuits the queue advance entirely.
    if q.get_repeat(chat_id):
        cur = q.now_playing(chat_id)
        if cur is not None:
            try:
                await play_track(chat_id, cur)
            except Exception:
                logger.exception("Repeat-replay failed for chat %s", chat_id)
                await end_session(chat_id)
            return

    nxt = q.pop_next(chat_id)
    if nxt is None:
        # Queue exhausted: end the session AND have the assistant exit the
        # group. The userbot doesn't linger after playback finishes —
        # anti-misuse measure. Users invite the assistant back next time.
        await end_session(chat_id)
        return

    try:
        await play_track(chat_id, nxt)
    except Exception:
        logger.exception("Auto-advance failed for chat %s", chat_id)
        further = q.pop_next(chat_id)
        if further is not None:
            try:
                await play_track(chat_id, further)
            except Exception:
                logger.exception("Second-chance auto-advance also failed")


def register_handlers() -> None:
    """Register the stream-end auto-advance on the live music instance.

    Called from bot.start._run after bot.utils.music.init has constructed
    PyTgCalls. Equivalent to the old `@music.on_update()` module-level
    decorator, but deferred so the music instance actually exists.
    """
    if music_mod.music is None:
        raise RuntimeError(
            "playback.register_handlers called before music.init"
        )
    music_mod.music.on_update()(_on_pytgcalls_update)
