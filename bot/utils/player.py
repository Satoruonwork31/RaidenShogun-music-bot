from yt_dlp import YoutubeDL


def search_youtube(query):
    ydl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android"]
        }
    }
}

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if not entries:
        return None

    entry = entries[0]
    return entry.get("webpage_url") or entry.get("url")


def get_audio_stream(url):
    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,
        "noplaylist": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        return None

    stream = info.get("url")
    if stream:
        return stream

    formats = info.get("formats") or []
    return formats[-1]["url"] if formats else None
