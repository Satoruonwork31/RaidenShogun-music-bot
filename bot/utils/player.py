"""yt-dlp wrapper that survives YouTube's anti-bot wall.

Strategy: instead of using a single YouTube `player_client`, try a chain of
clients in order. The newer/embed-style clients (`tv_embedded`,
`mediaconnect_frontend`) frequently slip past the "Sign in to confirm you're
not a bot" check that hits `android` and `web` from server IPs.

If COOKIES_FILE env var is set, cookies are passed in addition — which makes
every client more reliable.

Cookie-clobber defense: yt-dlp opens `cookiefile` read-write and saves
the post-request cookie jar back to disk. When Instagram soft-bans the
session, its response wipes the `sessionid` cookie, and yt-dlp persists
that empty state — so the master `instagram_cookies.txt` degrades from a
valid auth jar to junk after a single bad response. To avoid that we
hand yt-dlp a per-request *tempfile copy* of the master jar and never
let it touch the master. The tempfiles are cleaned up at process exit.
"""

import atexit
import logging
import os
import shutil
import tempfile

from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError, DownloadError

logger = logging.getLogger("RaidenShogun.player")

COOKIES_FILE = os.getenv("COOKIES_FILE", "")
INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "")

_COOKIE_TEMPFILES: list[str] = []


def _cleanup_cookie_tempfiles():
    for p in _COOKIE_TEMPFILES:
        try:
            os.remove(p)
        except OSError:
            pass


atexit.register(_cleanup_cookie_tempfiles)


def _master_cookies_for_url(url) -> str:
    if not isinstance(url, str):
        return COOKIES_FILE
    u = url.lower()
    if ("instagram.com" in u or "instagr.am" in u) and INSTAGRAM_COOKIES_FILE:
        return INSTAGRAM_COOKIES_FILE
    return COOKIES_FILE


def cookies_for_url(url) -> str:
    """Pick the right cookies file for a URL and return a tempfile copy
    so yt-dlp's cookie writeback can't degrade the master jar. Returns
    "" if no master is configured for this URL's host.

    Instagram and YouTube each block datacenter IPs unless requests come
    from a logged-in browser session, but they use entirely separate
    cookie jars — feeding YT cookies into IG (or vice versa) does
    nothing and risks confusing yt-dlp's extractor. Dispatch by host.
    """
    master = _master_cookies_for_url(url)
    if not master or not os.path.exists(master):
        return ""
    try:
        fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="cookies_")
        os.close(fd)
        shutil.copy2(master, tmp)
        _COOKIE_TEMPFILES.append(tmp)
        return tmp
    except OSError as exc:
        logger.warning("cookies_for_url: tempfile copy of %s failed: %s — falling back to master", master, exc)
        return master


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


def _load_proxy_pool() -> list[str]:
    """Build the proxy fallback pool.

    Sources, in order:
      1. YT_DLP_PROXY_LIST env var pointing at a file (one proxy URL per
         non-blank, non-`#` line). Lets the operator hot-swap the pool
         without restarting.
      2. YT_DLP_PROXIES env var as comma- or newline-separated URLs.
      3. The single-proxy fallbacks from _yt_dlp_proxy() (already covers
         YT_DLP_PROXY / PROXY_URL / bot.config.PROXY).

    Always returns at least one entry: "" means "direct, no proxy". The
    rotation loop in _try_extract iterates through the pool, so an empty
    pool means a single direct attempt.
    """
    pool: list[str] = []

    list_path = os.getenv("YT_DLP_PROXY_LIST", "").strip()
    if list_path and os.path.exists(list_path):
        try:
            with open(list_path) as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        pool.append(s)
        except OSError:
            pass

    raw = os.getenv("YT_DLP_PROXIES", "")
    if raw:
        for part in raw.replace("\n", ",").split(","):
            s = part.strip()
            if s and s not in pool:
                pool.append(s)

    if YT_DLP_PROXY and YT_DLP_PROXY not in pool:
        pool.append(YT_DLP_PROXY)

    return pool or [""]


_PROXY_POOL: list[str] = _load_proxy_pool()
_active_proxy_idx: int = 0

# Per-proxy consecutive-fail counter. When a proxy hits the threshold,
# it's evicted from the pool and won't be retried until process restart.
# Direct ("") is never evicted — it's the fallback floor.
_PROXY_FAIL_COUNT: dict[str, int] = {}
_PROXY_FAIL_THRESHOLD = 3


def current_proxy() -> str:
    return _PROXY_POOL[_active_proxy_idx % len(_PROXY_POOL)]


def rotate_proxy() -> str:
    """Advance the active proxy to the next slot. Returns the new active."""
    global _active_proxy_idx
    _active_proxy_idx = (_active_proxy_idx + 1) % len(_PROXY_POOL)
    return current_proxy()


def proxy_pool_size() -> int:
    return len(_PROXY_POOL)


def mark_proxy_ok(proxy: str) -> None:
    """Reset the fail counter for `proxy` on a successful attempt."""
    _PROXY_FAIL_COUNT.pop(proxy, None)


