from pyrogram import Client, filters
from pyrogram.enums import ParseMode

HELP_IMAGE = "https://i.ibb.co/0yjy0Cj0/0ad5a76f9731.jpg"

# Pyrofork's HTML parser recognises ONLY <emoji id="..."> for custom emoji,
# not the <tg-emoji emoji-id="..."> tag accepted by Telegram's HTTP Bot API.
# Using the wrong tag silently strips the entity, leaving just the fallback.
# The format is: <emoji id="ID">FALLBACK_EMOJI</emoji>
HELP_CAPTION = (
    '<emoji id="5033104253846029290">🎵</emoji> <b>RaidenShogun Music Bot Commands</b>\n\n'
    '<emoji id="5334653529741076580">🎶</emoji> <b>Music</b>\n'
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
    '<emoji id="4958900559139570572">🛡</emoji> <b>Moderation</b>\n'
    "• /ban - Ban a user\n"
    "• /unban - Unban a user\n\n"
    '<emoji id="5816875690183631180">👋</emoji> <b>Welcome &amp; Greetings</b>\n'
    "• /greetings on|off - Toggle welcome &amp; farewell messages\n\n"
    '<emoji id="5972061723400605896">🎲</emoji> <b>Fun</b>\n'
    "• /toss - Toss a coin\n\n"
    '<emoji id="5350427505805238170">🆔</emoji> <b>Information</b>\n'
    "• /id - Get user, group, or chat ID\n\n"
    '<emoji id="5341715473882955310">⚙️</emoji> <b>General</b>\n'
    "• /start - Show the welcome message\n"
    "• /help - Show this help menu\n"
    "• /ping - Check if the bot is online\n\n"
    '<emoji id="5341715473882955310">👑</emoji> <b>Sudo</b>\n'
    "• /broadcast - (sudo) push a message to every chat\n"
    "• /seeddm - (sudo) seed user IDs into the broadcast registry\n"
    "• /addsudo - (owner) grant sudo to a user\n"
    "• /delsudo - (owner) revoke sudo from a user\n"
    "• /sudolist - (sudo) list current sudoers"
)


@Client.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply_photo(
        photo=HELP_IMAGE,
        caption=HELP_CAPTION,
        parse_mode=ParseMode.HTML,
    )
