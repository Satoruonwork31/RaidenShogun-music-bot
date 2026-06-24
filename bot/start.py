import asyncio

from pyrogram import idle

from bot.client import app, userbot
from bot.core.loader import load_plugins
from bot.logger import logger
from bot.utils.music import music
# Importing playback registers the @music.on_update stream-end handler so
# the queue auto-advances. Must happen before music.start().
from bot.utils import playback  # noqa: F401


async def _run():
    load_plugins()
    logger.info("Starting RaidenShogun Music Bot")
    await userbot.start()
    await music.start()
    await app.start()
    me = await app.get_me()
    logger.info(f"Logged in as @{me.username} ({me.id})")
    await idle()
    await app.stop()
    await userbot.stop()


def start_bot():
    asyncio.run(_run())
