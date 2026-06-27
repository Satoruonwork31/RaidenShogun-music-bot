"""/help — paginated. Same banner photo stays in place; navigation
buttons swap the caption between pages.

Each page must fit Telegram's 1024-char media-caption limit. The
constructor below adds a small header line (page title + page
indicator) on top of the section body, so when adding/changing pages
keep the body shorter than ~950 chars to leave room for that.
"""

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

HELP_IMAGE = "https://i.ibb.co/0yjy0Cj0/0ad5a76f9731.jpg"

# Each page = (short title shown in the header, full HTML body).
# Bodies use <emoji id="ID">FALLBACK</emoji> — see help.py's note
# elsewhere about pyrofork's <emoji> vs <tg-emoji> tag.
HELP_PAGES: list[tuple[str, str]] = [
    (
        "Music",
        '<emoji id="5334653529741076580">🎶</emoji> <b>Music</b>\n'
        "• /play - Play a song\n"
        "• /vplay - Play a video in voice chat\n"
        "• /song - Search and download a song\n"
        "• /video - Search and download a video\n"
        "• /pause - Pause playback\n"
        "• /resume - Resume playback\n"
        "• /skip - Skip the current track\n"
        "• /vskip - Skip the current video\n"
        "• /stop - Stop playback\n"
        "• /queue - Show the music queue",
    ),
    (
        "Moderation",
        '<emoji id="4958900559139570572">🛡</emoji> <b>Moderation</b>\n'
        "• /ban - Ban a user in this chat\n"
        "• /unban - Unban a user in this chat\n"
        "• /gban - (sudo) global ban across every chat the bot is in\n"
        "• /removegban (alias /ungban) - (sudo) lift a global ban\n"
        "• /pin - Pin a replied message (add 'loud' to notify)\n"
        "• /unpin - Unpin a replied (or the latest) message\n"
        "• /unpinall confirm - Clear all pins\n"
        "• /purge - Reply: delete up to here. /purge n: last n. "
        "/purge n min: last n minutes (max 200, &lt;48h only)",
    ),
    (
        "General",
        '<emoji id="5816875690183631180">👋</emoji> <b>Welcome &amp; Greetings</b>\n'
        "• /greetings on|off - Toggle welcome cards on member join\n"
        "• /departure on|off - Toggle farewell messages on member leave\n\n"
        '<emoji id="5972061723400605896">🎲</emoji> <b>Fun</b>\n'
        "• /toss - Toss a coin\n"
        "• /kill - Attempt to kill another user (50/50 outcome)\n"
        "• /pat - Give someone a wholesome headpat\n"
        "• /aura - Check someone's aura level (0-100)\n"
        "• /celebrate &lt;occasion&gt; - bday/anniversary/promotion/win/welcome-back\n\n"
        '🔗 <b>Auto-download</b>\n'
        "Paste a YouTube, Instagram, or Pinterest link in any chat — I'll fetch the video and post it back.\n\n"
        '<emoji id="5350427505805238170">🆔</emoji> <b>Information</b>\n'
        "• /id - Get user, group, or chat ID\n\n"
        '<emoji id="5341715473882955310">⚙️</emoji> <b>General</b>\n'
        "• /start - Show the welcome message\n"
        "• /help - Show this help menu\n"
        "• /ping - Check if the bot is online",
    ),
    (
        "Sudo",
        '<emoji id="5341715473882955310">👑</emoji> <b>Sudo</b>\n'
        "• /stats - (sudo) bot stats and version info\n"
        "• /broadcast - (sudo) push a message to every chat\n"
        "• /seeddm - (sudo) seed user IDs into the broadcast registry\n"
        "• /addsudo - (owner) grant sudo to a user\n"
        "• /delsudo (alias /removesudo) - (owner) revoke sudo\n"
        "• /sudolist - (sudo) list current sudoers",
    ),
]

NUM_PAGES = len(HELP_PAGES)


def _build_caption(index: int) -> str:
    title, body = HELP_PAGES[index]
    return (
        f'<emoji id="5033104253846029290">🎵</emoji> '
        f"<b>RaidenShogun Music Bot</b>  "
        f"<i>· page {index + 1}/{NUM_PAGES} · {title}</i>\n\n"
        f"{body}"
    )


def _build_keyboard(index: int) -> InlineKeyboardMarkup:
    prev_idx = (index - 1) % NUM_PAGES
    next_idx = (index + 1) % NUM_PAGES
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("◀️ Prev", callback_data=f"help:{prev_idx}"),
                InlineKeyboardButton(
                    f"{index + 1}/{NUM_PAGES}", callback_data="help:noop"
                ),
                InlineKeyboardButton("Next ▶️", callback_data=f"help:{next_idx}"),
            ]
        ]
    )


@Client.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply_photo(
        photo=HELP_IMAGE,
        caption=_build_caption(0),
        parse_mode=ParseMode.HTML,
        reply_markup=_build_keyboard(0),
    )


@Client.on_callback_query(filters.regex(r"^help:(\d+|noop)$"))
async def help_page_callback(client, callback_query):
    data = callback_query.data.split(":", 1)[1]
    if data == "noop":
        await callback_query.answer()
        return
    try:
        page_idx = int(data)
    except ValueError:
        await callback_query.answer("Bad page id.", show_alert=False)
        return
    if not (0 <= page_idx < NUM_PAGES):
        await callback_query.answer("Out of range.", show_alert=False)
        return
    try:
        await callback_query.edit_message_caption(
            caption=_build_caption(page_idx),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_keyboard(page_idx),
        )
    except Exception as exc:
        # Common: MessageNotModified when user double-taps the same page.
        # Silently acknowledge — no need to alert.
        if "MESSAGE_NOT_MODIFIED" in str(exc).upper():
            await callback_query.answer()
            return
        await callback_query.answer(f"Update failed: {exc}", show_alert=True)
        return
    await callback_query.answer()
