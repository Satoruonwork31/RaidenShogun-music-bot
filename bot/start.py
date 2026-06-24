import asyncio

from pyrogram import idle

from bot.client import app, userbot
from bot.logger import logger
from bot.utils import music as music_mod
from bot.utils import playback as playback_mod


def _rebind_pyrofork_loops() -> None:
    """Repair pyrofork's import-time loop capture.

    Pyrofork's Dispatcher.__init__ calls asyncio.get_event_loop() at module
    import time. On Python 3.10+ that returns a separate loop from the one
    asyncio.run() creates at runtime — so handler-worker tasks get scheduled
    on a dead loop and never execute. Pointing dispatcher.loop at the
    current running loop before any client.start() call fixes this.
    """
    loop = asyncio.get_running_loop()
    for client in (app, userbot):
        client.dispatcher.loop = loop


async def _run():
    # Step 1 — fix pyrofork's loop capture so handlers fire.
    _rebind_pyrofork_loops()

    # Step 2 — construct PyTgCalls inside the running loop. This is the
    # equivalent rebind for py-tgcalls; instead of patching every internal
    # asyncio primitive (loop, ChatLock, Cache, NTgCalls callbacks) we just
    # build the instance after the loop exists. Then register the
    # stream-end auto-advance handler against it.
    music_mod.init(userbot)
    playback_mod.register_handlers()

    # Pyrofork loads bot/plugins/*.py automatically on app.start() because
    # bot/client.py passes plugins=dict(root="bot.plugins"). By the time
    # plugin imports happen, music_mod.music is populated — plugins that
    # do `from bot.utils.music import music` will name-bind the live
    # instance correctly.
    logger.info("Starting RaidenShogun Music Bot")
    await userbot.start()
    await music_mod.music.start()
    await app.start()

    # Backfill the /broadcast chat registry from the userbot's perspective.
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
