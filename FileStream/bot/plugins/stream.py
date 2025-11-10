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
from pyrogram.errors import FloodWait, MessageDeleteForbidden
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

# ایمپورت وضعیت ربات از admin در پوشه plugins
from FileStream.bot.plugins.admin import is_bot_active

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
    # چک کردن وضعیت ربات - اگر خاموش است و کاربر عادی است
    if not is_bot_active() and message.from_user.id != Telegram.OWNER_ID:
        await message.reply_text("❌ ربات در حال حاضر غیرفعال است. لطفاً بعداً تلاش کنید.")
        return

    # اگر کاربر ادمین نیست، باید verify_user را چک کنیم
    if message.from_user.id != Telegram.OWNER_ID:
        if not await is_user_authorized(message):
            return
        if await is_user_banned(message):
            return

        await is_user_exist(bot, message)
        if Telegram.FORCE_SUB:
            if not await is_user_joined(bot, message):
                return

    file_unique_id = get_file_info(message)['file_unique_id']

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

# بقیه کدهای stream.py بدون تغییر...