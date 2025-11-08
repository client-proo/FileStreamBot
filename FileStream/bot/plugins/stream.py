import asyncio
from FileStream.bot import FileStream, multi_clients
from FileStream.utils.bot_utils import is_user_banned, is_user_exist, is_user_joined, gen_link, is_channel_banned, is_channel_exist, is_user_authorized
from FileStream.utils.database import Database
from FileStream.utils.file_properties import get_file_ids, get_file_info
from FileStream.config import Telegram
from pyrogram import filters, Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

@FileStream.on_message(
    filters.private
    & (
            filters.document
            | filters.video
            | filters.video_note
            | filters.audio
            | filters.voice
            | filters.animation
            | filters.photo
    ),
    group=4,
)
async def private_receive_handler(bot: Client, message: Message):
    if not await is_user_authorized(message):
        return
    if await is_user_banned(message):
        return

    await is_user_exist(bot, message)
    if Telegram.FORCE_SUB:
        if not await is_user_joined(bot, message):
            return

    # آنتی اسپم هوشمند
    if Telegram.SPAM_PROTECTION and await db.is_user_on_cooldown(message.from_user.id):
        last_time = await db.get_user_last_link_time(message.from_user.id)
        remaining = int(Telegram.USER_COOLDOWN_SECONDS - (time.time() - last_time))
        hours = remaining // 3600
        mins = (remaining % 3600) // 60
        secs = remaining % 60

        time_text = ""
        if hours: time_text += f"{hours} ساعت "
        if mins: time_text += f"{mins} دقیقه "
        if secs: time_text += f"{secs} ثانیه"

        await message.reply_text(
            f"<b>آنتی اسپم فعال است!</b>\n\n"
            f"هر <b>{Telegram.USER_COOLDOWN_SECONDS // 3600} ساعت</b> فقط یک لینک\n\n"
            f"<b>زمان باقی‌مانده:</b>\n"
            f"<code>{time_text.strip()}</code>",
            parse_mode=ParseMode.HTML,
            quote=True
        )
        return

    try:
        # لینک با انقضای زمانی
        inserted_id = await db.add_file(get_file_info(message), expire_seconds=Telegram.LINK_EXPIRE_SECONDS)
        await get_file_ids(False, inserted_id, multi_clients, message)
        reply_markup, stream_text = await gen_link(_id=inserted_id)
        reply_msg = await message.reply_text(
            text=stream_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
            quote=True
        )

        # حذف خودکار بعد از انقضا
        await asyncio.sleep(Telegram.LINK_EXPIRE_SECONDS)
        try:
            await reply_msg.delete()
            await db.delete_one_file(inserted_id)
            await db.count_links(message.from_user.id, "-")
        except:
            pass

    except FloodWait as e:
        print(f"Sleeping for {str(e.value)}s")
        await asyncio.sleep(e.value)
        await bot.send_message(chat_id=Telegram.ULOG_CHANNEL,
                               text=f"Gᴏᴛ FʟᴏᴏᴅWᴀɪᴛ ᴏғ {str(e.value)}s ғʀᴏᴍ [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n\n**ᴜsᴇʀ ɪᴅ :** `{str(message.from_user.id)}`",
                               disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


@FileStream.on_message(
    filters.channel
    & ~filters.forwarded
    & ~filters.media_group
    & (
            filters.document
            | filters.video
            | filters.video_note
            | filters.audio
            | filters.voice
            | filters.photo
    )
)
async def channel_receive_handler(bot: Client, message: Message):
    if await is_channel_banned(bot, message):
        return
    await is_channel_exist(bot, message)

    try:
        inserted_id = await db.add_file(get_file_info(message))
        await get_file_ids(False, inserted_id, multi_clients, message)
        reply_markup, stream_link = await gen_link(_id=inserted_id)
        await bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.id,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📥 دانلود",
                                       url=f"https://t.me/{FileStream.username}?start=stream_{str(inserted_id)}")]])
        )

    except FloodWait as w:
        print(f"Sleeping for {str(w.x)}s")
        await asyncio.sleep(w.x)
        await bot.send_message(chat_id=Telegram.ULOG_CHANNEL,
                               text=f"ɢᴏᴛ ғʟᴏᴏᴅᴡᴀɪᴛ ᴏғ {str(w.x)}s ғʀᴏᴍ {message.chat.title}\n\n**ᴄʜᴀɴɴᴇʟ ɪᴅ :** `{str(message.chat.id)}`",
                               disable_web_page_preview=True)
    except Exception as e:
        await bot.send_message(chat_id=Telegram.ULOG_CHANNEL, text=f"**#EʀʀᴏʀTʀᴀᴄᴋᴇʙᴀᴄᴋ:** `{e}`",
                               disable_web_page_preview=True)
        print(f"Cᴀɴ'ᴛ Eᴅɪᴛ Bʀᴏᴀᴅᴄᴀsᴛ Mᴇssᴀɢᴇ!\nEʀʀᴏʀ:  **Gɪᴠᴇ ᴍᴇ ᴇᴅɪᴛ ᴘᴇʀᴍɪssɪᴏɴ ɪɴ ᴜᴘᴅᴀᴛᴇs ᴀɴᴅ ʙɪɴ Cʜᴀɴɴᴇʟ!{e}**")