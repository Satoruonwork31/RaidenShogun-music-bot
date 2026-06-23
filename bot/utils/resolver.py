"""Single entry point that turns any user input (plain text, YouTube link,
Spotify link, Resso link, SoundCloud link) into a stream URL that the player
can hand to PyTgCalls.

Resolution rules:
- YouTube URL          -> return as-is, yt-dlp will handle it
- SoundCloud URL       -> return as-is, yt-dlp handles SoundCloud natively
- Spotify track URL    -> read "Artist - Title" from Spotify API, YouTube-search it
- Resso song URL       -> scrape "Artist - Title" from the share page, YouTube-search it
- Anything else (text) -> treat as a YouTube text search

Returns (audio_stream_url, display_query) on success, (None, error_message) on failure.
"""

import asyncio
import re

from bot.utils.player import get_audio_stream, search_youtube
from bot.utils.resso import is_resso_url, resolve_resso
from bot.utils.spotify import is_spotify_url, resolve_spotify

_YT_RE = re.compile(r"(?:youtube\.com|youtu\.be|music\.youtube\.com)", re.IGNORECASE)
_SC_RE = re.compile(r"(?:soundcloud\.com|snd\.sc)", re.IGNORECASE)


async def resolve(query: str) -> tuple[str | None, str]:
    query = query.strip()

    # Direct platforms handled by yt-dlp.
    if _YT_RE.search(query) or _SC_RE.search(query):
        stream = await asyncio.to_thread(get_audio_stream, query)
        if not stream:
            return None, "Couldn't extract an audio stream for that link."
        return stream, query

    # Spotify -> metadata -> YouTube.
    if is_spotify_url(query):
        meta = await resolve_spotify(query)
        if not meta:
            return None, (
                "Spotify lookup failed. Make sure SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET are set in .env."
            )
        return await _via_youtube_search(meta)

    # Resso -> metadata -> YouTube.
    if is_resso_url(query):
        meta = await resolve_resso(query)
        if not meta:
            return None, "Couldn't read song info from that Resso link."
        return await _via_youtube_search(meta)

    # Plain text -> YouTube search.
    return await _via_youtube_search(query)


async def _via_youtube_search(query: str) -> tuple[str | None, str]:
    url = await asyncio.to_thread(search_youtube, query)
    if not url:
        return None, f"No YouTube result found for: {query}"
    stream = await asyncio.to_thread(get_audio_stream, url)
    if not stream:
        return None, f"Couldn't extract audio for: {query}"
    return stream, query
