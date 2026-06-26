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

    # Subscribe the userbot to ChatMemberUpdated. This is the always-on
    # path for greetings + departures. Telegram's MTProto only delivers
    # UpdateChannelParticipant to bot accounts under specific scope
    # conditions, and pyrofork 2.3.69 has had inconsistent behaviour
    # there. The userbot is a regular user — it gets these unconditionally
    # for every chat it's in.
    from pyrogram.handlers import ChatMemberUpdatedHandler
    from bot.plugins.welcome import handle_chat_member_event

    async def _userbot_member_dispatch(_client, chat_member_updated):
        try:
            await handle_chat_member_event(app, chat_member_updated, source="userbot")
        except Exception:
            logger.exception("userbot chat_member_updated dispatch failed")

    userbot.add_handler(ChatMemberUpdatedHandler(_userbot_member_dispatch))
    logger.info("Registered userbot ChatMemberUpdated dispatch")

    # Cookie diagnostics — a typo'd COOKIES_FILE path silently behaves
    # the same as unset, so surface the real state at boot.
    import os as _os
    cookies_path = _os.getenv("COOKIES_FILE", "").strip()
    if not cookies_path:
        logger.warning(
            "COOKIES_FILE is unset — YouTube downloads will fail on the "
            "bot-check wall. Set COOKIES_FILE=/abs/path/cookies.txt in .env."
        )
    elif _os.path.exists(cookies_path):
        logger.info("COOKIES_FILE is set and exists: %s", cookies_path)
    else:
        logger.warning(
            "COOKIES_FILE is set to %r but that path does NOT exist on disk "
            "— treated the same as unset. Check for a typo.",
            cookies_path,
        )

    # Empirical membership snapshot — list every chat the userbot is
    # currently a member of. Greetings/departure delivery via the userbot
    # ChatMemberUpdated path depends on the userbot being in the chat at
    # the moment a join/leave happens; this shows what it can see at boot.
    try:
        dialog_chats = []
        async for dialog in userbot.get_dialogs():
            ch = dialog.chat
            if ch and ch.type and ch.type.value in ("group", "supergroup"):
                dialog_chats.append(f"{ch.id} ({ch.title})")
        logger.info(
            "userbot is a member of %d group(s)/supergroup(s): %s",
            len(dialog_chats),
            "; ".join(dialog_chats) if dialog_chats else "(none)",
        )
    except Exception:
        logger.exception("could not enumerate userbot dialogs at startup")

    me = await app.get_me()
    logger.info(f"Logged in as @{me.username} ({me.id})")
    await idle()
    await app.stop()
    await userbot.stop()


def start_bot():
    asyncio.run(_run())
