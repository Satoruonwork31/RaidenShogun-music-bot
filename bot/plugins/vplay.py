from pyrogram import Client, filters

from bot.plugins.play import _do_play


@Client.on_message(filters.command(["vplay", "cplay"]))
async def vplay_command(client, message):
    await _do_play(client, message, is_video=True)
