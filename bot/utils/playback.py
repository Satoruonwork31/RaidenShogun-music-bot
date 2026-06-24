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
