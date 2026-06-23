from bot.client import app, userbot
from bot.logger import logger
from bot.core.loader import load_plugins
from bot.utils.music import music

def start_bot():
    load_plugins()

    logger.info("Starting RaidenShogun Music Bot")

    userbot.start()
    music.start()

    app.run()
