from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Your start banner image
START_IMAGE = "https://i.ibb.co/YF6mgfVx/f1fa18a00964.jpg"


@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user

    caption = f"""
✦  WELCOME TO RAIDEN SHOGUN <custom_emoji id="5994721794760642534"> 

Hey {mention}!
I'm Raiden Shogun, your premium music companion for Telegram Voice Chats.

<custom_emoji id="6170427231802757303"> Fast • <custom_emoji id="5352865784508980799"> High Quality Audio
<custom_emoji id="5278628322769654561"> Smart Queue • <custom_emoji id="5346334981792734939"> Powerful Playback
<custom_emoji id="5861955787181525936"> Group Friendly • <custom_emoji id="5886268068035827289"> 24/7 Music

━━━━━━━━━━━━━━

<custom_emoji id="5226810560250676186"> Your Profile
<custom_emoji id="6044337806719849057"> User: {mention}
<custom_emoji id="5994504293321805232"> ID: {user_id}

Use /help to view all available commands.
"""

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 Channels",
                    url="https://t.me/Warborns"
                ),
                InlineKeyboardButton(
                    "📢 Updates",
                    url="https://t.me/Warborns"
                ),
            ],
            [
                InlineKeyboardButton(
                    "👑 Owner",
                    url="https://t.me/SunlessSovereign"
                ),
                InlineKeyboardButton(
                    "💬 Support",
                    url="https://t.me/+Gob4wQW8V9diMTM1"
                ),
            ],
            [
                InlineKeyboardButton(
                    "➕ Add Me to Your Group",
                    url="https://t.me/Raiden_MusicPlayerBot?startgroup=true"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📚 Help & Commands",
                    callback_data="help"
                ),
            ],
        ]
    )

    await message.reply_photo(
        photo=START_IMAGE,
        caption=caption,
        reply_markup=buttons,
    )
