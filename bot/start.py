import asyncio

from pyrogram import idle

from bot.client import app, userbot
from bot.logger import logger
from bot.utils.music import music
# Importing playback registers the @music.on_update stream-end handler so
# the queue auto-advances. Must happen before music.start().
from bot.utils import playback  # noqa: F401


def _rebind_dispatcher_loops() -> None:
    """Repair pyrofork's import-time loop capture.

    Pyrofork's Dispatcher.__init__ calls asyncio.get_event_loop() at module
    import time. On Python 3.10+ that returns a separate loop from the one
    asyncio.run() creates at runtime — so handler-worker tasks get scheduled
    on a dead loop and never execute. The bot logs in, the socket receives
    UpdateNewMessage packets, the dispatcher queue fills up, and NO handler
    ever fires because the workers are on a different loop.

    Pointing dispatcher.loop at the current running loop before any
    `client.start()` call fixes this — Dispatcher.start uses self.loop to
    spawn workers, so they land on the right loop.
    """
    loop = asyncio.get_running_loop()
    for client in (app, userbot):
        client.dispatcher.loop = loop


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
