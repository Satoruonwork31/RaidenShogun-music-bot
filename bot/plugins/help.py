from pyrogram import Client, filters
from pyrogram.enums import ParseMode

HELP_IMAGE = "https://i.ibb.co/0yjy0Cj0/0ad5a76f9731.jpg"

# Each <tg-emoji emoji-id="..."> needs a fallback emoji INSIDE and a closing
# tag — Telegram renders the premium glyph for premium users and the fallback
# for everyone else. The bare `<custom_emoji id="...">` syntax used previously
# isn't a real Telegram tag and just gets stripped.
HELP_CAPTION = (
    '<tg-emoji emoji-id="5033104253846029290">🎵</tg-emoji> <b>RaidenShogun Music Bot Commands</b>\n\n'
    '<tg-emoji emoji-id="5334653529741076580">🎶</tg-emoji> <b>Music</b>\n'
    "• /play - Play a song\n"
    "• /vplay - Play a video in voice chat\n"
    "• /song - Search and download a song\n"
    "• /video - Search and download a video\n"
    "• /pause - Pause playback\n"
    "• /resume - Resume playback\n"
    "• /skip - Skip the current track\n"
    "• /vskip - Skip the current video\n"
    "• /stop - Stop playback\n"
    "• /queue - Show the music queue\n\n"
    '<tg-emoji emoji-id="4958900559139570572">🛡</tg-emoji> <b>Moderation</b>\n'
    "• /ban - Ban a user\n"
    "• /unban - Unban a user\n\n"
    '<tg-emoji emoji-id="5816875690183631180">👋</tg-emoji> <b>Welcome &amp; Greetings</b>\n'
    "• /greetings on|off - Toggle welcome &amp; farewell messages\n\n"
    '<tg-emoji emoji-id="5972061723400605896">🎲</tg-emoji> <b>Fun</b>\n'
    "• /toss - Toss a coin\n\n"
    '<tg-emoji emoji-id="5350427505805238170">🆔</tg-emoji> <b>Information</b>\n'
    "• /id - Get user, group, or chat ID\n\n"
    '<tg-emoji emoji-id="5341715473882955310">⚙️</tg-emoji> <b>General</b>\n'
    "• /start - Show the welcome message\n"
    "• /help - Show this help menu\n"
    "• /ping - Check if the bot is online\n"
    "• /broadcast - (owner only) push a message to every chat"
)


@Client.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply_photo(
        photo=HELP_IMAGE,
        caption=HELP_CAPTION,
        parse_mode=ParseMode.HTML,
    )
