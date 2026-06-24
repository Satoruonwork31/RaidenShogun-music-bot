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


def _opts_for(client: str, extra=None, *, video: bool = False) -> dict:
    # YouTube serves muxed audio+video only up to 720p. Above that the streams
    # are split and would need ffmpeg to remux on the fly, which py-tgcalls
    # already does — but staying at 720p avoids surprises on low-CPU VPSes.
    fmt = "best[height<=720]/best" if video else "bestaudio/best"
    opts = {
        "format": fmt,
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": [client]}},
        # Auto-download signature solver from yt-dlp/ejs releases on first run.
        # Required since YouTube enforces n-challenge + PO Tokens on server IPs.
        "remote_components": ["ejs:github"],
    }
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    if extra:
        opts.update(extra)
    return opts


def _try_extract(url_or_query: str, extra: dict | None = None, *, video: bool = False) -> dict | None:
    last_exc: Exception | None = None
    for client in PLAYER_CLIENTS:
        try:
            with YoutubeDL(_opts_for(client, extra, video=video)) as ydl:
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


def search_youtube(query, limit: int = 5):
    """Return up to `limit` candidate YouTube watch URLs.

    Returns either a single URL (kept for back-compat with old callers) or a
    list of URLs. The resolver iterates through the list so that if YouTube
    gates one result with the bot wall, we can try the next.
    """
    info = _try_extract(
        query,
        {"default_search": f"ytsearch{limit}", "extract_flat": "in_playlist"},
    )
    if not isinstance(info, dict):
        return []
    entries = info.get("entries") or []
    urls = []
    for entry in entries[:limit]:
        link = entry.get("webpage_url") or entry.get("url")
        if link:
            urls.append(link)
    if not urls and info.get("webpage_url"):
        urls.append(info["webpage_url"])
    return urls if urls else None


def _extract_stream(url: str, *, video: bool) -> str | None:
    info = _try_extract(url, video=video)
    if not isinstance(info, dict):
        return None
    stream = info.get("url")
    if stream:
        return stream
    formats = info.get("formats") or []
    return formats[-1]["url"] if formats else None


def get_audio_stream(url):
    return _extract_stream(url, video=False)


def get_video_stream(url):
    return _extract_stream(url, video=True)


def get_title(url: str) -> str | None:
    """Best-effort fetch of the human-readable title for a URL.

    Used to render `/queue` lines. Falls back to None on any error so callers
    can substitute the raw query.
    """
    try:
        info = _try_extract(url)
    except Exception:
        return None
    if isinstance(info, dict):
        return info.get("title")
    return None
