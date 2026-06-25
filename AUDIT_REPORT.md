# RaidenShogun Music Bot — Audit Report

Date: 2026-06-24 (initial), 2026-06-25 (delta below)

## 2026-06-25 — Delta

Resolved this pass (see context.txt Fix History for details):
- **Owner-gating false-rejections** — `OWNER_ID` env var now accepts a
  comma/whitespace list; if unset, the bot still falls back to the
  userbot id but logs a warning. Denial messages from
  `/sudolist /addsudo /removesudo /broadcast /stats` now show the
  caller's id and the configured owner ids, so misconfiguration is
  visible at the user level.
- **Departures silent** — split out of the `/greetings` toggle. New
  `bot/utils/departure.py` + `bot/plugins/departure.py`, default ON,
  admin-gated `/departure on|off`. `bot/plugins/welcome.py` leave
  handlers now consult `departure.is_enabled`.
- **HIGH-3 (assistant not auto-invited)** — partially addressed.
  `bot/utils/playback.py::ensure_userbot_in_chat` uses
  `app.export_chat_invite_link` + `userbot.join_chat`. Works only if
  the bot is admin with invite-link rights; otherwise reports a clear
  error.
- **New: assistant auto-leave after VC** — anti-misuse. Natural
  stream-end with empty queue, `/stop`, `/end`, and `/skip` on empty
  queue all call `playback.end_session()` which leaves the call AND
  has the userbot leave the group.

Still open:
- CRIT-1 (credential leak) — still requires user action (rotate
  BOT_TOKEN, STRING_SESSION, purge `.env` from git history).
- HIGH-2 (unpinned requirements) — unchanged.
- MED-1, MED-2, MED-3, MED-4 (already noted in original).
- MED-5 / MED-6 — unchanged.

---

## Original report (2026-06-24)
Auditor scope: static read of `main.py`, `bot/`, `ptb_main.py`, `scripts/`,
`requirements.txt`, `.env`, `.gitignore`, recent `git log`. No runtime
execution (Telegram network unavailable in this sandbox, and the leaked
credentials make any live test unsafe).

---

## CRITICAL

### CRIT-1 — Telegram credentials committed to git history on public remote
**Files:** `.env`
**Evidence:** `git log -- .env` shows three commits touching it:
- `994c6a2` Add environment variables for API configuration
- `fc918ae` Refactor .env file formatting
- `989e238` Update STRING_SESSION in .env file

`git remote -v` → `https://github.com/Satoruonwork31/RaidenShogun-music-bot`.
Anyone with read access to the repo has the bot's `BOT_TOKEN`, the userbot's
`API_HASH`, and the userbot's `STRING_SESSION`. The string session is
particularly dangerous — it grants full account access, not just bot scope.

