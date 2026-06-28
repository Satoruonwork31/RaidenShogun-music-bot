"""Client for the external media-downloader microservice.

The microservice is a separate FastAPI process (NOT part of this repo)
that the operator deploys independently. It accepts Instagram and
Pinterest URLs and returns the raw media bytes — keeping all the
cookie + proxy nonsense isolated from this bot.

This module exposes one async entry point — `fetch_via_api(url, dest_dir)`
— which returns a Path to a downloaded media file or None. None means
"disabled, unreachable, or the API said no" — the caller must fall
through to the existing in-process yt-dlp path on None.

Contract (from operator):
- POST {MEDIA_API_URL}/download
    body: {"url": <str>}, header: X-API-Key: <key>
    success (2xx): raw bytes; Content-Type application/octet-stream
        for a single file, application/zip for multi-file carousels.
    failure (non-2xx): JSON {"code": "...", ...}.
- GET  {MEDIA_API_URL}/health — no auth.

Design notes:
- Returns None on EVERY non-success path (disabled, network error,
  non-2xx, malformed body). Never raises. Caller wants a binary
  signal: "got file?" / "didn't, fall back to yt-dlp".
- The aiohttp dependency is already in requirements.txt for the
  cookie-clobber tempfile flow.
- The 90s timeout is wall-clock for the API call only; the API's own
  internal yt-dlp download time is inside that budget.
- Unzipping carousels: we save the .zip, extract into dest_dir, and
  return the first media file. Telegram doesn't reasonably consume a
  multi-file carousel as one message; the rest of the carousel is
  left in dest_dir for the caller to pick up if it wants.
"""

import json
import logging
import os
import re
import zipfile
from pathlib import Path

import aiohttp

from bot.config import MEDIA_API_KEY, MEDIA_API_URL

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


async def fetch_via_api(url: str, dest_dir: Path) -> list[Path]:
    """POST {url} to the media API and save the returned file(s) into
    dest_dir. Returns the saved paths on success, an empty list on every
    other outcome (disabled, network error, non-2xx, empty body).

    Single-file (application/octet-stream) responses come back as a
    one-item list. application/zip carousel responses are extracted
    and ALL extracted media files are returned, sorted by filename so
    carousel order is preserved.
    """
    if not is_enabled():
        return []

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
                if not (200 <= resp.status < 300):
                    err = await _read_error_body(resp)
                    logger.warning(
                        "media_api: %s for %s — code=%s detail=%s",
                        resp.status, url, err.get("code"), err.get("message") or err.get("detail"),
                    )
                    return []

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
                        return []
                    items = _all_media_in(extract_dir)
                    if not items:
                        logger.warning("media_api: zip had no media files for %s", url)
                        return []
                    return items

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
                    return []
                return [out]

    except aiohttp.ClientConnectorError as exc:
        logger.warning("media_api: connection failed for %s: %s", url, exc)
        return []
    except aiohttp.ServerTimeoutError:
        logger.warning("media_api: timed out for %s", url)
        return []
    except Exception as exc:
        logger.warning("media_api: unexpected %s for %s: %s", type(exc).__name__, url, exc)
        return []
