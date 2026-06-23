from pyrogram import Client
from bot.config import API_ID, API_HASH, BOT_TOKEN, STRING_SESSION

app = Client(
    "RaidenShogun",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

userbot = Client(
    "RaidenShogunAssistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION,
)
