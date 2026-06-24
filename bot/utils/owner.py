"""Identify the bot's owner.

Derived from the userbot session — whoever's STRING_SESSION runs the
assistant account IS the owner. They already have the keys to the bot;
no separate env var needed. Override with OWNER_ID env var if you want a
different account to hold the privileged commands.

Result is cached after first lookup so /broadcast doesn't hit get_me on
every invocation.
"""

import os
from typing import Optional

_cached: Optional[int] = None


def _env_owner() -> Optional[int]:
    raw = os.getenv("OWNER_ID", "").strip()
    return int(raw) if raw.isdigit() else None


async def get_owner_id() -> Optional[int]:
    global _cached
    if _cached is not None:
        return _cached
    env = _env_owner()
    if env is not None:
        _cached = env
        return env
    # Lazy import — bot.client constructs Pyrogram Client instances at
    # import time, and we don't want owner.py to drag that in unconditionally.
    from bot.client import userbot
    try:
        me = await userbot.get_me()
    except Exception:
        return None
    _cached = me.id
    return _cached


async def is_owner(user_id: int) -> bool:
    owner = await get_owner_id()
    return owner is not None and user_id == owner


async def is_sudo(user_id: int) -> bool:
    """True if the user is the owner OR an explicit sudoer.

    Use this for any command that should be delegable (e.g. /broadcast).
    Reserve is_owner for actions that mutate the privileged user list
    itself (/addsudo, /delsudo).
    """
    if await is_owner(user_id):
        return True
    from bot.utils import sudo as sudo_store
    return sudo_store.is_sudoer(user_id)
