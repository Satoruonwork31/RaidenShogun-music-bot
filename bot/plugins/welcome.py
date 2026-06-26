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
    except Exception as exc:
        # Log instead of silently swallowing — USER_NOT_PARTICIPANT here
        # (common for users who already left) means the "skip departing
        # admins" guard can never confirm admin status, so it returns
        # False and the farewell fires. That's the desired outcome for a
        # leaver, but we want it visible rather than assumed.
        import logging as _l
        _l.getLogger("RaidenShogun.welcome").info(
            "_is_chat_owner_or_admin(chat=%s user=%s) get_chat_member raised: %r",
            chat_id, user_id, exc,
        )
        return False
    return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


@Client.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(client, message):
    """Legacy path used by regular groups (plain join service message)."""
    import logging as _l
    _l.getLogger("RaidenShogun.welcome").info(
        "welcome_new_members (legacy new_chat_members) FIRED in chat=%s, members=%s",
        message.chat.id if message.chat else None,
        [u.id for u in (message.new_chat_members or [])],
    )
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


import logging as _logging

_chat_member_log = _logging.getLogger("RaidenShogun.welcome")


async def handle_chat_member_event(bot_client, chat_member_updated, source: str = "?"):
    """Core join/leave dispatcher.

    Called from two places:
      1. The @Client.on_chat_member_updated() decorator below — bot-side,
         fires for the subset of events Telegram delivers to the bot account.
      2. bot/start.py registers this against the userbot programmatically,
         catching events Telegram doesn't reliably push to bots even when
         the bot is admin (pyrofork 2.3.69 has had spotty
         UpdateChannelParticipant delivery to bot accounts).

    `bot_client` is always the BOT client — that's what actually posts the
    welcome card / farewell roast. Even when the event came in via the
    userbot, we send the visible message via the bot.
    """
    _chat_member_log.info(
        "chat_member_updated source=%s chat=%s new_status=%s old_status=%s user=%s",
        source,
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
        _chat_member_log.info("classification=JOIN chat=%s user=%s", chat_id, new_member.user.id)
        if not is_enabled(chat_id):
            _chat_member_log.info("JOIN skipped: greetings.is_enabled(%s)=False", chat_id)
            return
        if new_member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            _chat_member_log.info("JOIN skipped: new status is %s (owner/admin)", new_member.status)
            return
        _chat_member_log.info("JOIN sending welcome card to chat=%s for user=%s", chat_id, new_member.user.id)
        try:
            await _send_card(bot_client, chat_id, new_member.user)
            _chat_member_log.info("JOIN card sent ok")
        except Exception:
            _chat_member_log.exception("JOIN _send_card raised")
        return
    if old_status in _LEAVE_FROM and new_member.status in _LEAVE_TO:
        _chat_member_log.info("classification=LEAVE chat=%s user=%s", chat_id, new_member.user.id)
        if not departure_enabled(chat_id):
            _chat_member_log.info("LEAVE skipped: departure.is_enabled(%s)=False", chat_id)
            return
        if old_status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            _chat_member_log.info("LEAVE skipped: old status was %s (owner/admin)", old_status)
            return
        _chat_member_log.info("LEAVE sending farewell to chat=%s for user=%s", chat_id, new_member.user.id)
        try:
            await _send_leave(bot_client, chat_id, new_member.user)
            _chat_member_log.info("LEAVE farewell sent ok")
        except Exception:
            _chat_member_log.exception("LEAVE _send_leave raised")
        return
    _chat_member_log.info(
        "no classification: old=%s new=%s — not a join or leave transition we care about",
        old_status, new_member.status,
    )


@Client.on_chat_member_updated()
async def welcome_via_chat_member(client, chat_member_updated):
    """Bot-side subscription. May or may not fire reliably (see
    `handle_chat_member_event` docstring); the userbot-side
    subscription in bot/start.py is the always-on path.
    """
    # Entry log BEFORE dispatch, separate from handle_chat_member_event's
    # own logging, so we can confirm the BOT account is receiving
    # ChatMemberUpdated at all — independent of the userbot path.
    _chat_member_log.info(
        "welcome_via_chat_member (BOT-side ChatMemberUpdated) FIRED in chat=%s",
        chat_member_updated.chat.id if chat_member_updated.chat else None,
    )
    from bot.client import app
    await handle_chat_member_event(app, chat_member_updated, source="bot")
