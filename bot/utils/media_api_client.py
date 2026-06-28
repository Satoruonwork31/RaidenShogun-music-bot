"""Client for the external media-downloader microservice.

The microservice is a separate FastAPI process (NOT part of this repo)
that the operator deploys independently. It accepts Instagram and
Pinterest URLs and returns the raw media bytes — keeping all the
cookie + proxy nonsense isolated from this bot.

This module exposes one async entry point — `fetch_via_api(url, dest_dir)`
— which returns a list of Paths to downloaded media files. An empty list
means "disabled, unreachable, or the API said no" — the caller must fall
through to the existing in-process yt-dlp path on an empty list. The list
has length 1 for single-file responses and length N for zip carousels.

Contract (from operator):
- POST {MEDIA_API_URL}/download
    body: {"url": <str>}, header: X-API-Key: <key>
    success (2xx): raw bytes; Content-Type application/octet-stream
        for a single file, application/zip for multi-file carousels.
    failure (non-2xx): JSON {"code": "...", ...}.
- GET  {MEDIA_API_URL}/health — no auth.

Design notes:
- Returns [] on EVERY non-success path (disabled, network error,
  non-2xx, malformed body). Never raises. Caller wants a binary
  signal: "got files?" / "didn't, fall back to yt-dlp".
- The aiohttp dependency is already in requirements.txt for the
  cookie-clobber tempfile flow.
- The 90s timeout is wall-clock for the API call only; the API's own
  internal yt-dlp download time is inside that budget.
- Unzipping carousels: we save the .zip, extract into dest_dir/_extracted,
  and return ALL extracted media files sorted by filename so carousel
  order is preserved. Callers that can only send a single file should
  take paths[0].
"""

import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from bot.config import MEDIA_API_KEY, MEDIA_API_URL


@dataclass
class ApiResult:
    """Rich outcome of a media-API request. Lets the caller decide
    whether to fall through to a local downloader (transient) or surface
    a terminal classification (login_required / private / unavailable).
    """
    paths: list[Path] = field(default_factory=list)
    ok: bool = False
    status: int | None = None          # HTTP status, None on connect failure
    code: str | None = None            # API's error.code (e.g. login_required)
    message: str | None = None         # short human message for logs/UX
    transient: bool = True             # True → local fallback is appropriate

    @property
    def has_files(self) -> bool:
        return bool(self.paths)


# Terminal API error codes: do NOT fall through to local yt-dlp because
# IG/Pinterest gave a definitive answer the local extractor will repeat.
_TERMINAL_CODES = {
    "login_required",
    "private",
    "unavailable",
    "not_found",
    "media_not_found",
    "geo_restricted",
    "removed",
    "deleted",
}

logger = logging.getLogger("RaidenShogun.media_api")

_TIMEOUT = aiohttp.ClientTimeout(total=90, connect=10)

# Best-effort safe filenames — strip path traversal and weird control chars,
# cap the length. We never trust the API to give us a sane filename.
_BAD_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def is_enabled() -> bool:
    """True iff MEDIA_API_URL is configured. MEDIA_API_KEY is
    technically optional (some operators run the service without
    auth); a missing key just sends no auth header.
    """
    return bool(MEDIA_API_URL)


def _sanitize_name(raw: str, default: str) -> str:
    base = os.path.basename(raw or "").strip()
    base = _BAD_NAME_CHARS.sub("_", base).strip("_")
    if not base or base in (".", ".."):
        return default
    return base[:120]


def _filename_from_disposition(header: str | None, default: str) -> str:
    """Pull filename from a Content-Disposition header. Handles both the
    plain `filename="..."` and RFC 5987 `filename*=UTF-8''...` forms.
    """
    if not header:
        return default
    # filename*=UTF-8''… takes precedence per RFC 5987.
    m = re.search(r"filename\*\s*=\s*[^']+''([^;]+)", header, re.IGNORECASE)
    if m:
        from urllib.parse import unquote
        return _sanitize_name(unquote(m.group(1)), default)
    m = re.search(r'filename\s*=\s*"([^"]+)"', header, re.IGNORECASE)
    if m:
        return _sanitize_name(m.group(1), default)
    m = re.search(r"filename\s*=\s*([^;]+)", header, re.IGNORECASE)
    if m:
        return _sanitize_name(m.group(1).strip(), default)
    return default


def _all_media_in(dir_path: Path) -> list[Path]:
    """All media files in dir_path, recursive, sorted by full path so
    carousel order is preserved (yt-dlp / the API name them 01_, 02_,
    ... so a plain sort puts them in upload order).
    """
    exts = (".mp4", ".mov", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".webp", ".gif")
    candidates: list[Path] = []
    for root, _dirs, files in os.walk(dir_path):
        for f in files:
            if f.lower().endswith(exts):
                candidates.append(Path(root) / f)
    candidates.sort()
    return candidates


async def _read_error_body(resp: aiohttp.ClientResponse) -> dict:
    try:
        body = await resp.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


