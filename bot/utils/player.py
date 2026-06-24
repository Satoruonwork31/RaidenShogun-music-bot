"""yt-dlp wrapper that survives YouTube's anti-bot wall.

Strategy: instead of using a single YouTube `player_client`, try a chain of
clients in order. The newer/embed-style clients (`tv_embedded`,
`mediaconnect_frontend`) frequently slip past the "Sign in to confirm you're
not a bot" check that hits `android` and `web` from server IPs.

If COOKIES_FILE env var is set, cookies are passed in addition — which makes
every client more reliable.
"""

import os

from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError, DownloadError

COOKIES_FILE = os.getenv("COOKIES_FILE", "")

# Order matters — fastest / most reliable first.
PLAYER_CLIENTS = [
    "tv_embedded",
    "mediaconnect_frontend",
    "android",
    "web",
    "ios",
]


def _opts_for(client: str, extra=None) -> dict:
    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": [client]}},
    }
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    if extra:
        opts.update(extra)
    return opts


def _try_extract(url_or_query: str, extra: dict | None = None) -> dict | None:
    last_exc: Exception | None = None
    for client in PLAYER_CLIENTS:
        try:
            with YoutubeDL(_opts_for(client, extra)) as ydl:
                info = ydl.extract_info(url_or_query, download=False)
            if info:
                return info
        except (ExtractorError, DownloadError) as exc:
            text = str(exc).lower()
            # "format not available" / "no formats found" → try next client.
            # "Sign in" / "not a bot" → also try next, in case one slips through.
            last_exc = exc
            if any(
                marker in text
                for marker in (
                    "format is not available",
                    "no video formats",
                    "no formats",
                    "sign in",
                    "not a bot",
                    "could not find",
                )
            ):
                continue
            raise
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    return None


def search_youtube(query):
    info = _try_extract(
        query,
        {"default_search": "ytsearch1", "extract_flat": "in_playlist"},
    )
    if not isinstance(info, dict):
        return None
    entries = info.get("entries")
    if entries:
        entry = entries[0]
        return entry.get("webpage_url") or entry.get("url")
    return info.get("webpage_url")


def get_audio_stream(url):
    info = _try_extract(url)
    if not isinstance(info, dict):
        return None
    stream = info.get("url")
    if stream:
        return stream
    formats = info.get("formats") or []
    return formats[-1]["url"] if formats else None
