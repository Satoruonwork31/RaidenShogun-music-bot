"""Bot-side blacklist. Blacklisted users get all their messages dropped
before any handler runs — they aren't kicked from groups, they just
can't trigger any bot functionality (commands, link-sniffer, callbacks).

Persisted as a JSON object at $BLIST_FILE (default ./blist.json):
  {"123456789": {"reason": "spam", "by": 1459770505, "at": 1735000000}}
"""

import json
import os
import time
from threading import Lock
from typing import Optional

BLIST_FILE = os.getenv("BLIST_FILE", "blist.json")

_lock = Lock()
_loaded = False
_blocked: dict[int, dict] = {}


def _load() -> None:
    global _loaded
    if _loaded:
        return
    if os.path.exists(BLIST_FILE):
        try:
            with open(BLIST_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    try:
                        _blocked[int(k)] = v if isinstance(v, dict) else {}
                    except (TypeError, ValueError):
                        pass
        except (OSError, ValueError, TypeError):
            pass
    _loaded = True


def _save() -> None:
    tmp = BLIST_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump({str(k): v for k, v in _blocked.items()}, f)
        os.replace(tmp, BLIST_FILE)
    except OSError:
        pass


def add(user_id: int, reason: str = "", by_user: Optional[int] = None) -> bool:
    with _lock:
        _load()
        was_new = user_id not in _blocked
        _blocked[user_id] = {
            "reason": reason or "",
            "by": by_user,
            "at": int(time.time()),
        }
        _save()
        return was_new


def remove(user_id: int) -> bool:
    with _lock:
        _load()
        if user_id not in _blocked:
            return False
        _blocked.pop(user_id, None)
        _save()
        return True


def is_blacklisted(user_id: int) -> bool:
    with _lock:
        _load()
        return user_id in _blocked


def get(user_id: int) -> Optional[dict]:
    with _lock:
        _load()
        return _blocked.get(user_id)


def count() -> int:
    with _lock:
        _load()
        return len(_blocked)
