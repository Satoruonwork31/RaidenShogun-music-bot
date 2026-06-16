from pyrogram import Client, filters

HELP_IMAGE = "https://i.ibb.co/0yjy0Cj0/0ad5a76f9731.jpg"

@Client.on_message(filters.command("help"))
async def help_command(client, message):
    caption = """
📚 RaidenShogun Music Bot Commands

🎵 Music
• /play - Play a song
• /pause - Pause playback
• /resume - Resume playback
• /skip - Skip the current track
• /stop - Stop playback
• /queue - Show the music queue

⚙️ General
• /start - Show the welcome message
• /help - Show this help menu
• /ping - Check if the bot is online
"""

    await message.reply_photo(
        photo=HELP_IMAGE,
        caption=caption,
    )
