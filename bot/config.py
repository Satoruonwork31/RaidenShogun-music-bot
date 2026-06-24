import logging
import os
import random
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

_log = logging.getLogger("RaidenShogun.config")

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


def _parse_shorthand(line: str) -> dict | None:
    """Parse the host:port:user:pass shorthand used by PureVPN-style proxy
    lists. Returns the same dict shape as `_parse_proxy_url`. Defaults
    scheme to http since that's what those providers ship.
    """
    parts = line.strip().split(":")
    if len(parts) < 2:
        return None
    host = parts[0].strip()
    try:
        port = int(parts[1].strip())
    except (ValueError, IndexError):
        return None
    if not host or not (0 < port < 65536):
        return None
    cfg = {"scheme": "http", "hostname": host, "port": port}
    if len(parts) >= 4:
        u, p = parts[2].strip(), parts[3].strip()
        if u:
            cfg["username"] = u
        if p:
            cfg["password"] = p
    return cfg


def _load_proxies_file(path: str) -> list[dict]:
    """Read a proxy pool file. One proxy per line. Lines may be:
    - a URL: socks5://user:pass@host:port
    - shorthand: host:port:user:pass

    Blank lines and lines starting with # are ignored.
    """
    out: list[dict] = []
    if not path or not os.path.exists(path):
        return out
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                cfg = _parse_proxy_url(line) or _parse_shorthand(line)
                if cfg is not None:
                    out.append(cfg)
    except OSError:
        pass
    return out


def _pick_proxy() -> dict | None:
    """Resolve a single proxy config to use for this process.

    Priority:
    1. PROXY_URL — explicit single proxy (URL form).
    2. PROXIES_FILE — pool file; pick a random one per process start so
       restarts spread load and a flaky proxy doesn't permanently break
       the bot.
    """
    single = os.getenv("PROXY_URL", "").strip()
    if single:
        return _parse_proxy_url(single)

    pool_path = os.getenv("PROXIES_FILE", "").strip()
    pool = _load_proxies_file(pool_path)
    if not pool:
        return None
    pick = random.choice(pool)
    _log.info(
        "config: picked proxy %s://%s:%s (pool size %d)",
        pick["scheme"], pick["hostname"], pick["port"], len(pool),
    )
    return pick


# Single source of truth for an outbound proxy. Used by both pyrofork
# clients (bot + userbot) and as the default fallback for YT_DLP_PROXY.
# Leave PROXY_URL/PROXIES_FILE empty for direct connection.
PROXY_URL = os.getenv("PROXY_URL", "").strip()
PROXY = _pick_proxy()
