"""Savage farewells for the leave handler.

Each message contains `{name}` which gets replaced with the leaver's display
name (HTML mention, so it stays clickable). We keep a small per-chat ring buffer
of recently-used indices to avoid back-to-back repeats.
"""

import random
from collections import deque
from threading import Lock

MESSAGES = [
    "{name} has left. Finally, the liability is gone. 🗑️",
    "{name} left the chat. Group IQ just went up by 30 points. 📈",
    "{name} packed up and left. The group's collective trauma is now 12% lighter. 🫧",
    "{name} ragequit. Nobody's chasing. Don't come back. 🚪",
    "{name} left. The chat will recover within minutes. We were already pretending not to notice them. 👀",
    "{name} is gone. The vibe just got upgraded for free. ✨",
    "{name} left the group. We were saving the kick for later — they did us a favor. 🪑",
    "Lost: {name}. Reward: nothing. Description: won't be missed. 📜",
    "{name} exited. Performance reviews indicate this is an upgrade. 📋",
    "{name} ghosted the chat. Honestly the most useful thing they've done here. 👻",
    "Breaking: {name} has left. In other news, nobody cares. 📰",
    "{name} took the L and dipped. Take the hint and don't come back. ✋",
    "{name} left without saying goodbye. The audacity to think we wanted one. 💅",
    "{name} unsubscribed from the group. Wise move — we were about to charge rent. 💸",
    "{name} packed their dead weight and left. Lighter already. 🎈",
    "{name} left the chat. A net positive for the group's standardized testing scores. 🧠",
    "{name} ran for the exit so fast they left their dignity behind. We'll burn it. 🔥",
    "{name} has been removed by themselves. Best decision they've ever made. ✅",
    "{name} left. Don't take it personally — they were never personality anyway. 🤡",
    "{name} bounced. Group emotional damage reduced by 84%. 📉",
    "{name} exited stage left. Tragically without an encore. 🎭",
    "{name} clocked out permanently. Pension: declined. 🕔",
    "{name} disappeared. We had a poll going to see when. Three people guessed correctly. 🗳️",
    "{name} chose violence — against the door, on their way out. 🚪💨",
    "{name} left. The group chat just hit a personal record for collective relief. 🏆",
    "{name} pulled the plug on their group membership. Should've pulled it on the wifi instead. 🔌",
    "{name} left so dramatically Shakespeare would shed a tear. We won't. 🎭",
    "{name} is gone. Funeral arrangements: none. Attendance: none. Vibes: ascending. 🪦",
    "{name} took the express elevator out. Hope they read the maintenance notice. 🛗",
    "{name} left the chat. The remaining members got a 10% morale boost effective immediately. 📊",
    # ---- batch 2: even more savage ----
    "{name} left. Honestly we were one personality trait away from staging an intervention. 🛑",
    "{name} exited the group. Sources confirm even their reflection unfollowed them. 🪞",
    "{name} departed. Achievement unlocked: Self-Awareness (Bronze). 🏅",
    "{name} ghosted us. Their charisma did the same to them years ago. ✌️",
    "{name} left. The group hit fifteen seconds of silence before realizing it was finally peaceful. 🧘",
    "{name} packed their grievances and left. Sadly they forgot their personality on the way out. 🎒",
    "{name} bounced. Even the typing dots breathed a sigh of relief. ⌨️",
    "{name} has exited. Effective immediately, the chat's collective braincell is back in service. 🧠",
    "{name} left so hard the door bounced back twice. We added a brick to keep it shut. 🧱",
    "{name} is gone. We've already redistributed their seat to a houseplant. The plant contributes more. 🪴",
    "{name} unsubscribed. The algorithm learned a valuable lesson today. 🤖",
    "{name} left. The eulogy fit on a sticky note. We didn't write one. 🗒️",
    "{name} departed. Their group photo presence has been retroactively cropped out by popular demand. ✂️",
    "{name} chose to leave before we chose for them. Respect for the speed run. ⏱️",
    "{name} left. Honestly the only respectful thing they've ever done in here. 👏",
    "{name} disappeared. The void looked at us and said 'no thanks, you keep them — wait, you don't have to anymore. 🫥",
    "{name} left. Their last message will go unread, as a tradition we already started. 📩",
    "{name} packed up. The collective dignity of this chat just rose by triple digits. 📈",
    "{name} left the group. Even the captcha was relieved. 🤖",
    "{name} dipped. Their replies were already in airplane mode anyway. ✈️",
    "{name} exited. The group dynamic is now mathematically optimal. ➕",
    "{name} left and we're already pretending they never joined. The history books agree. 📚",
    "{name} bounced. They thought it was a flex. We're calling it a service. 💪",
    "{name} left. The wifi got 30% faster. Coincidence? Statistically, no. 📶",
    "{name} packed their issues and left. The luggage was overweight, the room is lighter. 🧳",
    "{name} took the elevator down. Pressed every floor on the way out. We don't care. We're free. 🆓",
    "{name} left. Their absence is the upgrade we waited months for. ⭐",
    "{name} is gone. The chat finally smells like clean air and possibility. 🌬️",
    "{name} left. Even autocorrect refused to fix their last message. It knew. ❌",
    "{name} departed. We tried to be sad. We failed. We will not be trying again. 🫡",
]

_HISTORY_SIZE = 12
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
