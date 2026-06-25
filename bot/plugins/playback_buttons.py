"""Callback handlers for the Now Playing inline control panel.

Callback data layout: mp:<action>
  mp:prev     — step back to the previous track (if history exists)
  mp:toggle   — pause if playing, resume if paused (we don't track
                state explicitly, so we try pause first and fall back
                to resume on failure)
  mp:next     — skip to next track
  mp:skip     — alias of next, kept because the user asked for both
  mp:shuffle  — random-shuffle the upcoming queue
  mp:loop     — toggle the per-chat repeat flag
  mp:stop     — end the session (clears queue, leaves VC + group)

Authorization: any user in the chat may click. Voice-chat controls
have historically been open in this bot's text-command surface so
this matches.

Each handler refreshes the Now Playing message in place when the
visible state (track / repeat) changes.
"""

import logging

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

from bot.utils import music as music_mod
from bot.utils import queue as q
from bot.utils.np_ui import nowplaying_keyboard, render_for_chat
from bot.utils.playback import end_session, play_track

logger = logging.getLogger("RaidenShogun.playback_buttons")


async def _refresh_card(callback_query) -> None:
    """Re-render the Now Playing card in place if a track is currently set."""
    chat_id = callback_query.message.chat.id
    cur = q.now_playing(chat_id)
    if cur is None:
        return
    try:
        await callback_query.message.edit_text(
            render_for_chat(chat_id, cur),
            parse_mode=ParseMode.HTML,
            reply_markup=nowplaying_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception as exc:
        # MessageNotModified is harmless. Anything else we just log.
        if "MESSAGE_NOT_MODIFIED" not in str(exc).upper():
            logger.info("refresh_card edit failed: %s", exc)


@Client.on_callback_query(filters.regex(r"^mp:(prev|toggle|next|skip|shuffle|loop|stop)$"))
async def mp_callback(client, callback_query):
    action = callback_query.data.split(":", 1)[1]
    chat_id = callback_query.message.chat.id if callback_query.message and callback_query.message.chat else None

    if chat_id is None:
        await callback_query.answer("Lost the chat — try /play again.", show_alert=True)
        return

    if not q.is_active(chat_id) and action not in ("stop",):
        await callback_query.answer("Nothing is playing.", show_alert=False)
        return

    music = music_mod.music

    try:
        if action == "toggle":
            # Try pause; if py-tgcalls reports "not paused" we treat it
            # as a resume request. Different py-tgcalls versions raise
            # different exception classes, so go by message.
            try:
                await music.pause(chat_id)
                await callback_query.answer("Paused.")
            except Exception as exc:
                msg = str(exc).lower()
                if "paused" in msg or "not playing" in msg or "already" in msg:
                    try:
                        await music.resume(chat_id)
                        await callback_query.answer("Resumed.")
                    except Exception as exc2:
                        await callback_query.answer(f"Resume failed: {exc2}", show_alert=True)
                else:
                    await callback_query.answer(f"Pause failed: {exc}", show_alert=True)
            return

        if action in ("next", "skip"):
            nxt = q.pop_next(chat_id)
            if nxt is None:
                await end_session(chat_id)
                await callback_query.answer("Queue empty — assistant left the group.", show_alert=False)
                try:
                    await callback_query.message.edit_text(
                        "⏹️ Playback ended. The assistant has left the group.",
                        reply_markup=None,
                    )
                except Exception:
                    pass
                return
            await play_track(chat_id, nxt)
            await callback_query.answer(f"Skipped → {nxt.title[:40]}")
            await _refresh_card(callback_query)
            return

        if action == "prev":
            prev = q.pop_history(chat_id)
            if prev is None:
                await callback_query.answer("No previous track.", show_alert=False)
                return
            await play_track(chat_id, prev)
            await callback_query.answer(f"Rewound → {prev.title[:40]}")
            await _refresh_card(callback_query)
            return

        if action == "shuffle":
            n = q.shuffle_upcoming(chat_id)
            if n < 2:
                await callback_query.answer("Need at least 2 upcoming tracks to shuffle.", show_alert=False)
                return
            await callback_query.answer(f"Shuffled {n} upcoming tracks.")
            return

        if action == "loop":
            new = q.toggle_repeat(chat_id)
            await callback_query.answer(f"Repeat: {'ON' if new else 'OFF'}.")
            await _refresh_card(callback_query)
            return

        if action == "stop":
            await end_session(chat_id)
            await callback_query.answer("Stopped. Assistant left the group.")
            try:
                await callback_query.message.edit_text(
                    "⏹️ Playback stopped. The assistant has left the group.",
                    reply_markup=None,
                )
            except Exception:
                pass
            return

    except Exception as exc:
        logger.exception("mp callback %s failed", action)
        await callback_query.answer(f"{type(exc).__name__}: {exc}", show_alert=True)
