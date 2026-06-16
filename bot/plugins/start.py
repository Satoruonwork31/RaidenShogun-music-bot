from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Your start banner image
START_IMAGE = "https://i.ibb.co/YF6mgfVx/f1fa18a00964.jpg"


@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user

    caption = f"""
✦ 𝑾𝑬𝑳𝑪𝑶𝑴𝑬 𝑻𝑶 𝑹𝑨𝑰𝑫𝑬𝑵 𝑺𝑯𝑶𝑮𝑼𝑵 🎵

Hey {user.mention}!
I'm Raiden Shogun, your music companion for Telegram voice chats.

────────────────────────
⚡ Fast • 🎶 High Quality Audio
🧠 Smart Queue • 🔥 Powerful Playback
👥 Group Friendly • 🎧 24/7 Music
────────────────────────

👤 Your Profile
❤️‍🔥 User: {user.mention}
🩵 ID: {user.id}

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
