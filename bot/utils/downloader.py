"""yt-dlp download wrappers for /song and /video.

Distinct from bot/utils/player.py — that module extracts streaming URLs
for py-tgcalls. This one writes a file to disk that the bot can upload
to Telegram via send_audio / send_video.

Reuses player.PLAYER_CLIENTS so the same anti-bot-wall fallback chain
applies. Audio downloads are post-processed to mp3@192k via ffmpeg
(installed by scripts/install.sh).

Caller is responsible for deleting the returned file. The download dir
sits under /tmp so a reboot reaps any leaks.
"""

from __future__ import annotations

import os

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from bot.utils.player import COOKIES_FILE, PLAYER_CLIENTS

DOWNLOAD_DIR = "/tmp/raiden_downloads"

# Hard duration cap so a user can't accidentally `/song <2-hour podcast>`
# and fill the VPS disk + wait forever for upload. 20 minutes covers any
# reasonable song or short video.
MAX_DURATION_SECONDS = 20 * 60

# Telegram's hard upload limit for bots over Pyrogram (MTProto) is 2 GB,
# but huge files take long enough that the userbot can hit a flood wait.
# Cap at 1.5 GB and refuse upfront.
MAX_FILE_BYTES = 1_500_000_000

_RETRY_MARKERS = (
    "format is not available",
    "no video formats",
    "no formats",
    "sign in",
    "not a bot",
    "could not find",
)


def _opts(client: str, *, video: bool, quality: str | None = None) -> dict:
    outtmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    postprocessors: list[dict] = []
    merge_to_mp4 = False
    if video:
        # quality: "480" | "720" | "1080" | None (=> 720 default).
        # Modern YouTube splits >=720p into video-only + audio-only streams,
        # so a single muxed-mp4 selector would fail with "format not
        # available". Try muxed first (cheap, no ffmpeg work), then fall
        # through to bestvideo+bestaudio (yt-dlp will merge via ffmpeg).
        try:
            cap = int(quality) if quality else 720
        except (TypeError, ValueError):
            cap = 720
        fmt = (
            f"best[height<={cap}][ext=mp4]/"
            f"bestvideo[height<={cap}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={cap}]+bestaudio/"
            f"best[height<={cap}]/best"
        )
        merge_to_mp4 = True
    else:
        fmt = "bestaudio/best"
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    opts: dict = {
        "format": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": [client]}},
        "remote_components": ["ejs:github"],
    }
    if merge_to_mp4:
        opts["merge_output_format"] = "mp4"
    if postprocessors:
        opts["postprocessors"] = postprocessors
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    return opts


def _final_path(info: dict, *, video: bool) -> str | None:
    """Find the on-disk path after yt-dlp finishes (including post-process)."""
    requested = info.get("requested_downloads") or []
    if requested:
        cand = requested[-1].get("filepath") or requested[-1].get("_filename")
        if cand and os.path.exists(cand):
            return cand

    vid_id = info.get("id")
    if vid_id and os.path.isdir(DOWNLOAD_DIR):
        # Postprocessor renames the extension; search by id prefix.
        good_exts_video = (".mp4", ".mkv", ".webm", ".mov")
        good_exts_audio = (".mp3",)
        for fn in sorted(os.listdir(DOWNLOAD_DIR), key=len, reverse=True):
            if not fn.startswith(vid_id + "."):
                continue
            full = os.path.join(DOWNLOAD_DIR, fn)
            if video and fn.endswith(good_exts_video):
                return full
            if not video and fn.endswith(good_exts_audio):
                return full
    return None


def _try_download(url: str, *, video: bool, quality: str | None = None) -> tuple[str, dict]:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    last_exc: Exception | None = None
    for client in PLAYER_CLIENTS:
        try:
            with YoutubeDL(_opts(client, video=video, quality=quality)) as ydl:
                info = ydl.extract_info(url, download=True)
        except (ExtractorError, DownloadError) as exc:
            last_exc = exc
            if any(marker in str(exc).lower() for marker in _RETRY_MARKERS):
                continue
            raise
        except Exception as exc:
            last_exc = exc
            continue

        if not isinstance(info, dict):
            continue
        path = _final_path(info, video=video)
        if path:
            return path, info

    if last_exc:
        raise last_exc
    raise RuntimeError("yt-dlp returned no usable file")


def check_size_and_duration(info: dict) -> str | None:
    """Reject upfront based on probe metadata. Returns an error or None.

    Called with the lightweight info dict from `bot.utils.player._try_extract`
    (no download). Catches the obvious "this would never upload" cases
    before we burn bandwidth.
    """
    if not isinstance(info, dict):
        return None
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > MAX_DURATION_SECONDS:
        mins = int(duration // 60)
        return (
            f"That's {mins} min long — /song and /video are capped at "
            f"{MAX_DURATION_SECONDS // 60} minutes."
        )
    filesize = info.get("filesize") or info.get("filesize_approx")
    if isinstance(filesize, (int, float)) and filesize > MAX_FILE_BYTES:
        mb = int(filesize / 1_000_000)
        return f"That file is ~{mb} MB — over the 1500 MB upload cap."
    return None


def download_audio(url: str) -> tuple[str, dict]:
    return _try_download(url, video=False)


def download_video(url: str, quality: str | None = None) -> tuple[str, dict]:
    return _try_download(url, video=True, quality=quality)
