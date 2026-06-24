"""Registry of chats the bot has been used in.

Bots can't enumerate dialogs over MTProto — they only know a chat exists
when they receive a message from it. So we record every chat_id that
sends us a message and persist to disk. Used by /broadcast to know where
to fan out.

Persistence is a JSON list at $CHATS_FILE (default ./chats.json), written
atomically via temp + rename so a kill -9 mid-write doesn't truncate it.
"""

import json
import os
from threading import Lock

CHATS_FILE = os.getenv("CHATS_FILE", "chats.json")

_lock = Lock()
_loaded = False
_known: set[int] = set()


def _load() -> None:
    global _loaded
    if _loaded:
        return
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                _known.update(int(x) for x in data)
        except (OSError, ValueError, TypeError):
            pass
    _loaded = True


def _save() -> None:
    tmp = CHATS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(sorted(_known), f)
        os.replace(tmp, CHATS_FILE)
    except OSError:
        pass


def remember(chat_id: int) -> bool:
    """Record chat_id if new. Returns True iff it was added this call."""
    with _lock:
        _load()
        if chat_id in _known:
            return False
        _known.add(chat_id)
        _save()
        return True


def all_chats() -> list[int]:
    with _lock:
        _load()
        return sorted(_known)


def forget(chat_id: int) -> bool:
    """Drop a chat (bot kicked / user blocked / id invalid)."""
    with _lock:
        _load()
        if chat_id not in _known:
            return False
        _known.discard(chat_id)
        _save()
        return True


def count() -> int:
    with _lock:
        _load()
        return len(_known)
