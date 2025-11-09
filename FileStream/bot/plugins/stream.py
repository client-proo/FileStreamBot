import time
import asyncio
from FileStream.bot import FileStream, multi_clients
from FileStream.utils.bot_utils import (
    is_user_banned, is_user_exist, is_user_joined,
    gen_link, is_channel_banned, is_channel_exist,
    is_user_authorized, seconds_to_hms
)
from FileStream.utils.database import Database
from FileStream.utils.file_properties import get_file_ids, get_file_info
from FileStream.config import Telegram
from pyrogram import filters, Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)


# ====================== PRIVATE FILE HANDLER ======================
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

    file_unique_id = get_file_info(message)['file_unique_id']

    # 1. چک ضد تکرار (اول)
    is_repeat, remaining_repeat = await db.check_repeat(message.from_user.id, file_unique_id)
    if is_repeat:
        await message.reply_text(
            f"فایل تکراری است! لطفاً {seconds_to_hms(remaining_repeat)} صبر کنید.",
            quote=True
        )
        return  # مهم: return کن تا check_spam اجرا نشه

    # 2. چک ضد اسپم (فقط برای فایل جدید)
    remaining_spam, is_spam = await db.check_spam(message.from_user.id)
    if is_spam:
        await message.reply_text(
            f"اسپم نکنید! منتظر بمانید {seconds_to_hms(int(remaining_spam))}",
            quote=True
        )
        return

    try:
        # 3. اضافه کردن فایل
        inserted_id = await db.add_file(get_file_info(message))
        await get_file_ids(False, inserted_id, multi_clients, message)

        # 4. ساخت لینک
        reply_markup, stream_text = await gen_link(_id=inserted_id)
        if reply_markup is None:
            await message.reply_text("لینک منقضی شده است!")
            return

        # 5. ارسال پیام
        reply_msg = await message.reply_text(
            text=stream_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
            quote=True
        )

        # 6. حذف خودکار بعد از انقضا
        expire_delay = Telegram.EXPIRE_TIME
        if expire_delay > 0:
            asyncio.create_task(delete_after_expire(reply_msg, expire_delay))

    except FloodWait as e:
        print(f"Sleeping for {e.value}s")
        await asyncio.sleep(e.value)
        await bot.send_message(
            chat_id=Telegram.ULOG_CHANNEL,
            text=f"Gᴏᴛ FʟᴏᴏᴅWᴀɪᴛ ᴏғ {e.value}s ғʀᴏᴍ [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n\n**ᴜsᴇʀ ɪᴅ :** `{message.from_user.id}`",
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Error in private handler: {e}")


# ====================== AUTO DELETE AFTER EXPIRE ======================
async def delete_after_expire(msg: Message, delay: float):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
        await msg.reply_text("لینک شما منقضی شد!")
    except:
        pass  # اگر پیام حذف شده بود


# ====================== CHANNEL FILE HANDLER ======================
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

    file_unique_id = get_file_info(message)['file_unique_id']

    # چک ضد تکرار (در کانال)
    is_repeat, _ = await db.check_repeat(message.chat.id, file_unique_id)
    if is_repeat:
        return  # جلوگیری از آپلود تکراری

    try:
        inserted_id = await db.add_file(get_file_info(message))
        await get_file_ids(False, inserted_id, multi_clients, message)
        reply_markup, _ = await gen_link(_id=inserted_id)

        # سعی برای ویرایش پیام
        try:
            await bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=message.id,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("دانلود", url=f"https://t.me/{FileStream.username}?start=stream_{inserted_id}")]
                ])
            )
        except Exception as e:
            # fallback: پیام جدید
            await bot.send_message(
                chat_id=message.chat.id,
                text="لینک دانلود:",
                reply_to_message_id=message.id,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("دانلود فایل", url=f"https://t.me/{FileStream.username}?start=stream_{inserted_id}")]
                ])
            )

    except FloodWait as w:
        print(f"Sleeping for {w.value}s")
        await asyncio.sleep(w.value)
        await bot.send_message(
            chat_id=Telegram.ULOG_CHANNEL,
            text=f"ɢᴏᴛ ғʟᴏᴏᴅᴡᴀɪᴛ ᴏғ {w.value}s ғʀᴏᴍ {message.chat.title}\n\n**ᴄʜᴀɴɴᴇʟ ɪᴅ :** `{message.chat.id}`",
            disable_web_page_preview=True
        )
    except Exception as e:
        await bot.send_message(
            chat_id=Telegram.ULOG_CHANNEL,
            text=f"**#EʀʀᴏʀTʀᴀᴄᴋᴇʙᴀᴄᴋ:** `{e}`",
            disable_web_page_preview=True
        )
        print(f"Can't Edit Broadcast Message!\nError: {e}")