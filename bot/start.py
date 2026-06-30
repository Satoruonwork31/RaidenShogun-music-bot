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


async def _stage(name: str, coro):
    """Run a startup coroutine, log the stage that failed before re-raising.

    Bare tracebacks from a failed `userbot.start()` look identical to a
    failed `app.start()` in journalctl — both show a Telegram client
    error with no hint at which client. Wrapping each step in a named
    stage tag makes the failure point obvious without changing behaviour.
    """
    try:
        return await coro
    except Exception:
        logger.exception("Startup failed at stage: %s", name)
        raise


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
    await _stage("userbot.start", userbot.start())
    await _stage("music.start", music_mod.music.start())
    await _stage("app.start (bot + plugin load)", app.start())

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
    from pyrogram.handlers import ChatMemberUpdatedHandler, RawUpdateHandler
    from bot.plugins.welcome import (
        handle_chat_member_event,
        _raw_participant_bridge,
    )

    async def _userbot_member_dispatch(_client, chat_member_updated):
        try:
            await handle_chat_member_event(app, chat_member_updated, source="userbot")
        except Exception:
            logger.exception("userbot chat_member_updated dispatch failed")

    userbot.add_handler(ChatMemberUpdatedHandler(_userbot_member_dispatch))

    # Same raw participant bridge that's registered on the bot, attached
    # to the userbot too.
    async def _userbot_raw_bridge(_client, update, users, chats):
        try:
            await _raw_participant_bridge(app, update, users, chats)
        except Exception:
            logger.exception("userbot raw participant bridge failed")

    userbot.add_handler(RawUpdateHandler(_userbot_raw_bridge))

    # ALSO register the bridge on the BOT client programmatically.
    # pyrofork 2.2.21 plugin-scanner loads RawUpdateHandler decorators
    # ("[LOAD] RawUpdateHandler ... in group 0") but the Dispatcher does
    # not invoke them at runtime — verified empirically. Explicit
    # add_handler bypasses the broken plugin path.
    async def _app_raw_bridge(_client, update, users, chats):
        try:
            await _raw_participant_bridge(app, update, users, chats)
        except Exception:
            logger.exception("bot raw participant bridge failed")

    app.add_handler(RawUpdateHandler(_app_raw_bridge), group=-9999)
    logger.info("Registered userbot + bot ChatMemberUpdated dispatch + raw bridge (programmatic)")

    # Polling fallback. Telegram MTProto stops pushing
    # UpdateChannelParticipant to bot accounts in some scopes — verified
    # empirically: bot is admin everywhere with full rights yet zero
    # participant updates arrive even while message updates flow normally.
    # Periodically snapshot membership and fire join/leave for diffs so
    # greetings/departures work regardless of update delivery.
    from bot.plugins.welcome import poll_participants_forever
    asyncio.create_task(poll_participants_forever(app))
    logger.info("Started participant polling loop")

    # Diagnostic: dump the groups dict on both dispatchers so we can
    # confirm RawUpdateHandler is actually in the runtime handler list.
    for label, cli in (("bot", app), ("userbot", userbot)):
        try:
            groups = cli.dispatcher.groups
            summary = []
            for grp, hs in groups.items():
                summary.append(f"g{grp}=" + ",".join(type(h).__name__ for h in hs))
            logger.info("dispatcher[%s] handler groups: %s", label, " | ".join(summary)[:1200])
        except Exception:
            logger.exception("could not dump dispatcher groups for %s", label)

    # Cookie diagnostics — a typo'd COOKIES_FILE path silently behaves
    # the same as unset, so surface the real state at boot.
    import os as _os
    for env_name, host_label in (
        ("COOKIES_FILE", "YouTube"),
        ("INSTAGRAM_COOKIES_FILE", "Instagram"),
    ):
        path = _os.getenv(env_name, "").strip()
        if not path:
            logger.warning(
                "%s is unset — %s downloads will fail on the "
                "bot-check / login wall. Set %s=/abs/path/cookies.txt in .env.",
                env_name, host_label, env_name,
            )
        elif _os.path.exists(path):
            logger.info("%s is set and exists: %s", env_name, path)
        else:
            logger.warning(
                "%s is set to %r but that path does NOT exist on disk "
                "— treated the same as unset. Check for a typo.",
                env_name, path,
            )

    # Media API diagnostics — only ping if MEDIA_API_URL is set, so a bot
    # without the external service runs unchanged. A misconfigured URL or
    # a down service is visible in the log immediately instead of being
    # discovered on the first real IG/Pinterest paste.
    from bot.config import MEDIA_API_URL
    if MEDIA_API_URL:
        from bot.utils.media_api_client import health_check
        try:
            ok, detail = await health_check()
            if ok:
                logger.info("MEDIA_API reachable at %s — %s", MEDIA_API_URL, detail)
            else:
                logger.warning(
                    "MEDIA_API at %s is NOT reachable: %s — IG/Pinterest will "
                    "fall through to in-process yt-dlp.",
                    MEDIA_API_URL, detail,
                )
        except Exception as exc:
            logger.warning(
                "MEDIA_API health check raised %s: %s — IG/Pinterest will "
                "fall through to in-process yt-dlp.",
                type(exc).__name__, exc,
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
