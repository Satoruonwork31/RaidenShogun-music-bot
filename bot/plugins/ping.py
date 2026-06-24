import logging

from pyrogram import Client, filters

logger = logging.getLogger("RaidenShogun.ping")


@Client.on_message(filters.command("ping"))
async def ping_command(client, message):
    logger.info(
        "ping_command fired in chat=%s by user=%s",
        message.chat.id if message.chat else None,
        message.from_user.id if message.from_user else None,
    )
    await message.reply_text("🏓 Pong!")
