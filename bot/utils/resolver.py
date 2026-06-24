"""Single entry point that turns any user input (plain text, YouTube link,
Spotify link, Resso link, SoundCloud link) into a stream URL that the player
can hand to PyTgCalls.

Resolution rules:
- YouTube URL          -> return as-is, yt-dlp will handle it
- SoundCloud URL       -> return as-is, yt-dlp handles SoundCloud natively
- Spotify track URL    -> read "Artist - Title" from Spotify API, YouTube-search it
- Resso song URL       -> scrape "Artist - Title" from the share page, YouTube-search it
- Anything else (text) -> treat as a YouTube text search

Returns (audio_stream_url, display_query) on success, (None, error_message)
on failure. All known failure modes are caught so the caller can always
edit_text the status message instead of leaving it hanging.
"""

import asyncio
import re

from bot.utils.player import (
    get_audio_stream,
    get_video_stream,
    search_youtube,
)
from bot.utils.resso import is_resso_url, resolve_resso
from bot.utils.spotify import is_spotify_url, resolve_spotify

_YT_RE = re.compile(r"(?:youtube\.com|youtu\.be|music\.youtube\.com)", re.IGNORECASE)
_SC_RE = re.compile(r"(?:soundcloud\.com|snd\.sc)", re.IGNORECASE)


def _humanize_ytdlp_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "sign in to confirm" in text or "not a bot" in text:
        return (
            "YouTube is asking yt-dlp to prove it's not a bot. Add a Netscape "
            "`cookies.txt` from a logged-in YouTube account and set "
            "`COOKIES_FILE=/absolute/path/cookies.txt` in `.env`, then restart."
        )
    if "video unavailable" in text or "private video" in text:
        return "That video is unavailable or private."
    if "age-restricted" in text or "age restricted" in text:
        return "That video is age-restricted. Cookies from a verified account fix this."
    if "no video found" in text or "unable to extract" in text:
        return "yt-dlp couldn't extract that source. It may have been removed or moved."
    return f"yt-dlp error: {exc}"


async def resolve(query: str, *, video: bool = False) -> tuple[str | None, str]:
    query = query.strip()
    extractor = get_video_stream if video else get_audio_stream

    if _YT_RE.search(query) or _SC_RE.search(query):
        try:
            stream = await asyncio.to_thread(extractor, query)
        except Exception as exc:
            return None, _humanize_ytdlp_error(exc)
        if not stream:
            kind = "video" if video else "audio"
            return None, f"Couldn't extract a {kind} stream for that link."
        return stream, query

    if is_spotify_url(query):
        try:
            meta = await resolve_spotify(query)
        except Exception as exc:
            return None, f"Spotify lookup failed: {exc}"
        if not meta:
            return None, (
                "Spotify lookup failed. Make sure SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET are set in .env."
            )
        return await _via_youtube_search(meta, video=video)

    if is_resso_url(query):
        try:
            meta = await resolve_resso(query)
        except Exception as exc:
            return None, f"Resso lookup failed: {exc}"
        if not meta:
            return None, "Couldn't read song info from that Resso link."
        return await _via_youtube_search(meta, video=video)

    return await _via_youtube_search(query, video=video)


async def _via_youtube_search(query: str, *, video: bool = False) -> tuple[str | None, str]:
    extractor = get_video_stream if video else get_audio_stream
    try:
        results = await asyncio.to_thread(search_youtube, query)
    except Exception as exc:
        return None, _humanize_ytdlp_error(exc)
    if not results:
        return None, f"No YouTube result found for: {query}"
    # Normalize: search_youtube may return a single URL (legacy) or a list.
    if isinstance(results, str):
        results = [results]

    last_err: str | None = None
    for url in results:
        try:
            stream = await asyncio.to_thread(extractor, url)
        except Exception as exc:
            last_err = _humanize_ytdlp_error(exc)
            continue
        if stream:
            return stream, query
    kind = "video" if video else "audio"
    return None, last_err or f"Couldn't extract {kind} for: {query}"
