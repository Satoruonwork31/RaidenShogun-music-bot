import asyncio
import logging

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioQuality, MediaStream
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters as tg_filters,
)

from bot.config import API_HASH, API_ID, BOT_TOKEN, STRING_SESSION
from bot.utils.resolver import resolve

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("pytgcalls").setLevel(logging.DEBUG)
logging.getLogger("ntgcalls").setLevel(logging.DEBUG)
logger = logging.getLogger("RaidenShogun")

userbot = Client(
    "RaidenShogunAssistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION,
    in_memory=True,
)
music = PyTgCalls(userbot)

START_IMAGE = "https://i.ibb.co/YF6mgfVx/f1fa18a00964.jpg"
HELP_IMAGE = "https://i.ibb.co/0yjy0Cj0/0ad5a76f9731.jpg"

HELP_CAPTION = (
    "📚 RaidenShogun Music Bot Commands\n\n"
    "🎵 Music\n"
    "• /play - Play a song\n"
    "• /pause - Pause playback\n"
    "• /resume - Resume playback\n"
    "• /skip - Skip the current track\n"
    "• /stop - Stop playback\n"
    "• /queue - Show the music queue\n\n"
    "⚙️ General\n"
    "• /start - Show the welcome message\n"
    "• /help - Show this help menu\n"
    "• /ping - Check if the bot is online"
)


