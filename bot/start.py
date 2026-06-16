from bot.client import app
from bot.logger import logger
from bot.core.loader import load_plugins

def start_bot():
    load_plugins()
    logger.info("Starting RaidenShogun Music Bot...")
    app.run()
