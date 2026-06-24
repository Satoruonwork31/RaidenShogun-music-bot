"""Single entry point that hands a `Track` to py-tgcalls and reacts to
stream-end events by advancing the per-chat queue.

This module is imported once at startup (from bot/start.py) so the
stream-end handler gets registered on the global `music` instance before
`music.start()` runs.

Why not put this in bot/plugins/play.py: the stream-end auto-advance has
to live somewhere that ALL command plugins can call into without creating
import cycles. The plugin layer should describe commands; the orchestrator
sits one layer below.
"""

from __future__ import annotations

import logging

from pytgcalls.types import AudioQuality, MediaStream

try:
    # py-tgcalls 2.x exposes VideoQuality alongside AudioQuality.
    from pytgcalls.types import VideoQuality  # type: ignore
except Exception:  # pragma: no cover - older / future versions
    VideoQuality = None  # type: ignore

from bot.client import userbot
from bot.utils import queue as q
from bot.utils.music import music

logger = logging.getLogger("RaidenShogun.playback")


def _build_stream(track: q.Track) -> MediaStream:
    """Construct a MediaStream for a Track.

    Audio tracks get AudioQuality.HIGH only. Video tracks add VideoQuality
    when the running py-tgcalls exposes it; older builds fall back to
    audio+default video parameters and rely on yt-dlp having already
    capped resolution at 720p.
    """
    if track.is_video and VideoQuality is not None:
        return MediaStream(
            track.stream_url,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
        )
    if track.is_video:
        # Older py-tgcalls: passing the URL alone with AUTO_DETECT flag tries
        # to bring up both streams from the same source.
        return MediaStream(track.stream_url, audio_parameters=AudioQuality.HIGH)
    return MediaStream(track.stream_url, audio_parameters=AudioQuality.HIGH)


async def play_track(chat_id: int, track: q.Track) -> None:
    """Start (or replace) playback for this chat with the given track.

    Primes the userbot peer cache first — fresh joins via invite link can
    leave the cache unwarmed, after which `phone.JoinGroupCall` fails with
    an opaque TelegramServerError. Mirrors the workaround in ptb_main.py.

    Raises whatever py-tgcalls raises so callers can surface a useful error
    to the user. Updates queue.current on success.
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
        await music.play(chat_id, stream)
    except Exception as exc:
        logger.exception("music.play raised in chat=%s", chat_id)
        raise
    logger.info("music.play returned cleanly for chat=%s", chat_id)
    q.set_current(chat_id, track)


def _is_stream_end(update) -> bool:
    """Version-tolerant check for py-tgcalls stream-end events.

    py-tgcalls renames these types between minor versions (StreamAudioEnded
    → StreamEnded → Update.STREAM_AUDIO_ENDED in different releases). The
    class name is stable enough for routing.
    """
    name = type(update).__name__
    return name in (
        "StreamAudioEnded",
        "StreamVideoEnded",
        "StreamEnded",
    )


@music.on_update()  # type: ignore[misc]
async def _on_pytgcalls_update(_, update) -> None:
    if not _is_stream_end(update):
        return
    chat_id = getattr(update, "chat_id", None)
    if chat_id is None:
        return

    nxt = q.pop_next(chat_id)
    if nxt is None:
        # Queue exhausted — leave the call so the userbot doesn't sit in
        # an empty VC consuming a slot.
        try:
            await music.leave_call(chat_id)
        except Exception as exc:
            logger.info("leave_call after queue-empty failed: %s", exc)
        return

    try:
        await play_track(chat_id, nxt)
    except Exception as exc:
        logger.exception("Auto-advance failed for chat %s", chat_id)
        # Drop the broken track and try the next one. Avoids getting stuck
        # on a single dead URL.
        further = q.pop_next(chat_id)
        if further is not None:
            try:
                await play_track(chat_id, further)
            except Exception:
                logger.exception("Second-chance auto-advance also failed")