async def health_check() -> tuple[bool, str]:
    """GET /health. Returns (ok, detail). Detail is a short string for
    logging. Not used inside the request path — only at boot.
    """
    if not is_enabled():
        return False, "disabled (MEDIA_API_URL not set)"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{MEDIA_API_URL}/health") as resp:
                if 200 <= resp.status < 300:
                    return True, f"{resp.status} {(await resp.text())[:120]}"
                return False, f"HTTP {resp.status}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _parse_error_body(body: dict) -> tuple[str | None, str | None]:
    """Extract (code, message) from the API's error envelope.

    The server's contract is:
        { "ok": false, "error": { "code": "...", "message": "...", "detail": "..." } }
    Older code-paths used a flat top-level {"code": "...", "message": "..."}.
    Handle both.
    """
    if not isinstance(body, dict):
        return None, None
    err = body.get("error") if isinstance(body.get("error"), dict) else None
    if err:
        code = err.get("code")
        message = err.get("message") or err.get("detail")
    else:
        code = body.get("code")
        message = body.get("message") or body.get("detail")
    if code is not None:
        code = str(code).lower().strip()
    return code, message


def _classify(status: int | None, code: str | None) -> bool:
    """Return transient=True (local fallback OK) / False (terminal)."""
    if status is None:
        return True            # connect failure / timeout
    if status == 401 or status == 403 and code != "login_required":
        return False           # auth issue / forbidden — surface, don't retry locally
    if status == 404:
        return False
    if 500 <= status < 600:
        return True
    if code and code in _TERMINAL_CODES:
        return False
    return True


async def fetch_via_api_detailed(url: str, dest_dir: Path) -> ApiResult:
    """POST {url} to the media API and save the returned file(s) into
    dest_dir. Returns a rich ApiResult so the caller can distinguish
    transient failures (network / 5xx → fall through) from terminal
    refusals (login_required / private → surface to the user).
    """
    if not is_enabled():
        return ApiResult(ok=False, transient=True, message="disabled (MEDIA_API_URL not set)")

    headers: dict[str, str] = {}
    if MEDIA_API_KEY:
        headers["X-API-Key"] = MEDIA_API_KEY

    payload = {"url": url}
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.post(
                f"{MEDIA_API_URL}/download",
                json=payload,
                headers=headers,
            ) as resp:
                status = resp.status
                if not (200 <= status < 300):
                    err = await _read_error_body(resp)
                    code, message = _parse_error_body(err)
                    transient = _classify(status, code)
                    logger.warning(
                        "media_api: %s for %s — code=%s message=%s transient=%s",
                        status, url, code, message, transient,
                    )
                    return ApiResult(
                        ok=False, status=status, code=code,
                        message=message, transient=transient,
                    )

                ctype = (resp.headers.get("Content-Type") or "").lower().split(";")[0].strip()
                disp = resp.headers.get("Content-Disposition")

                if ctype == "application/zip":
                    zip_path = dest_dir / "carousel.zip"
                    with open(zip_path, "wb") as fh:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            fh.write(chunk)
                    extract_dir = dest_dir / "_extracted"
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        with zipfile.ZipFile(zip_path) as zf:
                            # Defuse zip-slip: refuse entries with absolute
                            # paths or .. components. The API is ours but
                            # the file content isn't always.
                            safe_members = []
                            for m in zf.namelist():
                                if m.startswith("/") or ".." in Path(m).parts:
                                    logger.warning(
                                        "media_api: refusing zip member with traversal: %r", m,
                                    )
                                    continue
                                safe_members.append(m)
                            zf.extractall(extract_dir, members=safe_members)
                    except zipfile.BadZipFile:
                        logger.warning("media_api: returned zip is corrupt for %s", url)
                        return ApiResult(ok=False, status=status, transient=True,
                                         message="corrupt zip from API")
                    items = _all_media_in(extract_dir)
                    if not items:
                        logger.warning("media_api: zip had no media files for %s", url)
                        return ApiResult(ok=False, status=status, transient=True,
                                         message="empty zip from API")
                    return ApiResult(paths=items, ok=True, status=status)

                # Single-file path — stream to disk under a sanitized name.
                fallback_name = "media.mp4"
                if "image/" in ctype:
                    ext = ctype.split("/", 1)[1].split(";")[0].strip() or "jpg"
                    fallback_name = f"media.{ext}"
                fname = _filename_from_disposition(disp, fallback_name)
                # Ensure we have an extension so downstream callers don't
                # confuse the file with something else.
                if "." not in fname:
                    fname = f"{fname}.bin"
                out = dest_dir / fname
                with open(out, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        fh.write(chunk)
                if out.stat().st_size == 0:
                    logger.warning("media_api: returned empty body for %s", url)
                    out.unlink(missing_ok=True)
                    return ApiResult(ok=False, status=status, transient=True,
                                     message="empty body from API")
                return ApiResult(paths=[out], ok=True, status=status)

    except aiohttp.ClientConnectorError as exc:
        logger.warning("media_api: connection failed for %s: %s", url, exc)
        return ApiResult(ok=False, status=None, transient=True,
                         message=f"connection failed: {exc}")
    except aiohttp.ServerTimeoutError:
        logger.warning("media_api: timed out for %s", url)
        return ApiResult(ok=False, status=None, transient=True, message="timed out")
    except Exception as exc:
        logger.warning("media_api: unexpected %s for %s: %s", type(exc).__name__, url, exc)
        return ApiResult(ok=False, status=None, transient=True,
                         message=f"{type(exc).__name__}: {exc}")


async def fetch_via_api(url: str, dest_dir: Path) -> list[Path]:
    """Back-compat wrapper around `fetch_via_api_detailed`. Returns just
    the saved paths; callers needing failure classification (instagram.py)
    should call the detailed variant.
    """
    return (await fetch_via_api_detailed(url, dest_dir)).paths
