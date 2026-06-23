from pyrogram import Client, filters


@Client.on_message(filters.command("id"))
async def id_command(client, message):
    reply = message.reply_to_message

    if reply and reply.from_user:
        u = reply.from_user
        text = (
            f"👤 User: {u.mention}\n"
            f"🆔 User ID: `{u.id}`\n"
            f"💬 Chat ID: `{message.chat.id}`"
        )
        await message.reply_text(text)
        return

    if len(message.command) >= 2:
        raw = message.command[1].lstrip("@")
        try:
            u = await client.get_users(int(raw) if raw.isdigit() else raw)
        except Exception as exc:
            await message.reply_text(f"❌ Couldn't resolve `{raw}`: {exc}")
            return
        text = (
            f"👤 User: {u.mention}\n"
            f"🆔 User ID: `{u.id}`\n"
            f"💬 Chat ID: `{message.chat.id}`"
        )
        await message.reply_text(text)
        return

    u = message.from_user
    text = (
        f"👤 User: {u.mention}\n"
        f"🆔 Your ID: `{u.id}`\n"
        f"💬 Chat ID: `{message.chat.id}`"
    )
    await message.reply_text(text)
