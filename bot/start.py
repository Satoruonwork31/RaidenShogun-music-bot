from bot.client import app
from bot.logger import logger

def start_bot():
    logger.info("Starting RaidenShogun Music Bot...")
    app.run()