def mark_proxy_failed(proxy: str) -> None:
    """Increment the proxy's fail counter. Evict from the pool when the
    counter reaches `_PROXY_FAIL_THRESHOLD`. Direct connection ("") is
    never evicted. Logs the eviction so the operator can see why the
    pool is shrinking.
    """
    global _active_proxy_idx
    if not proxy:
        return
    _PROXY_FAIL_COUNT[proxy] = _PROXY_FAIL_COUNT.get(proxy, 0) + 1
    if _PROXY_FAIL_COUNT[proxy] < _PROXY_FAIL_THRESHOLD:
        return
    if proxy not in _PROXY_POOL:
        return
    # Keep at least one entry; if this is the last live proxy, replace
    # the pool with [""] so the bot falls back to direct.
    if len(_PROXY_POOL) <= 1:
        logger.warning(
            "proxy pool exhausted: last proxy %s evicted, falling back to direct",
            proxy,
        )
        _PROXY_POOL.clear()
        _PROXY_POOL.append("")
        _active_proxy_idx = 0
        _PROXY_FAIL_COUNT.pop(proxy, None)
        return
    idx = _PROXY_POOL.index(proxy)
    _PROXY_POOL.pop(idx)
    _PROXY_FAIL_COUNT.pop(proxy, None)
    if _active_proxy_idx >= len(_PROXY_POOL):
        _active_proxy_idx = 0
    logger.warning(
        "evicted dead proxy %s after %d consecutive failures; pool size now %d",
        proxy, _PROXY_FAIL_THRESHOLD, len(_PROXY_POOL),
    )

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


def _is_youtube_url(url: str) -> bool:
    """The SOCKS5 proxy pool is YouTube-only.

    Instagram / Pinterest / etc. work fine from the bot's direct IP but
    get rate-limited or blocked when routed through a shared free
    proxy whose IP other scrapers have already burned. So apply the
    proxy and the YT-specific multi-pass logic only to YouTube URLs.
    """
    if not isinstance(url, str):
        return False
    u = url.lower()
    return "youtube.com" in u or "youtu.be" in u


def _opts_for(client: str, extra=None, *, video: bool = False, use_cookies: bool = True, use_proxy: bool = True, cookies_path: str | None = None) -> dict:
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
    if use_cookies:
        ck = cookies_path if cookies_path is not None else COOKIES_FILE
        if ck:
            opts["cookiefile"] = ck
    if use_proxy:
        proxy = current_proxy()
        if proxy:
            opts["proxy"] = proxy
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


def _extract_pass(url_or_query, extra, *, video, use_cookies, use_proxy=True, cookies_path=None):
    """One iteration over PLAYER_CLIENTS with a fixed cookie policy.

    Returns (info_dict_or_None, last_exc, bot_check_count).
    """
    last_exc: Exception | None = None
    bot_check_count = 0
    for client in ("default", *PLAYER_CLIENTS):
        try:
            with YoutubeDL(_opts_for(client, extra, video=video, use_cookies=use_cookies, use_proxy=use_proxy, cookies_path=cookies_path)) as ydl:
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
    """Two-pass extract (anon → cookied) with proxy rotation for YouTube.

    Non-YouTube URLs (Instagram, Pinterest, SoundCloud, etc.) go direct
    — no proxy, no cookies, single pass. Free shared SOCKS5 IPs are
    rate-limited or blocklisted by those services, and the YT-specific
    fallbacks waste latency for no benefit.
    """
    is_yt = _is_youtube_url(url_or_query)

    if not is_yt:
        # Non-YouTube: direct, no proxy, no rotation, but per-host
        # cookies if configured (e.g. INSTAGRAM_COOKIES_FILE for IG).
        ig_cookies = cookies_for_url(url_or_query)
        info, last_exc, _ = _extract_pass(
            url_or_query, extra, video=video,
            use_cookies=bool(ig_cookies), use_proxy=False, cookies_path=ig_cookies or None,
        )
        if info is not None:
            return info
        if last_exc:
            raise last_exc
        return None

    last_exc: Exception | None = None
    bot_no_cookies = 0
    bot_with_cookies = 0
    pool_size = max(1, proxy_pool_size())

    for _ in range(pool_size):
        attempt_proxy = current_proxy()
        info, exc1, b1 = _extract_pass(
            url_or_query, extra, video=video, use_cookies=False, use_proxy=True,
        )
        if info is not None:
            mark_proxy_ok(attempt_proxy)
            return info
        if exc1:
            last_exc = exc1
        bot_no_cookies = max(bot_no_cookies, b1)

        if COOKIES_FILE:
            info, exc2, b2 = _extract_pass(
                url_or_query, extra, video=video, use_cookies=True, use_proxy=True,
            )
            if info is not None:
                mark_proxy_ok(attempt_proxy)
                return info
            if exc2:
                last_exc = exc2
            bot_with_cookies = max(bot_with_cookies, b2)

        # Both anon and cookied passes through this proxy returned nothing
        # usable — count it as a fail for eviction purposes.
        mark_proxy_failed(attempt_proxy)
        if proxy_pool_size() > 1:
            rotate_proxy()
        pool_size = max(1, proxy_pool_size())  # may have shrunk via eviction

    if (bot_no_cookies or bot_with_cookies) and (not COOKIES_FILE or bot_with_cookies):
        raise YouTubeAuthRequiredError(
            "Every proxy / player client hit the YouTube bot-check or returned no playable formats."
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
