from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Your start banner image
START_IMAGE = "https://i.ibb.co/YF6mgfVx/f1fa18a00964.jpg"


@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user
    mention = user.mention
    user_id = user.id

    caption = f"""
✦  𝑾𝑬𝑳𝑪𝑶𝑴𝑬 𝑻𝑶 𝑹𝑨𝑰𝑫𝑬𝑵 𝑺𝑯𝑶𝑮𝑼𝑵 <tg-emoji emoji-id="5994721794760642534">🎵</tg-emoji>

Hey {mention}!
I'm Raiden Shogun, your premium music companion for Telegram Voice Chats.

<tg-emoji emoji-id="6170427231802757303">⚡</tg-emoji> Fast • <tg-emoji emoji-id="5352865784508980799">🎶</tg-emoji> High Quality Audio
<tg-emoji emoji-id="5278628322769654561">🧠</tg-emoji> Smart Queue • <tg-emoji emoji-id="5346334981792734939">🔥</tg-emoji> Powerful Playback
<tg-emoji emoji-id="5861955787181525936">👥</tg-emoji> Group Friendly • <tg-emoji emoji-id="5886268068035827289">🎧</tg-emoji> 24/7 Music

━━━━━━━━━━━━━━

<tg-emoji emoji-id="5226810560250676186">👤</tg-emoji> Your Profile
<tg-emoji emoji-id="6044337806719849057">❤️‍🔥</tg-emoji> User: {mention}
<tg-emoji emoji-id="5994504293321805232">🩵</tg-emoji> ID: {user_id}

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
        parse_mode=ParseMode.HTML,
        reply_markup=buttons,
    )
