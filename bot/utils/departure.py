"""Per-chat on/off flag for the leave/farewell handler.

This is split from greetings.py so the user can independently enable
"savage farewell on leave" without also enabling welcome cards on join.

Default for any new chat is ON — the bot ships departure messages
turned on, and admins use `/departure off` to opt out. Storage is a
JSON list of chat ids in DEPARTURE_OFF_FILE — chats in the file are
the ones where departures are OFF.

The default-on store differs from greetings.py (which is default-off and
stores chats that are ON) precisely because the typical group expects a
farewell to fire without ceremony.
"""

import json
import os
from threading import Lock

DEPARTURE_OFF_FILE = os.getenv("DEPARTURE_OFF_FILE", "departure_off.json")

_lock = Lock()
_loaded = False
_disabled: set[int] = set()


def _load() -> None:
    global _loaded
    if _loaded:
        return
    if os.path.exists(DEPARTURE_OFF_FILE):
        try:
            with open(DEPARTURE_OFF_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                _disabled.update(int(x) for x in data)
        except (OSError, ValueError, TypeError):
            pass
    _loaded = True


def _save() -> None:
    tmp = DEPARTURE_OFF_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(sorted(_disabled), f)
        os.replace(tmp, DEPARTURE_OFF_FILE)
    except OSError:
        pass


def is_enabled(chat_id: int) -> bool:
    """True (default) unless the chat has explicitly turned departures off."""
    with _lock:
        _load()
        return chat_id not in _disabled


def set_enabled(chat_id: int, on: bool) -> None:
    with _lock:
        _load()
        if on:
            _disabled.discard(chat_id)
        else:
            _disabled.add(chat_id)
        _save()
