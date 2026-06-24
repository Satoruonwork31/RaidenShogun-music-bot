from pyrogram import Client, filters

HELP_IMAGE = "https://i.ibb.co/0yjy0Cj0/0ad5a76f9731.jpg"

@Client.on_message(filters.command("help"))
async def help_command(client, message):
    caption = """
<custom_emoji id="5033104253846029290"> RaidenShogun Music Bot Commands

<custom_emoji id="5334653529741076580"> Music
• /play - Play a song
• /vplay - Play a video in voice chat
• /song - Search and download a song
• /video - Search and download a video
• /pause - Pause playback
• /resume - Resume playback
• /skip - Skip the current track
• /vskip - Skip the current video
• /stop - Stop playback
• /queue - Show the music queue

<custom_emoji id="4958900559139570572"> Moderation
• /ban - Ban a user
• /unban - Unban a user

<custom_emoji id="5816875690183631180"> Welcome & Greetings
• /welcome - Configure welcome settings
• /greetings - Show greeting options

<custom_emoji id="5972061723400605896"> Fun
• /toss - Toss a coin

<custom_emoji id="5350427505805238170"> Information
• /id - Get user, group, or chat ID

<custom_emoji id="5341715473882955310"> General
• /start - Show the welcome message
• /help - Show this help menu
• /ping - Check if the bot is online
"""

    await message.reply_photo(
        photo=HELP_IMAGE,
        caption=caption,
    )
