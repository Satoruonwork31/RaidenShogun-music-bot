import os

from yt_dlp import YoutubeDL

# Optional path to a Netscape-format cookies.txt for YouTube. If set, yt-dlp
# acts as your logged-in account and bypasses "Sign in to confirm you're not a
# bot" blocks. Set COOKIES_FILE=/path/to/cookies.txt in .env (or in the env).
COOKIES_FILE = os.getenv("COOKIES_FILE", "")


def _opts(extra=None):
    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"],
            },
        },
    }
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    if extra:
        opts.update(extra)
    return opts


def search_youtube(query):
    opts = _opts({"default_search": "ytsearch1", "extract_flat": "in_playlist"})

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if not entries:
        return None

    entry = entries[0]
    return entry.get("webpage_url") or entry.get("url")


def get_audio_stream(url):
    with YoutubeDL(_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        return None

    stream = info.get("url")
    if stream:
        return stream

    formats = info.get("formats") or []
    return formats[-1]["url"] if formats else None
