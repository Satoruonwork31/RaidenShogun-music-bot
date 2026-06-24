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

from pytgcalls.types import AudioQuality, GroupCallConfig, MediaStream

try:
    from pytgcalls.types import VideoQuality  # type: ignore
except Exception:  # pragma: no cover
    VideoQuality = None  # type: ignore

from bot.client import userbot
from bot.config import JOIN_AS
from bot.utils import music as music_mod
from bot.utils import queue as q

logger = logging.getLogger("RaidenShogun.playback")

# Cache the resolved JOIN_AS peer so we only hit Telegram once.
_join_as_peer = None
_join_as_attempted = False


async def _resolve_join_as():
    """Resolve the JOIN_AS channel to a peer the first time we need it.

    Returns the resolved InputPeer or None if JOIN_AS is unset / didn't
    resolve. Subsequent calls return the cached value.
    """
    global _join_as_peer, _join_as_attempted
    if _join_as_attempted:
        return _join_as_peer
    _join_as_attempted = True
    if not JOIN_AS:
        return None
    # Pyrofork's resolve_peer treats a string as a @username and rejects
    # numeric chat ids in string form with PEER_ID_INVALID. Coerce
    # JOIN_AS to int when it looks like an id so both env-var forms work:
    #   JOIN_AS=-1001234567890
    #   JOIN_AS=@my_channel
    peer_input: object = JOIN_AS
    stripped = JOIN_AS.lstrip("-")
    if stripped.isdigit():
        peer_input = int(JOIN_AS)
    try:
        peer = await userbot.resolve_peer(peer_input)
        _join_as_peer = peer
        logger.info(
            "JOIN_AS resolved %r → %s — voice chats will be joined as this peer",
            JOIN_AS, type(peer).__name__,
        )
    except Exception as exc:
        logger.warning(
            "JOIN_AS %r could not be resolved: %s — falling back to userbot self",
            JOIN_AS, exc,
        )
        _join_as_peer = None
    return _join_as_peer


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
    join_as_peer = await _resolve_join_as()
    config = GroupCallConfig(join_as=join_as_peer) if join_as_peer is not None else None
    logger.info(
        "music.play(chat=%s) video=%s join_as=%s url_head=%s",
        chat_id, track.is_video, "channel" if join_as_peer else "self",
        (track.stream_url or "")[:80],
    )
    try:
        if config is not None:
            await music_mod.music.play(chat_id, stream, config=config)
        else:
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

    nxt = q.pop_next(chat_id)
    if nxt is None:
        try:
            await music_mod.music.leave_call(chat_id)
        except Exception as exc:
            logger.info("leave_call after queue-empty failed: %s", exc)
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