**Action required (by user, not auto-fixable):**
1. In @BotFather: revoke and reissue `BOT_TOKEN` for the bot.
2. In `my.telegram.org`: reset the API_HASH (or accept that it's known
   and rely on token rotation; API_HASH alone isn't auth).
3. **Revoke the userbot STRING_SESSION.** Sign in to that account via
   official Telegram app → Devices → terminate the active session that
   matches the leaked one. Generate a fresh string session.
4. Purge `.env` from git history (`git filter-repo --invert-paths --path .env`
   or BFG). Force-push. *This is destructive and rewrites history — ask
   first before doing it.*
5. Confirm `.env` is matched by `.gitignore`. (It is: the gitignore covers
   `*.env`-related patterns in the Python template.)

**Why this is critical, not high:** with the userbot session, an attacker
can read every message in every chat the userbot account is in, post as
that account, and join/leave groups. Token-only leaks are bad; session
leaks are catastrophic.

---

### CRIT-2 — Music control commands are placeholder text replies
**Files:**
- `bot/plugins/skip.py`
- `bot/plugins/pause.py`
- `bot/plugins/resume.py`
- `bot/plugins/stop.py`
- `bot/plugins/queue.py`
- `bot/plugins/vplay.py`
- `bot/plugins/vskip.py`
- `bot/plugins/song.py`
- `bot/plugins/video.py`

**Symptom:** every one of those handlers does `await message.reply_text("...")`
and nothing else. They never touch `music` (the PyTgCalls instance) and they
never modify any queue. The bot lies to the user: it claims it skipped /
paused / stopped, but playback continues unchanged.

**Evidence:** e.g. `bot/plugins/skip.py:1-7`:
```python
@Client.on_message(filters.command("skip"))
async def skip_command(client, message):
    await message.reply_text("⏭️ Skipped to the next track.")
```

**Fix sketch (pyrogram path):**
- `/pause` → `await music.pause_stream(message.chat.id)`
- `/resume` → `await music.resume_stream(message.chat.id)`
- `/stop` → `await music.leave_group_call(message.chat.id)` + clear queue.
- `/skip` → pop next from per-chat queue, `await music.change_stream(...)` or
  leave+rejoin with the new MediaStream.
- `/queue` → render the per-chat queue list.
- `/vplay` / `/vskip` / `/song` / `/video` are aspirational — either
  implement (vplay = VideoQuality stream, song = ydl download+send_audio,
  video = ydl mp4 download+send_video) or remove from `/help`.

A reference implementation exists in `ptb_main.py` (functions `pause`,
`resume`, `stop`, `skip` around lines 228-264). Same py-tgcalls API.

---

### CRIT-3 — No queue. /play overrides whatever is currently playing.
**Files:** `bot/plugins/play.py`, `bot/utils/queue.py`
**Symptom:** `bot/utils/queue.py` is literally `QUEUE = {}` and is imported
by nothing. Calling `/play song B` while song A is streaming causes PyTgCalls
to switch to B without any "added to queue" semantics. The `/help` text
promises a queue (`/queue - Show the music queue`); none exists.

**Fix:** introduce a real queue (per-chat `list[Track]`), have `/play`
enqueue when something is already playing, register a stream-ended callback
on the PyTgCalls instance to auto-advance, and have `/queue` print it.

---

## HIGH

### HIGH-1 — Dual parallel implementations, only one deployed
**Files:** `ptb_main.py` (830 lines, python-telegram-bot) vs.
`main.py` → `bot/start.py` (pyrogram).
**Symptom:**
- `main.py` (and therefore the systemd unit in `scripts/install.sh:71`)
  runs the pyrogram path, which has the stub handlers.
- `ptb_main.py` runs python-telegram-bot, has *real* play/pause/resume/skip/
  stop/ban/unban/welcome/leave handlers, plus `_ensure_userbot_in_chat`
  logic that pre-invites the assistant to the group, plus a more complete
  `/play` that downloads replied media and supports both `/play` and
  inline-button flows.
- `requirements.txt` does NOT list `python-telegram-bot`, so even if you
  pointed systemd at `ptb_main.py`, fresh installs would fail at import.

**Why this matters:** the user is currently running the *less complete*
implementation. The work in `ptb_main.py` is unreachable from the deployment.

**Decision needed (user):**
- (a) Port the missing handlers from `ptb_main.py` into `bot/plugins/`,
  keep pyrogram, delete `ptb_main.py`.
- (b) Switch the deployment to `ptb_main.py`: add `python-telegram-bot` to
  `requirements.txt`, change `scripts/install.sh:71` ExecStart, delete `bot/`.

Option (a) is closer to recent commit history (the multi-client yt-dlp work,
welcome card work, etc. all sit in `bot/*`). Recommend (a).

---

### HIGH-2 — requirements.txt fully unpinned
**File:** `requirements.txt`
```
pyrofork
py-tgcalls
tgcrypto
python-dotenv
yt-dlp
aiohttp
Pillow
```
**Symptom:** every fresh `pip install -r` pulls the latest of each. py-tgcalls
and pyrofork have had breaking releases as recently as Q1 2026. yt-dlp ships
multiple times a week. This is the single most common cause of "it worked
yesterday, now it crashes on import."

**Fix:** pin to the versions currently working on the deployed VPS. You can
grab them with `pip freeze` on the live box and replace `requirements.txt`
with that output. Then loosen only the pins you have a reason to (`yt-dlp>=...`
makes sense; `pyrofork>=...` does not).

---

### HIGH-3 — No `_ensure_userbot_in_chat` in pyrogram path
**File:** `bot/plugins/play.py` — `play_command` calls `music.play(chat_id,...)`
directly. PyTgCalls will raise `NotInGroupCallError` / userbot-must-be-in-chat
errors if the assistant account isn't already a member of the group.

**Evidence:** `ptb_main.py:720-779` (`_ensure_userbot_in_chat`) has the logic:
look up the group invite link via the bot, have the userbot join, then start
the call. The pyrogram path skips this entirely.

**Fix:** port `_ensure_userbot_in_chat` to `bot/plugins/play.py`. The pyrogram
APIs are slightly different but functionally identical
(`app.export_chat_invite_link`, `userbot.join_chat`).

---

## MEDIUM

### MED-1 — No top-level exception handler in startup
**File:** `bot/start.py:11-21`
**Symptom:** if `userbot.start()` raises (wrong session string, network),
`asyncio.run(_run())` propagates and the process dies with a stack trace.
systemd will restart per its `Restart=on-failure`, but logs show only the
raw traceback with no context line about which stage failed. Wrap each
start step with a try/log/re-raise so journalctl shows `failed at userbot.start`
rather than a bare TimeoutError.

### MED-2 — `bot/core/music.py` is dead code
**File:** `bot/core/music.py`
```python
from pytgcalls import PyTgCalls
```
That's the whole file. No symbol exported, no side effect. The real instance
lives in `bot/utils/music.py`. Delete `bot/core/music.py`.

### MED-3 — `bot/utils/queue.py` is dead code (until CRIT-3 is fixed)
Imported by nothing. Either wire it up as part of the queue work or delete it.

### MED-4 — `/help` advertises commands that don't exist or don't work
**File:** `bot/plugins/help.py`
**Symptom:** the help block lists `/vplay`, `/vskip`, `/song`, `/video`,
`/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/welcome`, all of which are
either placeholders (CRIT-2) or aren't implemented as a handler at all
(`/welcome` has no command handler — only the join-event handlers exist).
Either implement them or trim the help text.

### MED-5 — Lazy `from bot.client import userbot` inside handlers
**Files:** `bot/plugins/id.py:34`, `bot/plugins/ban.py:41`, `bot/plugins/unban.py:39`
**Symptom:** importing inside the function works (Python module cache makes
it cheap after first call) but it's a smell — and if `bot/client.py` raised
on import (e.g. bad config), the error surfaces inside a handler rather than
at startup. Move these to top-of-file imports; they don't create cycles.

### MED-6 — `bot/utils/youtube.py` purpose unclear
File exists, was not read in this pass. Likely older / alternative
yt-dlp wrapper superseded by `bot/utils/player.py`. Either delete or
document. (Open item — re-read in next session.)

---

## LOW

### LOW-1 — `os.makedirs(DOWNLOAD_DIR, exist_ok=True)` per-call
**File:** `bot/plugins/play.py:61`
**Symptom:** harmless but redundant — do it once at module load.

### LOW-2 — Welcome-card avatar files accumulate in `/tmp/raiden_pfps`
**File:** `bot/plugins/welcome.py:42`
**Symptom:** every new join writes `/tmp/raiden_pfps/<user_id>.jpg` and
nothing reaps them. `/tmp` gets cleared on reboot so disk pressure is
bounded, but consider deleting after `send_photo` finishes.

### LOW-3 — Hard-coded image URLs in `/start`, `/help`
**Files:** `bot/plugins/start.py:7`, `bot/plugins/help.py:3`
URLs at `i.ibb.co` are owned by a third party. If they're deleted /
moved, those commands break. Consider committing the images to the repo
or owning the asset host.

### LOW-4 — `pick_leave_message` ring buffer is in-process only
**File:** `bot/utils/leave_messages.py`
**Symptom:** anti-repeat state lives in-memory; restart wipes it.
Acceptable for a 12-line window — not worth fixing.

### LOW-5 — `bot/utils/greetings.py` writes JSON without atomic rename
**File:** `bot/utils/greetings.py:33-38`
**Symptom:** kill -9 mid-write could truncate the file. Switch to
`tmp + os.replace`.

### LOW-6 — `audio_parameters=AudioQuality.HIGH` hard-coded
**File:** `bot/plugins/play.py:80`
Acceptable default. Make configurable later if users want lower-bitrate
for poor-network groups.

---

## Open questions for the user

1. **Which path do we consolidate around — pyrogram (`bot/*`) or
   python-telegram-bot (`ptb_main.py`)?** This blocks all music-control fixes.
2. **Is the deployed bot currently used in real groups?** If yes, the
   credential rotation in CRIT-1 should be coordinated with a maintenance window.
3. **Has the git history of `.env` already been seen by anyone outside your
   team?** Determines whether we need to history-rewrite or simply
   rotate-and-move-on.

---

## What's NOT in this report

This was a one-pass static audit. The following deserve their own deep dive
once the path decision is made:

- Race conditions inside the music control flow once a real queue exists
  (concurrent /skip vs auto-advance).
- Network resilience of yt-dlp signature solver (`remote_components`).
- ffmpeg subprocess lifecycle leaks under py-tgcalls.
- The Spotify and Resso resolvers (not read this pass).
- The welcome-image PIL pipeline (not read this pass).
