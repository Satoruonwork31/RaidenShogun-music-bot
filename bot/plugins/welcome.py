from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ParseMode

from bot.utils.greetings import is_enabled

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


def _format(user) -> str:
    first_name = user.first_name or "friend"
    last_name = user.last_name or ""
    full_name = (first_name + " " + last_name).strip() or "Unknown"
    # Clickable name that opens the user's profile.
    mention = f'<a href="tg://user?id={user.id}">{full_name}</a>'
    username = f"@{user.username}" if user.username else "(no username)"
    return WELCOME_TEMPLATE.format(
        first_name=first_name,
        full_name=mention,
        user_id=user.id,
        username=username,
    )


@Client.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(client, message):
    """Legacy path used by regular groups."""
    if not is_enabled(message.chat.id):
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        await client.send_message(
            chat_id=message.chat.id,
            text=_format(user),
            parse_mode=ParseMode.HTML,
        )


_JOIN_FROM = (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
_JOIN_TO = (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED)


@Client.on_chat_member_updated()
async def welcome_via_chat_member(client, chat_member_updated):
    """Modern path used by supergroups — fires on member status changes."""
    if chat_member_updated.chat is None:
        return
    if not is_enabled(chat_member_updated.chat.id):
        return
    new_member = chat_member_updated.new_chat_member
    old_member = chat_member_updated.old_chat_member
    if not new_member or not new_member.user or new_member.user.is_bot:
        return
    old_status = old_member.status if old_member else ChatMemberStatus.LEFT
    if old_status in _JOIN_FROM and new_member.status in _JOIN_TO:
        await client.send_message(
            chat_id=chat_member_updated.chat.id,
            text=_format(new_member.user),
            parse_mode=ParseMode.HTML,
        )
