from pyrogram import Client, filters

# /vskip is identical to /skip — there's one VC per chat, so audio and
# video share the same queue. Re-using the implementation keeps behaviour
# consistent and stops the two from drifting apart.
from bot.plugins.skip import _skip


@Client.on_message(filters.command("vskip"))
async def vskip_command(client, message):
    await _skip(message)
