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


class YouTubeAuthRequiredError(Exception):
    """All extraction paths failed with the YouTube bot-check / sign-in
    page AND no cookies file is configured. Callers catch this to
    render a friendly UX message instead of a raw yt-dlp traceback.
    """

    USER_MESSAGE = (
        "🍪 YouTube is blocking this request and asking for a sign-in.\n\n"
        "The bot owner needs to upload a `cookies.txt` exported from a "
        "logged-in YouTube browser session and set the `COOKIES_FILE` "
        "env var to its absolute path."
    )

# Outbound proxy for yt-dlp specifically. If unset, fall back to:
#   1) PROXY_URL (explicit single proxy)
#   2) the same picked-from-pool config that Telegram uses (so a single
#      pool file configures both).
def _yt_dlp_proxy() -> str:
    explicit = os.getenv("YT_DLP_PROXY", "").strip()
    if explicit:
        return explicit
    single = os.getenv("PROXY_URL", "").strip()
    if single:
        return single
    # Reuse the same config.PROXY pick — yt-dlp wants a URL string.
    try:
        from bot.config import PROXY
    except Exception:
        return ""
    if not PROXY:
        return ""
    auth = ""
    if PROXY.get("username"):
        auth = PROXY["username"]
        if PROXY.get("password"):
            auth += ":" + PROXY["password"]
        auth += "@"
    return f"{PROXY['scheme']}://{auth}{PROXY['hostname']}:{PROXY['port']}"


YT_DLP_PROXY = _yt_dlp_proxy()

# Order matters — fastest / most reliable first. As of yt-dlp 2026.x:
# - `web` is the only client that fully honours cookies AND can solve the
#   n-challenge (with deno + ejs:github components downloaded).
# - `mweb` is a lighter web variant, also cookie-aware.
# - `tv` is the new name for the old tv_embedded client.
# - `android` and `ios` are kept as bot-wall fallbacks but they silently
#   drop cookies, so they only work for videos not gated by the wall.
# Older client names (tv_embedded, mediaconnect_frontend) were removed
# and yt-dlp prints "Skipping unsupported client" for them.
PLAYER_CLIENTS = [
    "web",
    "mweb",
    "tv",
    "android",
    "ios",
]


def _opts_for(client: str, extra=None, *, video: bool = False, use_cookies: bool = True) -> dict:
    fmt = "best[height<=720]/best" if video else "bestaudio/best"
    opts = {
        "format": fmt,
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "remote_components": ["ejs:github"],
    }
    if client != "default":
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    if use_cookies and COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    if YT_DLP_PROXY:
        opts["proxy"] = YT_DLP_PROXY
    if extra:
        opts.update(extra)
    return opts


def _is_bot_check(text: str) -> bool:
    return any(m in text for m in ("sign in", "not a bot", "confirm you"))


def _has_real_media(info, *, video: bool) -> bool:
    """True if info contains at least one usable audio/video format.

    YouTube on AWS-IP cookied sessions sometimes returns only image
    storyboards (mhtml) — no error, just unusable info. Detect that
    explicitly so callers can retry through a different path.
    """
    if not isinstance(info, dict):
        return False
    if isinstance(info.get("url"), str) and info["url"].startswith("http"):
        return True
    for f in info.get("formats") or []:
        if not isinstance(f, dict):
            continue
        if f.get("protocol") == "mhtml" or f.get("ext") == "mhtml":
            continue
        if video:
            if f.get("vcodec") not in (None, "none"):
                return True
        else:
            if f.get("acodec") not in (None, "none"):
                return True
    return False


def _extract_pass(url_or_query, extra, *, video, use_cookies):
    """One iteration over PLAYER_CLIENTS with a fixed cookie policy.

    Returns (info_dict_or_None, last_exc, bot_check_count).
    """
    last_exc: Exception | None = None
    bot_check_count = 0
    for client in ("default", *PLAYER_CLIENTS):
        try:
            with YoutubeDL(_opts_for(client, extra, video=video, use_cookies=use_cookies)) as ydl:
                info = ydl.extract_info(url_or_query, download=False)
            if info and _has_real_media(info, video=video):
                return info, last_exc, bot_check_count
            # No-error but storyboard-only: treat as retryable.
            continue
        except (ExtractorError, DownloadError) as exc:
            text = str(exc).lower()
            last_exc = exc
            if _is_bot_check(text):
                bot_check_count += 1
                continue
            if any(
                m in text for m in
                ("format is not available", "no video formats", "no formats", "could not find")
            ):
                continue
            raise
        except Exception as exc:
            last_exc = exc
            continue
    return None, last_exc, bot_check_count


def _try_extract(url_or_query: str, extra: dict | None = None, *, video: bool = False) -> dict | None:
    # Pass 1: no cookies. YouTube serves richer format lists to anonymous
    # server-IP sessions than to cookied ones (cookies trigger PO-token-only
    # mode that collapses formats down to storyboards).
    info, last_exc, bot_no_cookies = _extract_pass(
        url_or_query, extra, video=video, use_cookies=False,
    )
    if info is not None:
        return info

    # Pass 2: with cookies, if available. Auth-gated / age-restricted
    # videos need this.
    bot_with_cookies = 0
    if COOKIES_FILE:
        info, last_exc2, bot_with_cookies = _extract_pass(
            url_or_query, extra, video=video, use_cookies=True,
        )
        if info is not None:
            return info
        if last_exc2:
            last_exc = last_exc2

    # All paths failed. If both passes hit the bot-check page (or pass 1
    # did and no cookies are configured), surface that distinctly.
    if (bot_no_cookies or bot_with_cookies) and (not COOKIES_FILE or bot_with_cookies):
        raise YouTubeAuthRequiredError(
            "Every player client hit the YouTube bot-check or returned no playable formats."
        ) from last_exc
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
