import time
import asyncio
from FileStream.bot import FileStream, multi_clients
from FileStream.utils.bot_utils import (
    is_user_banned, is_user_exist, is_user_joined,
    gen_link, is_channel_banned, is_channel_exist,
    is_user_authorized, seconds_to_hms, check_file_size_limit
)
from FileStream.utils.database import Database
from FileStream.utils.file_properties import get_file_ids, get_file_info
from FileStream.config import Telegram
from pyrogram import filters, Client
from pyrogram.errors import FloodWait, MessageDeleteForbidden
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

    file_info = get_file_info(message)
    file_size = file_info['file_size']

    # بررسی محدودیت حجم فایل
    if not await check_file_size_limit(message, file_size):
        return

    file_unique_id = file_info['file_unique_id']

    # چک ضد تکرار
    is_repeat, remaining_repeat = await db.check_repeat(message.from_user.id, file_unique_id)
    if is_repeat:
        remaining_readable = seconds_to_hms(remaining_repeat)
        await message.reply_text(
            f"این فایل هنوز معتبر است! لینک قبلی تا **{remaining_readable}** دیگر فعال است.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    # چک ضد اسپم
    remaining_spam, is_spam = await db.check_spam(message.from_user.id)
    if is_spam:
        remaining_readable = seconds_to_hms(int(remaining_spam))
        await message.reply_text(
            f"اسپم نکنید! منتظر بمانید **{remaining_readable}**",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    reply_msg = None
    inserted_id = None

    try:
        # --- 1. اضافه کردن فایل به دیتابیس ---
        inserted_id = await db.add_file(get_file_info(message))
        await get_file_ids(False, inserted_id, multi_clients, message)

        # --- 2. ساخت لینک ---
        reply_markup, stream_text = await gen_link(_id=inserted_id)
        if reply_markup is None:
            await message.reply_text("لینک منقضی شده است!")
            return

        # --- 3. ارسال پیام لینک ---
        reply_msg = await message.reply_text(
            text=stream_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
            quote=True
        )

        # --- 4. زمان‌بندی حذف + پاک کردن دیتابیس ---
        expire_delay = max(Telegram.EXPIRE_TIME, 1)
        asyncio.create_task(
            delete_after_expire(
                reply_msg=reply_msg,
                original_msg=message,
                user_id=message.from_user.id,
                file_id=inserted_id,
                delay=expire_delay
            )
        )

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await bot.send_message(chat_id=Telegram.ULOG_CHANNEL, text=f"FloodWait {e.value}s")

    except Exception as e:
        print(f"Error in private handler: {e}")
        await message.reply_text("خطایی رخ داد! دوباره تلاش کنید.")

        # --- پاک کردن فایل ناقص از دیتابیس ---
        if inserted_id:
            try:
                await db.delete_one_file(inserted_id)
                print(f"Cleaned up incomplete file {inserted_id}")
            except Exception as cleanup_error:
                print(f"Cleanup failed: {cleanup_error}")


# ====================== AUTO DELETE + DB CLEANUP + EXPIRED MESSAGE ======================
async def delete_after_expire(reply_msg: Message, original_msg: Message, user_id: int, file_id: int, delay: float):
    await asyncio.sleep(delay)

    # --- 1. حذف پیام لینک ---
    try:
        await reply_msg.delete()
        print(f"Link message deleted: {reply_msg.id}")
    except MessageDeleteForbidden:
        print(f"Cannot delete link message (forbidden): {reply_msg.id}")
    except Exception as e:
        print(f"Error deleting link message: {e}")

    # --- 2. پاک کردن فایل از دیتابیس ---
    try:
        await db.delete_one_file(file_id)
        await db.count_links(user_id, "-")
        print(f"File {file_id} expired and deleted from DB")
    except Exception as e:
        print(f"Error deleting expired file from DB: {e}")

    # --- 3. ارسال پیام منقضی شده ---
    try:
        if original_msg and original_msg.id:
            await original_msg.reply_text(
                "لینک شما منقضی شد!",
                quote=True
            )
        else:
            await FileStream.send_message(
                chat_id=user_id,
                text="لینک شما منقضی شد!"
            )
    except Exception as e:
        print(f"Could not send expired message: {e}")
        try:
            await FileStream.send_message(chat_id=user_id, text="لینک شما منقضی شد!")
        except Exception:
            pass


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
    is_repeat, _ = await db.check_repeat(message.chat.id, file_unique_id)
    if is_repeat:
        return

    try:
        inserted_id = await db.add_file(get_file_info(message))
        await get_file_ids(False, inserted_id, multi_clients, message)
        reply_markup, _ = await gen_link(_id=inserted_id)

        try:
            await bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=message.id,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("دانلود", url=f"https://t.me/{FileStream.username}?start=stream_{inserted_id}")]
                ])
            )
        except Exception:
            await bot.send_message(
                chat_id=message.chat.id,
                text="لینک دانلود:",
                reply_to_message_id=message.id,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("دانلود فایل", url=f"https://t.me/{FileStream.username}?start=stream_{inserted_id}")]
                ])
            )

    except FloodWait as w:
        await asyncio.sleep(w.value)
        await bot.send_message(chat_id=Telegram.ULOG_CHANNEL, text=f"FloodWait {w.value}s")
    except Exception as e:
        await bot.send_message(chat_id=Telegram.ULOG_CHANNEL, text=f"Error: {e}")
        print(f"Channel error: {e}")