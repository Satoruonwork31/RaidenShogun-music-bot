"""Per-chat playback queue.

A single queue per chat for both audio and video tracks — there's only one
voice chat per group, so audio and video share one timeline. Each `Track`
carries enough info to (re)start it and to render `/queue`.

State lives in process memory. Restart wipes it. That matches the rest of
the bot — there's no DB layer.

Locking note: handlers run on the event loop, but `enqueue` / `pop_next`
are also called from the stream-end callback, which runs on a different
PyTgCalls task. Using a stdlib `Lock` keeps the data structure safe even
if a /skip lands at the same instant as a natural stream-end.
"""

import random
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Optional


@dataclass
class Track:
    stream_url: str
    title: str
    requested_by: str
    is_video: bool = False


_lock = Lock()
_current: dict[int, Track] = {}
_upcoming: dict[int, deque] = {}
_history: dict[int, deque] = {}
_repeat: dict[int, bool] = {}

# Cap per-chat history so a 24h binge doesn't pile up memory.
_HISTORY_MAX = 50


def now_playing(chat_id: int) -> Optional[Track]:
    with _lock:
        return _current.get(chat_id)


def upcoming(chat_id: int) -> list:
    with _lock:
        return list(_upcoming.get(chat_id, ()))


def is_active(chat_id: int) -> bool:
    """True iff there's a track currently set as playing for this chat."""
    with _lock:
        return chat_id in _current


def set_current(chat_id: int, track: Track) -> None:
    with _lock:
        _current[chat_id] = track


def enqueue(chat_id: int, track: Track) -> int:
    """Append to the upcoming queue. Returns 1-indexed queue position."""
    with _lock:
        if chat_id not in _upcoming:
            _upcoming[chat_id] = deque()
        _upcoming[chat_id].append(track)
        return len(_upcoming[chat_id])


def pop_next(chat_id: int) -> Optional[Track]:
    """Move the next upcoming track into `current` and return it.

    The displaced current track is pushed onto the history deque so the
    ⏮ control can step backwards. If there is nothing upcoming, clears
    `current` for this chat and returns None — callers should interpret
    that as "queue exhausted, leave the call."
    """
    with _lock:
        # Push the outgoing current to history before we overwrite it.
        prev = _current.get(chat_id)
        if prev is not None:
            hist = _history.setdefault(chat_id, deque(maxlen=_HISTORY_MAX))
            hist.append(prev)

        q = _upcoming.get(chat_id)
        if not q:
            _current.pop(chat_id, None)
            return None
        nxt = q.popleft()
        _current[chat_id] = nxt
        return nxt


def pop_history(chat_id: int) -> Optional[Track]:
    """Return the most recently played track and push the current one
    back to the front of the upcoming queue. Used by the ⏮ button.
    """
    with _lock:
        hist = _history.get(chat_id)
        if not hist:
            return None
        prev = hist.pop()
        # Re-queue the current track at the front, so when prev finishes
        # the natural advance brings us back to where we were.
        cur = _current.get(chat_id)
        if cur is not None:
            up = _upcoming.setdefault(chat_id, deque())
            up.appendleft(cur)
        _current[chat_id] = prev
        return prev


def shuffle_upcoming(chat_id: int) -> int:
    """Shuffle the upcoming queue in place. Returns its length."""
    with _lock:
        q = _upcoming.get(chat_id)
        if not q or len(q) < 2:
            return len(q) if q else 0
        items = list(q)
        random.shuffle(items)
        q.clear()
        q.extend(items)
        return len(q)


def get_repeat(chat_id: int) -> bool:
    with _lock:
        return _repeat.get(chat_id, False)


def set_repeat(chat_id: int, on: bool) -> None:
    with _lock:
        if on:
            _repeat[chat_id] = True
        else:
            _repeat.pop(chat_id, None)


def toggle_repeat(chat_id: int) -> bool:
    """Flip the per-chat repeat flag. Returns the new state."""
    with _lock:
        new = not _repeat.get(chat_id, False)
        if new:
            _repeat[chat_id] = True
        else:
            _repeat.pop(chat_id, None)
        return new


def clear(chat_id: int) -> None:
    """Forget all queue state for this chat — used by /stop."""
    with _lock:
        _current.pop(chat_id, None)
        _upcoming.pop(chat_id, None)
        _history.pop(chat_id, None)
        _repeat.pop(chat_id, None)
