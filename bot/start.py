import asyncio

from pyrogram import idle

from bot.client import app, userbot
from bot.logger import logger
from bot.utils.music import music
# Importing playback registers the @music.on_update stream-end handler so
# the queue auto-advances. Must happen before music.start().
from bot.utils import playback  # noqa: F401


def _rebind_dispatcher_loops() -> None:
    """Repair every import-time loop capture in the stack.

    Multiple libraries here call asyncio.get_event_loop() at module import
    time and cache the result on self.loop. On Python 3.10+ that returns
    a loop separate from the one asyncio.run() actually runs — so workers
    schedule onto a dead loop, futures attach to the wrong loop, the whole
    thing silently breaks. We re-point every captured reference at the
    current running loop before any .start() call.

    Affected:
    - pyrofork's `Dispatcher` on each Client (handler-worker scheduling,
      causes "command not responding").
    - py-tgcalls' `PyTgCalls` instance (causes "RuntimeError: Future
      attached to a different loop" the moment music.play tries to
      coordinate JoinGroupCall internally).
    """
    loop = asyncio.get_running_loop()
    for client in (app, userbot):
        client.dispatcher.loop = loop
    music.loop = loop


async def _run():
    # Pyrofork loads bot/plugins/*.py automatically on app.start() because
    # bot/client.py passes plugins=dict(root="bot.plugins"). The old manual
    # load_plugins() call did nothing useful — kept around in
    # bot/core/loader.py only for the PLUGINS list comment / reference.
    _rebind_dispatcher_loops()
    logger.info("Starting RaidenShogun Music Bot")
    await userbot.start()
    await music.start()
    await app.start()

    # Backfill the /broadcast chat registry from the userbot's perspective.
    # Bots can't enumerate their own dialogs, so on a fresh start the
    # registry would only know chats that have sent a message since boot.
    from bot.utils.discover import backfill_common_chats
    try:
        await backfill_common_chats()
    except Exception:
        logger.exception("backfill_common_chats failed (continuing)")
    me = await app.get_me()
    logger.info(f"Logged in as @{me.username} ({me.id})")
    await idle()
    await app.stop()
    await userbot.stop()


def start_bot():
    asyncio.run(_run())
