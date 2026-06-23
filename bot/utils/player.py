from yt_dlp import YoutubeDL
from youtubesearchpython import VideosSearch


def search_youtube(query):
    results = VideosSearch(query, limit=1).result()

    if not results["result"]:
        return None

    return results["result"][0]["link"]


def get_audio_stream(url):
    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,
        "noplaylist": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["url"]
