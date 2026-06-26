import os

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ParseMode

from bot.utils.departure import is_enabled as departure_enabled
from bot.utils.greetings import is_enabled
from bot.utils.leave_messages import pick as pick_leave_message
from bot.utils.welcome_image import render_welcome_card

WELCOME_TEMPLATE = (
    # Pyrofork's HTML parser uses <emoji id="..."> not <tg-emoji emoji-id="...">.
    '<emoji id="5460858729962421671">👋</emoji> Welcome, {first_name}!\n\n'
    "━━━━━━━━━━━━━━━\n"
    '<emoji id="5249053508681883137">👤</emoji> Name - {full_name}\n'
    '<emoji id="5818885490065017876">🆔</emoji> User ID - <code>{user_id}</code>\n'
    '<emoji id="6032675574646836901">📛</emoji> Username - {username}\n'
    "━━━━━━━━━━━━━━━\n\n"
    '<emoji id="5969733271305588971">✨</emoji> Your arrival has been successfully registered.\n\n'
    '<emoji id="6269566961168944843">🌐</emoji> Explore, connect, and enjoy everything waiting for you.\n\n'
    '<emoji id="5970041332129863164">💫</emoji> We hope you have an amazing experience and a wonderful time ahead!'
)


def _format(user) -> str:
    first_name = user.first_name or "friend"
    last_name = user.last_name or ""
    full_name = (first_name + " " + last_name).strip() or "Unknown"
    mention = f'<a href="tg://user?id={user.id}">{full_name}</a>'
    username = f"@{user.username}" if user.username else "(no username)"
    return WELCOME_TEMPLATE.format(
        first_name=first_name,
        full_name=mention,
        user_id=user.id,
        username=username,
    )


async def _download_pfp(client, user_id: int) -> str | None:
    try:
        async for photo in client.get_chat_photos(user_id, limit=1):
            os.makedirs("/tmp/raiden_pfps", exist_ok=True)
            path = f"/tmp/raiden_pfps/{user_id}.jpg"
            await client.download_media(photo.file_id, file_name=path)
            return path
    except Exception:
        return None
    return None


async def _send_card(client, chat_id: int, user) -> None:
    first_name = user.first_name or "friend"
    last_name = user.last_name or ""
    display_name = (first_name + " " + last_name).strip() or "friend"
    avatar_path = await _download_pfp(client, user.id)
    bio = await render_welcome_card(display_name, user.id, avatar_path)
    await client.send_photo(
        chat_id=chat_id,
        photo=bio,
        caption=_format(user),
        parse_mode=ParseMode.HTML,
    )


async def _is_chat_owner_or_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


@Client.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(client, message):
    """Legacy path used by regular groups."""
    if not is_enabled(message.chat.id):
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        if await _is_chat_owner_or_admin(client, message.chat.id, user.id):
            continue
        await _send_card(client, message.chat.id, user)


_JOIN_FROM = (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
_JOIN_TO = (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED)
_LEAVE_FROM = (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED, ChatMemberStatus.ADMINISTRATOR)
_LEAVE_TO = (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)


def _mention(user) -> str:
    first_name = user.first_name or "Someone"
    last_name = user.last_name or ""
    full_name = (first_name + " " + last_name).strip() or "Someone"
    return f'<a href="tg://user?id={user.id}">{full_name}</a>'


async def _send_leave(client, chat_id: int, user) -> None:
    template = pick_leave_message(chat_id)
    text = template.format(name=_mention(user))
    await client.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.left_chat_member & filters.group)
async def leave_legacy(client, message):
    if not departure_enabled(message.chat.id):
        return
    user = message.left_chat_member
    if not user or user.is_bot:
        return
    if await _is_chat_owner_or_admin(client, message.chat.id, user.id):
        return
    await _send_leave(client, message.chat.id, user)


@Client.on_chat_member_updated()
async def welcome_via_chat_member(client, chat_member_updated):
    """Modern path used by supergroups — fires on member status changes."""
    import logging as _logging
    _log = _logging.getLogger("RaidenShogun.welcome")
    _log.info(
        "chat_member_updated chat=%s new_status=%s old_status=%s user=%s",
        chat_member_updated.chat.id if chat_member_updated.chat else None,
        chat_member_updated.new_chat_member.status if chat_member_updated.new_chat_member else None,
        chat_member_updated.old_chat_member.status if chat_member_updated.old_chat_member else None,
        chat_member_updated.new_chat_member.user.id if (chat_member_updated.new_chat_member and chat_member_updated.new_chat_member.user) else None,
    )
    if chat_member_updated.chat is None:
        return
    new_member = chat_member_updated.new_chat_member
    old_member = chat_member_updated.old_chat_member
    if not new_member or not new_member.user or new_member.user.is_bot:
        return
    chat_id = chat_member_updated.chat.id
    old_status = old_member.status if old_member else ChatMemberStatus.LEFT
    if old_status in _JOIN_FROM and new_member.status in _JOIN_TO:
        if not is_enabled(chat_id):
            return
        # Skip the welcome for owners / admins re-joining.
        if new_member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return
        await _send_card(client, chat_id, new_member.user)
        return
    if old_status in _LEAVE_FROM and new_member.status in _LEAVE_TO:
        if not departure_enabled(chat_id):
            return
        # No savage farewell for owners or admins — they get a pass.
        if old_status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return
        await _send_leave(client, chat_id, new_member.user)
