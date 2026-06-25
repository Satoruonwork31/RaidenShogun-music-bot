"""Now-playing message renderer + control keyboard.

Layout matches the user-supplied mockup: boxed header, track block,
static progress bar, decorative control row with premium custom emoji,
requester / repeat footer box.

Telegram custom-emoji uses pyrofork's <emoji id="...">FALLBACK</emoji>
syntax (not <custom_emoji ...>). Fallback glyphs are visible on clients
without premium-emoji support.

The progress bar is intentionally static. Real-time updates would
require either an in-process tick task per chat or repeated message
edits, both of which break Telegram's edit rate limits in heavy use.
"""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils import queue as q

# Custom emoji IDs taken from the spec.
_EMOJI_PLAY = "4956442665320186933"
_EMOJI_VOL = "5253809111220364948"
_EMOJI_REQ = "5818715087237549366"
_EMOJI_REPEAT = "5249019346512008974"

# Box-drawing top and bottom of the now-playing header.
_TOP = "╭━━━━━━━━━━━━━━━ ♫ ━━━━━━━━━━━━━━━╮"
_BOT = "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"

# Inner separator between track title and "Telegram Music" tag.
_INNER_SEP = "──────────────────"

# Footer box.
_FOOT_TOP = "╭────────────────────────────────╮"
_FOOT_BOT = "╰────────────────────────────────╯"

# Static 14-cell progress bar — "▰▰▰▰▱▱▱▱▱▱▱▱▱▱". Sender sees a fresh
# render, so we always start the indicator near the head of the track.
_PROGRESS_BAR = "▰▰▰▰▱▱▱▱▱▱▱▱▱▱"


def _fmt_dur(seconds) -> str:
    if not seconds or seconds <= 0:
        return "LIVE"
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def render_now_playing(track, duration=None) -> str:
    """Return the HTML caption for a Now Playing message.

    `duration` is the upstream track duration in seconds (None / 0 for
    live streams).
    """
    title = (track.title or "Unknown title").strip()
    requester = (track.requested_by or "someone").strip()
    end = _fmt_dur(duration)
    # The repeat flag lives per-chat. Callers that know the chat should
    # use render_for_chat; this function defaults to OFF.
    repeat = "OFF"

    return (
        f"{_TOP}\n"
        f"         ✦  ɴᴏᴡ sᴘɪɴɴɪɴɢ  ✦\n"
        f"{_BOT}\n"
        f"\n"
        f"      🎧  {title}\n"
        f"      {_INNER_SEP}\n"
        f"      ✦  Telegram Music  ✦\n"
        f"\n"
        f"{_PROGRESS_BAR}  0:00 / {end}\n"
        f"\n"
        f'⏮     <emoji id="{_EMOJI_PLAY}">▶️</emoji>     ⏭\n'
        f'      <emoji id="{_EMOJI_VOL}">🔊</emoji> 100%\n'
        f"\n"
        f"{_FOOT_TOP}\n"
        f'<emoji id="{_EMOJI_REQ}">👤</emoji>  ʀᴇǫ • {requester}\n'
        f'<emoji id="{_EMOJI_REPEAT}">🔁</emoji>  Repeat : {repeat}\n'
        f"{_FOOT_BOT}"
    )


def render_for_chat(chat_id: int, track, duration=None) -> str:
    """Same as render_now_playing but reads the chat's repeat flag."""
    title = (track.title or "Unknown title").strip()
    requester = (track.requested_by or "someone").strip()
    end = _fmt_dur(duration)
    repeat = "ON" if q.get_repeat(chat_id) else "OFF"

    return (
        f"{_TOP}\n"
        f"         ✦  ɴᴏᴡ sᴘɪɴɴɪɴɢ  ✦\n"
        f"{_BOT}\n"
        f"\n"
        f"      🎧  {title}\n"
        f"      {_INNER_SEP}\n"
        f"      ✦  Telegram Music  ✦\n"
        f"\n"
        f"{_PROGRESS_BAR}  0:00 / {end}\n"
        f"\n"
        f'⏮     <emoji id="{_EMOJI_PLAY}">▶️</emoji>     ⏭\n'
        f'      <emoji id="{_EMOJI_VOL}">🔊</emoji> 100%\n'
        f"\n"
        f"{_FOOT_TOP}\n"
        f'<emoji id="{_EMOJI_REQ}">👤</emoji>  ʀᴇǫ • {requester}\n'
        f'<emoji id="{_EMOJI_REPEAT}">🔁</emoji>  Repeat : {repeat}\n'
        f"{_FOOT_BOT}"
    )


def nowplaying_keyboard() -> InlineKeyboardMarkup:
    """Inline controls under the Now Playing message.

    Layout:
      ⏮ Prev   ⏯ Pause/Resume   ⏭ Next
      🔀 Shuffle   🔁 Loop   ⏹ Stop
      ⏭ Skip
    Skip is functionally identical to Next — kept as a separate row
    because the user explicitly asked for both.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏮", callback_data="mp:prev"),
                InlineKeyboardButton("⏯", callback_data="mp:toggle"),
                InlineKeyboardButton("⏭", callback_data="mp:next"),
            ],
            [
                InlineKeyboardButton("🔀 Shuffle", callback_data="mp:shuffle"),
                InlineKeyboardButton("🔁 Loop", callback_data="mp:loop"),
                InlineKeyboardButton("⏹ Stop", callback_data="mp:stop"),
            ],
            [
                InlineKeyboardButton("⏭ Skip", callback_data="mp:skip"),
            ],
        ]
    )
