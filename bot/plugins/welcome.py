from pyrogram import Client, filters
from pyrogram.enums import ParseMode

WELCOME_TEMPLATE = (
    '<tg-emoji emoji-id="5460858729962421671">👋</tg-emoji> Welcome, {first_name}!\n\n'
    "━━━━━━━━━━━━━━━\n"
    '<tg-emoji emoji-id="5249053508681883137">👤</tg-emoji> Name - {full_name}\n'
    '<tg-emoji emoji-id="5818885490065017876">🆔</tg-emoji> User ID - <code>{user_id}</code>\n'
    '<tg-emoji emoji-id="6032675574646836901">📛</tg-emoji> Username - {username}\n'
    "━━━━━━━━━━━━━━━\n\n"
    '<tg-emoji emoji-id="5969733271305588971">✨</tg-emoji> Your arrival has been successfully registered.\n\n'
    '<tg-emoji emoji-id="6269566961168944843">🌐</tg-emoji> Explore, connect, and enjoy everything waiting for you.\n\n'
    '<tg-emoji emoji-id="5970041332129863164">💫</tg-emoji> We hope you have an amazing experience and a wonderful time ahead!'
)


@Client.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(client, message):
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        first_name = user.first_name or "friend"
        last_name = user.last_name or ""
        full_name = (first_name + " " + last_name).strip() or "Unknown"
        username = f"@{user.username}" if user.username else "(no username)"
        text = WELCOME_TEMPLATE.format(
            first_name=first_name,
            full_name=full_name,
            user_id=user.id,
            username=username,
        )
        await message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