def _start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📢 Channels", url="https://t.me/Warborns"),
                InlineKeyboardButton("📢 Updates", url="https://t.me/Warborns"),
            ],
            [
                InlineKeyboardButton("👑 Owner", url="https://t.me/SunlessSovereign"),
                InlineKeyboardButton("💬 Support", url="https://t.me/+Gob4wQW8V9diMTM1"),
            ],
            [
                InlineKeyboardButton(
                    "➕ Add Me to Your Group",
                    url="https://t.me/Raiden_MusicPlayerBot?startgroup=true",
                ),
            ],
            [InlineKeyboardButton("📚 Help & Commands", callback_data="help")],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    mention = user.mention_html()
    user_id = user.id
    caption = (
        '✦  𝑾𝑬𝑳𝑪𝑶𝑴𝑬 𝑻𝑶 𝑹𝑨𝑰𝑫𝑬𝑵 𝑺𝑯𝑶𝑮𝑼𝑵 <tg-emoji emoji-id="5994721794760642534">🎵</tg-emoji>\n\n'
        f"Hey {mention}!\n"
        "I'm Raiden Shogun, your premium music companion for Telegram Voice Chats.\n\n"
        '<tg-emoji emoji-id="6170427231802757303">⚡</tg-emoji> Fast • '
        '<tg-emoji emoji-id="5352865784508980799">🎶</tg-emoji> High Quality Audio\n'
        '<tg-emoji emoji-id="5278628322769654561">🧠</tg-emoji> Smart Queue • '
        '<tg-emoji emoji-id="5346334981792734939">🔥</tg-emoji> Powerful Playback\n'
        '<tg-emoji emoji-id="5861955787181525936">👥</tg-emoji> Group Friendly • '
        '<tg-emoji emoji-id="5886268068035827289">🎧</tg-emoji> 24/7 Music\n\n'
        "━━━━━━━━━━━━━━\n\n"
        '<tg-emoji emoji-id="5226810560250676186">👤</tg-emoji> Your Profile\n'
        f'<tg-emoji emoji-id="6044337806719849057">❤️‍🔥</tg-emoji> User: {mention}\n'
        f'<tg-emoji emoji-id="5994504293321805232">🩵</tg-emoji> ID: {user_id}\n\n'
        "Use /help to view all available commands."
    )
    await update.message.reply_photo(
        photo=START_IMAGE,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=_start_buttons(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_photo(photo=HELP_IMAGE, caption=HELP_CAPTION)


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.reply_photo(photo=HELP_IMAGE, caption=HELP_CAPTION)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🏓 Pong!")


DOWNLOAD_DIR = "/tmp/raiden_downloads"


def _replied_media(msg):
    """Return (telegram media object, label) from a replied message, or (None, None)."""
    if not msg or not msg.reply_to_message:
        return None, None
    r = msg.reply_to_message
    for attr in ("audio", "voice", "video", "video_note"):
        media = getattr(r, attr, None)
        if media:
            label = getattr(media, "file_name", None) or getattr(media, "title", None) or attr
            return media, label
    if r.document and r.document.mime_type and (
        r.document.mime_type.startswith("audio/") or r.document.mime_type.startswith("video/")
    ):
        return r.document, r.document.file_name or "uploaded file"
    return None, None


async def _download_replied(media, context):
    import os
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    tg_file = await context.bot.get_file(media.file_id)
    suffix = ""
    fname = getattr(media, "file_name", None)
    if fname and "." in fname:
        suffix = "." + fname.rsplit(".", 1)[-1]
    elif tg_file.file_path and "." in tg_file.file_path:
        suffix = "." + tg_file.file_path.rsplit(".", 1)[-1]
    local_path = os.path.join(DOWNLOAD_DIR, f"{media.file_unique_id}{suffix}")
    await tg_file.download_to_drive(local_path)
    return local_path


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text(
            "👥 The /play command only works in groups with an active voice chat."
        )
        return

    replied_media, replied_label = _replied_media(update.message)

    if not context.args and not replied_media:
        await update.message.reply_text(
            "🎵 Please provide a song name or link, or reply to an audio/video message with /play.\n\n"
            "Supported sources:\n"
            "• YouTube (link or text search)\n"
            "• Spotify track link\n"
            "• Resso song link\n"
            "• SoundCloud track link\n"
            "• Uploaded audio/voice/video (reply with /play)\n\n"
            "Example:\n"
            "`/play Believer`\n"
            "`/play https://open.spotify.com/track/...`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if replied_media:
        status = await update.message.reply_text(f"⬇️ Downloading {replied_label}...")
    else:
        query = " ".join(context.args)
        status = await update.message.reply_text(f"🔍 Resolving: {query}")

    err = await _ensure_userbot_in_chat(update.effective_chat.id, context.bot)
    if err:
        await status.edit_text(f"❌ {err}")
        return

    if replied_media:
        try:
            stream_url = await _download_replied(replied_media, context)
            info = replied_label
        except Exception as exc:
            await status.edit_text(f"❌ Download failed: {exc}")
            return
    else:
        stream_url, info = await resolve(" ".join(context.args))
        if not stream_url:
            await status.edit_text(f"❌ {info}")
            return

    # Make sure the userbot's peer cache knows this chat before PyTgCalls tries to
    # invoke phone.JoinGroupCall — fresh joins via invite link can leave the cache
    # un-primed and the join then fails with an opaque TelegramServerError.
    try:
        await userbot.get_chat(update.effective_chat.id)
    except Exception as exc:
        logger.warning(f"userbot.get_chat({update.effective_chat.id}) failed: {exc}")

    try:
        await music.play(
            update.effective_chat.id,
            MediaStream(stream_url, audio_parameters=AudioQuality.HIGH),
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        logger.exception("music.play failed")
        await status.edit_text(f"❌ Playback failed: {detail}")
        return

    await status.edit_text(f"🎵 Now Playing: {info}")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await music.pause(update.effective_chat.id)
    except Exception as exc:
        await update.message.reply_text(f"❌ Pause failed: {exc}")
        return
    await update.message.reply_text("⏸️ Playback paused.\n\nUse /resume to continue.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await music.resume(update.effective_chat.id)
    except Exception as exc:
        await update.message.reply_text(f"❌ Resume failed: {exc}")
        return
    await update.message.reply_text("▶️ Playback resumed.")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await music.leave_call(update.effective_chat.id)
    except Exception as exc:
        await update.message.reply_text(f"❌ Stop failed: {exc}")
        return
    await update.message.reply_text("⏹️ Playback stopped and the queue has been cleared.")


async def queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📜 The queue is currently empty.\n\n🎵 Use /play <song name> to add music."
    )


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏭️ Skipped to the next track.")


async def song(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🎵 Song download system is under development.")


async def video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📹 Video download system is under development.")


async def vplay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🎬 Video playback system is under development.")


async def vskip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏭ Video skip system is under development.")


async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import secrets
    result = "Heads 🪙" if secrets.randbelow(2) == 0 else "Tails 🪙"
    await update.message.reply_text(f"🎲 {result}")


_ADMIN_STATUSES_PTB = {"creator", "administrator"}


async def _ptb_is_admin(context, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return getattr(member, "status", "") in _ADMIN_STATUSES_PTB


async def _ptb_resolve_target(update, context):
    """Return (user_id, user_mention_html, leftover_reason)."""
    msg = update.message
    text = msg.text or ""

    # Text-mention entities — these tag users who don't have a public @username.
    # The mention text is at text[offset:offset+length] and the user is on the entity.
    for ent in (msg.entities or []):
        if ent.type == "text_mention" and ent.user:
            mention_text = text[ent.offset:ent.offset + ent.length]
            after_cmd = text.split(maxsplit=1)
            after_cmd = after_cmd[1] if len(after_cmd) > 1 else ""
            reason = after_cmd.replace(mention_text, "", 1).strip()
            return ent.user.id, ent.user.mention_html(), reason

    reply = msg.reply_to_message
    if reply and reply.from_user:
        reason = " ".join(context.args).strip() if context.args else ""
        return reply.from_user.id, reply.from_user.mention_html(), reason

    if not context.args:
        return None, None, ""

    raw = context.args[0].lstrip("@")
    reason = " ".join(context.args[1:]).strip()

    if raw.isdigit():
        try:
            chat = await context.bot.get_chat(int(raw))
            mention = f'<a href="tg://user?id={chat.id}">{chat.first_name or raw}</a>'
            return chat.id, mention, reason
        except Exception:
            return int(raw), f'<a href="tg://user?id={raw}">user {raw}</a>', reason

    # The HTTP Bot API can't resolve a user by @username unless the bot has cached
    # them. The userbot (MTProto) can resolve any public username, so try it first.
    try:
        user = await userbot.get_users(raw)
        first = getattr(user, "first_name", None) or raw
        mention = f'<a href="tg://user?id={user.id}">{first}</a>'
        return user.id, mention, reason
    except Exception:
        pass

    try:
        chat = await context.bot.get_chat("@" + raw)
        mention = f'<a href="tg://user?id={chat.id}">{chat.first_name or raw}</a>'
        return chat.id, mention, reason
    except Exception:
        return None, None, reason


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("👥 /ban only works in groups.")
        return

    actor_id = update.effective_user.id
    if not await _ptb_is_admin(context, chat.id, actor_id):
        await update.message.reply_text("🔒 Only group admins can /ban.")
        return

    me = await context.bot.get_me()
    if not await _ptb_is_admin(context, chat.id, me.id):
        await update.message.reply_text(
            "⚠️ Make me an admin with Ban Users permission so I can do that."
        )
        return

    target_id, target_mention, reason = await _ptb_resolve_target(update, context)
    if target_id is None:
        await update.message.reply_text(
            "Usage:\n"
            "• Reply to a message with /ban [reason]\n"
            "• /ban <user_id> [reason]\n"
            "• /ban @username [reason]"
        )
        return

    if target_id == me.id:
        await update.message.reply_text("🙃 I'm not going to ban myself.")
        return
    if target_id == actor_id:
        await update.message.reply_text("🙃 You can't ban yourself.")
        return
    if await _ptb_is_admin(context, chat.id, target_id):
        await update.message.reply_text("🔒 I can't ban another admin.")
        return

    try:
        await context.bot.ban_chat_member(chat.id, target_id)
    except Exception as exc:
        await update.message.reply_text(f"❌ Ban failed: {exc}")
        return

    banner_mention = update.effective_user.mention_html()
    if reason:
        text = (
            f"🚫 {target_mention} got banned by admin = {banner_mention}\n"
            f"Reason: {reason}"
        )
    else:
        text = f"🚫 {target_mention} got banned by admin = {banner_mention}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("👥 /unban only works in groups.")
        return

    actor_id = update.effective_user.id
    if not await _ptb_is_admin(context, chat.id, actor_id):
        await update.message.reply_text("🔒 Only group admins can /unban.")
        return

    me = await context.bot.get_me()
    if not await _ptb_is_admin(context, chat.id, me.id):
        await update.message.reply_text(
            "⚠️ Make me an admin with Ban Users permission so I can do that."
        )
        return

    target_id, target_mention, reason = await _ptb_resolve_target(update, context)
    if target_id is None:
        await update.message.reply_text(
            "Usage:\n"
            "• Reply to a message with /unban [reason]\n"
            "• /unban <user_id> [reason]\n"
            "• /unban @username [reason]"
        )
        return

    try:
        await context.bot.unban_chat_member(chat.id, target_id, only_if_banned=True)
    except Exception as exc:
        await update.message.reply_text(f"❌ Unban failed: {exc}")
        return

    unbanner = update.effective_user.mention_html()
    if reason:
        text = (
            f"✅ {target_mention} got unbanned by admin = {unbanner}\n"
            f"Reason: {reason}"
        )
    else:
        text = f"✅ {target_mention} got unbanned by admin = {unbanner}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


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


def _format_welcome(user) -> str:
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


async def _download_user_pfp(context, user_id: int) -> str | None:
    """Download the user's largest profile photo, or None if they don't have one."""
    import os
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
    except Exception:
        return None
    if not photos or not photos.photos:
        return None
    largest = max(photos.photos[0], key=lambda p: p.width or 0)
    try:
        tg_file = await context.bot.get_file(largest.file_id)
    except Exception:
        return None
    os.makedirs("/tmp/raiden_pfps", exist_ok=True)
    path = f"/tmp/raiden_pfps/{user_id}.jpg"
    try:
        await tg_file.download_to_drive(path)
    except Exception:
        return None
    return path


async def _send_welcome(context, chat_id: int, user) -> None:
    from bot.utils.welcome_image import render_welcome_card
    first_name = user.first_name or "friend"
    last_name = user.last_name or ""
    display_name = (first_name + " " + last_name).strip() or "friend"
    avatar_path = await _download_user_pfp(context, user.id)
    bio = await render_welcome_card(display_name, user.id, avatar_path)
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=bio,
        caption=_format_welcome(user),
        parse_mode=ParseMode.HTML,
    )


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy path: message with new_chat_members service entries."""
    msg = update.message
    if not msg or not msg.new_chat_members:
        return
    from bot.utils.greetings import is_enabled
    if not is_enabled(update.effective_chat.id):
        return
    for user in msg.new_chat_members:
        if user.is_bot:
            continue
        await _send_welcome(context, update.effective_chat.id, user)


def _mention_html(user) -> str:
    first_name = user.first_name or "Someone"
    last_name = user.last_name or ""
    full_name = (first_name + " " + last_name).strip() or "Someone"
    return f'<a href="tg://user?id={user.id}">{full_name}</a>'


async def _send_leave_message(context, chat_id: int, user) -> None:
    from bot.utils.leave_messages import pick as pick_leave_message
    template = pick_leave_message(chat_id)
    text = template.format(name=_mention_html(user))
    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode=ParseMode.HTML
    )


async def leave_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy path: someone left via service message left_chat_member."""
    msg = update.message
    if not msg or not msg.left_chat_member:
        return
    from bot.utils.greetings import is_enabled
    if not is_enabled(update.effective_chat.id):
        return
    user = msg.left_chat_member
    if user.is_bot:
        return
    await _send_leave_message(context, update.effective_chat.id, user)


async def welcome_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Modern path: supergroups deliver joins AND leaves via chat_member updates."""
    cm = update.chat_member
    if cm is None or cm.new_chat_member is None or cm.new_chat_member.user is None:
        return
    user = cm.new_chat_member.user
    if user.is_bot:
        return
    old_status = cm.old_chat_member.status if cm.old_chat_member else "left"
    new_status = cm.new_chat_member.status

    from bot.utils.greetings import is_enabled

    if old_status in ("left", "kicked") and new_status in ("member", "restricted"):
        if not is_enabled(update.effective_chat.id):
            return
        await _send_welcome(context, update.effective_chat.id, user)
        return

    if old_status in ("member", "restricted", "administrator") and new_status in ("left", "kicked"):
        if not is_enabled(update.effective_chat.id):
            return
        await _send_leave_message(context, update.effective_chat.id, user)


async def greetings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("👥 /greetings only works in groups.")
        return

    actor_id = update.effective_user.id
    if not await _ptb_is_admin(context, chat.id, actor_id):
        await update.message.reply_text("🔒 Only group admins can toggle greetings.")
        return

    from bot.utils.greetings import is_enabled, set_enabled

    if not context.args:
        state = "ON ✅" if is_enabled(chat.id) else "OFF ❌"
        await update.message.reply_text(
            f"👋 Greetings are currently: *{state}*\n\n"
            "Use `/greetings on` or `/greetings off`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    arg = context.args[0].lower()
    if arg in ("on", "enable", "enabled", "yes", "true"):
        set_enabled(chat.id, True)
        await update.message.reply_text("✅ Greetings turned ON. New members will be welcomed.")
    elif arg in ("off", "disable", "disabled", "no", "false"):
        set_enabled(chat.id, False)
        await update.message.reply_text("❌ Greetings turned OFF.")
    else:
        await update.message.reply_text("Use `/greetings on` or `/greetings off`.")


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat_id = update.effective_chat.id

    for ent in (msg.entities or []):
        if ent.type == "text_mention" and ent.user:
            u = ent.user
            text = (
                f"👤 User: {u.mention_html()}\n"
                f"🆔 User ID: <code>{u.id}</code>\n"
                f"💬 Chat ID: <code>{chat_id}</code>"
            )
            await msg.reply_text(text, parse_mode=ParseMode.HTML)
            return

    reply = msg.reply_to_message

    if reply and reply.from_user:
        u = reply.from_user
        text = (
            f"👤 User: {u.mention_html()}\n"
            f"🆔 User ID: <code>{u.id}</code>\n"
            f"💬 Chat ID: <code>{chat_id}</code>"
        )
        await msg.reply_text(text, parse_mode=ParseMode.HTML)
        return

    if context.args:
        raw = context.args[0].lstrip("@")
        resolved_id = None
        first_name = raw
        if raw.isdigit():
            try:
                chat = await context.bot.get_chat(int(raw))
                resolved_id = chat.id
                first_name = chat.first_name or raw
            except Exception:
                resolved_id = int(raw)
        else:
            try:
                user = await userbot.get_users(raw)
                resolved_id = user.id
                first_name = getattr(user, "first_name", None) or raw
            except Exception:
                try:
                    chat = await context.bot.get_chat("@" + raw)
                    resolved_id = chat.id
                    first_name = chat.first_name or raw
                except Exception as exc:
                    await msg.reply_text(f"❌ Couldn't resolve {raw}: {exc}")
                    return
        mention = f'<a href="tg://user?id={resolved_id}">{first_name}</a>'
        text = (
            f"👤 User: {mention}\n"
            f"🆔 User ID: <code>{resolved_id}</code>\n"
            f"💬 Chat ID: <code>{chat_id}</code>"
        )
        await msg.reply_text(text, parse_mode=ParseMode.HTML)
        return

    u = update.effective_user
    text = (
        f"👤 User: {u.mention_html()}\n"
        f"🆔 Your ID: <code>{u.id}</code>\n"
        f"💬 Chat ID: <code>{chat_id}</code>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML)


USERBOT_ID: int = 0


async def _post_init(application: Application) -> None:
    global USERBOT_ID
    logger.info("Starting userbot for voice chat audio...")
    await userbot.start()
    await music.start()
    me = await userbot.get_me()
    USERBOT_ID = me.id
    logger.info(f"Userbot ready as @{me.username or me.first_name} ({me.id})")


async def _ensure_userbot_in_chat(chat_id: int, bot) -> str | None:
    """Make sure the userbot is a member of `chat_id`. Returns error string on failure."""
    try:
        member = await userbot.get_chat_member(chat_id, "me")
        # Already a member if get_chat_member doesn't raise.
        if str(member.status) not in ("ChatMemberStatus.LEFT", "ChatMemberStatus.BANNED"):
            return None
    except Exception:
        pass

    invite_link: str | None = None
    try:
        link_obj = await bot.create_chat_invite_link(chat_id, name="raiden-assistant")
        invite_link = getattr(link_obj, "invite_link", None) or str(link_obj)
    except Exception as exc:
        try:
            chat = await bot.get_chat(chat_id)
            invite_link = chat.invite_link
        except Exception:
            invite_link = None
        if not invite_link:
            return (
                "I need to be an admin with **Invite Users via Link** permission to bring the "
                f"assistant in here. ({exc})"
            )

    if not invite_link:
        return "Couldn't generate an invite link for the assistant."

    join_err: str | None = None
    for attempt in range(3):
        try:
            await userbot.join_chat(invite_link)
            join_err = None
            break
        except Exception as exc:
            join_err = str(exc)
            if "INVITE_HASH_EXPIRED" in join_err or "INVITE_HASH_INVALID" in join_err:
                try:
                    link_obj = await bot.create_chat_invite_link(
                        chat_id, name=f"raiden-assistant-{attempt}"
                    )
                    invite_link = getattr(link_obj, "invite_link", None) or str(link_obj)
                except Exception:
                    pass
                await asyncio.sleep(1)
                continue
            break

    if join_err:
        return f"Assistant failed to join via the invite link: {join_err}"

    try:
        await bot.revoke_chat_invite_link(chat_id, invite_link)
    except Exception:
        pass

    return None


async def _post_shutdown(application: Application) -> None:
    try:
        await userbot.stop()
    except Exception:
        pass


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("queue", queue))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("skip", skip))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("song", song))
    app.add_handler(CommandHandler("video", video))
    app.add_handler(CommandHandler("vplay", vplay))
    app.add_handler(CommandHandler("vskip", vskip))
    app.add_handler(CommandHandler("toss", toss))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("greetings", greetings_cmd))
    app.add_handler(
        MessageHandler(tg_filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members)
    )
    app.add_handler(
        MessageHandler(tg_filters.StatusUpdate.LEFT_CHAT_MEMBER, leave_legacy)
    )
    app.add_handler(
        ChatMemberHandler(welcome_chat_member, ChatMemberHandler.CHAT_MEMBER)
    )
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))

    logger.info("Starting RaidenShogun (HTTP Bot API)...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
