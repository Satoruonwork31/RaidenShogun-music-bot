"""Savage farewells for the leave handler.

Each message contains `{name}` which gets replaced with the leaver's display
name (HTML mention, so it stays clickable). We keep a small per-chat ring buffer
of recently-used indices to avoid back-to-back repeats.
"""

import random
from collections import deque
from threading import Lock

MESSAGES = [
    "{name} left the chat. Good riddance, honestly. 🫡",
    "Oh no, {name} couldn't handle the heat and left. 🚪💨",
    "{name} just left. Anyone want their stuff?",
    "Plot twist: {name} ragequit the group. 🎬",
    "{name} has left the chat. We will not be holding a moment of silence.",
    "Another one bites the dust. Farewell {name}, you absolute legend (or maybe not). 💀",
    "{name} left the building. Elvis style. 🕴️",
    "{name} has officially logged off forever. Or until they get bored elsewhere. 📴",
    "And just like that, {name} ghosted us. 👻",
    "{name} pulled the plug. Brave move. 🔌",
    "Tap tap... is this thing on? {name} left and the silence is deafening. 🎤",
    "Hold F to pay respects to {name}'s departure. 🪦",
    "{name} couldn't keep up and bounced. Sad. 💁",
    "{name} chose violence and left. Not even a goodbye. 🥲",
    "{name} took the L and exited the chat. 🚶",
    "{name} unsubscribed from our chaos. Smart move tbh. ✋",
    "{name} has decided this chat is not the vibe. Their loss. ✨",
    "{name} left without saying bye. Rude. 😤",
    "{name} packed up and went home. The drama was too much. 🎭",
    "{name} hit the eject button. Mission abandoned. 🚀",
    "{name} dipped. Don't let the door hit ya. 🚪",
    "{name} took the side exit. Quietly. Like a ninja. 🥷",
    "{name} left to touch grass. We'll see them in 7 business days. 🌿",
    "{name} bounced. Now we're one heartbeat short. 💔",
    "{name} unmatched with the group. Tragic. ❌",
    "{name} took the high road. We took the screenshots. 📸",
    "{name} clocked out. Shift's over apparently. 🕔",
    "{name} left the chat. The group's average vibe just went up. 📈",
    "{name} ragequit faster than a noob in Dark Souls. 🎮",
    "{name} left so quietly we almost didn't notice. Almost. 👀",
]

_HISTORY_SIZE = 6
_lock = Lock()
_recent: dict[int, deque] = {}


def pick(chat_id: int) -> str:
    """Return a message with `{name}` placeholder, avoiding recent repeats."""
    with _lock:
        history = _recent.setdefault(chat_id, deque(maxlen=_HISTORY_SIZE))
        choices = [i for i in range(len(MESSAGES)) if i not in history]
        if not choices:
            choices = list(range(len(MESSAGES)))
            history.clear()
        idx = random.choice(choices)
        history.append(idx)
        return MESSAGES[idx]
