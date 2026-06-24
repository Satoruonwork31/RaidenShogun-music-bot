from dotenv import load_dotenv
import os
from urllib.parse import urlparse

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRING_SESSION = os.getenv("STRING_SESSION")

# Optional. Needed only for Spotify links. Get yours at
# https://developer.spotify.com/dashboard (free).
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")


def _parse_proxy_url(raw: str) -> dict | None:
    """Parse PROXY_URL into a pyrofork-compatible proxy config.

    Accepts: socks4://, socks5://, http:// URLs, optionally with
    user:pass auth. Returns None on missing/invalid input so callers
    can short-circuit cleanly.

    Example:
      socks5://user:pass@host:1080
      http://host:8080
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        u = urlparse(raw)
    except Exception:
        return None
    scheme = (u.scheme or "").lower()
    if scheme not in ("socks4", "socks5", "http"):
        return None
    if not u.hostname or not u.port:
        return None
    cfg = {"scheme": scheme, "hostname": u.hostname, "port": u.port}
    if u.username:
        cfg["username"] = u.username
    if u.password:
        cfg["password"] = u.password
    return cfg


# Single source of truth for an outbound proxy. Used by both pyrofork
# clients (bot + userbot) and as the default fallback for YT_DLP_PROXY.
# Leave empty for direct connection.
PROXY_URL = os.getenv("PROXY_URL", "").strip()
PROXY = _parse_proxy_url(PROXY_URL)
