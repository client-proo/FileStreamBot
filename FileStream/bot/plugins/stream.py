import time
import asyncio
import logging
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

# تنظیم لاگ‌گیری
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    """
    هندلر دریافت فایل از چت خصوصی
    """
    try:
        # بررسی مجوز کاربر
        if not await is_user_authorized(message):
            logger.warning(f"User {message.from_user.id} is not authorized")
            return
        
        # بررسی مسدود بودن کاربر
        if await is_user_banned(message):
            logger.warning(f"User {message.from_user.id} is banned")
            return

        # افزودن کاربر به دیتابیس اگر وجود ندارد
        await is_user_exist(bot, message)
        
        # بررسی عضویت در کانال اجباری
        if Telegram.FORCE_SUB:
            if not await is_user_joined(bot, message):
                logger.warning(f"User {message.from_user.id} is not joined in force sub channel")
                return

        # دریافت اطلاعات فایل
        file_info = get_file_info(message)
        file_unique_id = file_info['file_unique_id']

        # چک ضد تکرار
        is_repeat, remaining_repeat = await db.check_repeat(message.from_user.id, file_unique_id)
        if is_repeat:
            remaining_readable = seconds_to_hms(remaining_repeat)
            logger.info(f"Repeat file detected for user {message.from_user.id}, remaining: {remaining_readable}")
            await message.reply_text(
                f"🔄 این فایل هنوز معتبر است!\n\nلینک قبلی تا **{remaining_readable}** دیگر فعال است.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        # چک ضد اسپم
        remaining_spam, is_spam = await db.check_spam(message.from_user.id)
        if is_spam:
            remaining_readable = seconds_to_hms(int(remaining_spam))
            logger.info(f"Spam detected for user {message.from_user.id}, wait: {remaining_readable}")
            await message.reply_text(
                f"⏳ لطفاً کمی صبر کنید!\n\nمی‌توانید بعد از **{remaining_readable}** دوباره امتحان کنید.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        reply_msg = None
        inserted_id = None

        try:
            # --- 1. اضافه کردن فایل به دیتابیس ---
            inserted_id = await db.add_file(file_info)
            logger.info(f"File added to DB with ID: {inserted_id} for user {message.from_user.id}")
            
            # دریافت file_ids برای کلاینت‌های مختلف
            await get_file_ids(False, inserted_id, multi_clients, message)

            # --- 2. ساخت لینک ---
            reply_markup, stream_text = await gen_link(_id=inserted_id)
            if reply_markup is None:
                await message.reply_text("❌ خطا در تولید لینک!")
                return

            # --- 3. ارسال پیام لینک ---
            reply_msg = await message.reply_text(
                text=stream_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
                quote=True
            )

            logger.info(f"Link sent for file {inserted_id} to user {message.from_user.id}")

            # --- 4. زمان‌بندی حذف خودکار ---
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
            logger.warning(f"FloodWait for {e.value}s for user {message.from_user.id}")
            await asyncio.sleep(e.value)
            # تلاش مجدد پس از FloodWait
            if inserted_id:
                try:
                    reply_markup, stream_text = await gen_link(_id=inserted_id)
                    if reply_markup:
                        reply_msg = await message.reply_text(
                            text=stream_text,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                            reply_markup=reply_markup,
                            quote=True
                        )
                except Exception as retry_error:
                    logger.error(f"Retry failed after FloodWait: {retry_error}")

        except Exception as e:
            logger.error(f"Error processing file for user {message.from_user.id}: {e}")
            await message.reply_text(
                "❌ خطایی در پردازش فایل رخ داد! لطفاً دوباره تلاش کنید.",
                quote=True
            )

            # پاک کردن فایل ناقص از دیتابیس
            if inserted_id:
                try:
                    await db.delete_one_file(inserted_id)
                    logger.info(f"Cleaned up incomplete file {inserted_id}")
                except Exception as cleanup_error:
                    logger.error(f"Cleanup failed for file {inserted_id}: {cleanup_error}")

    except Exception as e:
        logger.error(f"Unexpected error in private_receive_handler: {e}")
        await message.reply_text(
            "❌ خطای غیرمنتظره‌ای رخ داد! لطفاً بعداً تلاش کنید.",
            quote=True
        )


# ====================== AUTO DELETE + DB CLEANUP + EXPIRED MESSAGE ======================
async def delete_after_expire(reply_msg: Message, original_msg: Message, user_id: int, file_id: int, delay: float):
    """
    حذف خودکار لینک و فایل پس از انقضا
    """
    try:
        logger.info(f"Scheduled deletion for file {file_id} in {delay} seconds")
        
        # انتظار برای زمان انقضا
        await asyncio.sleep(delay)

        # --- 1. حذف پیام لینک ---
        try:
            await reply_msg.delete()
            logger.info(f"Link message deleted: {reply_msg.id} for file {file_id}")
        except MessageDeleteForbidden:
            logger.warning(f"Cannot delete link message (forbidden): {reply_msg.id}")
        except Exception as e:
            logger.error(f"Error deleting link message {reply_msg.id}: {e}")

        # --- 2. پاک کردن فایل از دیتابیس ---
        try:
            await db.delete_one_file(file_id)
            await db.count_links(user_id, "-")
            logger.info(f"File {file_id} expired and deleted from DB")
        except Exception as e:
            logger.error(f"Error deleting expired file {file_id} from DB: {e}")

        # --- 3. ارسال پیام منقضی شده ---
        try:
            if original_msg and original_msg.id:
                await original_msg.reply_text(
                    "⏰ لینک شما منقضی شد!\n\nبرای آپلود مجدد فایل، آن را دوباره ارسال کنید.",
                    quote=True
                )
                logger.info(f"Expiration message sent to user {user_id} for file {file_id}")
        except Exception as e:
            logger.error(f"Could not send expiration message to user {user_id}: {e}")
            # تلاش جایگزین برای ارسال پیام
            try:
                await FileStream.send_message(
                    chat_id=user_id,
                    text="⏰ لینک شما منقضی شد!\n\nبرای آپلود مجدد فایل، آن را دوباره ارسال کنید."
                )
            except Exception:
                logger.error(f"Failed to send alternative expiration message to user {user_id}")

    except Exception as e:
        logger.error(f"Error in delete_after_expire for file {file_id}: {e}")


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
    """
    هندلر دریافت فایل از کانال
    """
    try:
        # بررسی مسدود بودن کانال
        if await is_channel_banned(bot, message):
            logger.warning(f"Channel {message.chat.id} is banned")
            return
        
        # افزودن کانال به دیتابیس اگر وجود ندارد
        await is_channel_exist(bot, message)

        # دریافت اطلاعات فایل
        file_info = get_file_info(message)
        file_unique_id = file_info['file_unique_id']

        # چک ضد تکرار برای کانال
        is_repeat, _ = await db.check_repeat(message.chat.id, file_unique_id)
        if is_repeat:
            logger.info(f"Repeat file detected in channel {message.chat.id}")
            return

        inserted_id = None
        
        try:
            # افزودن فایل به دیتابیس
            inserted_id = await db.add_file(file_info)
            await get_file_ids(False, inserted_id, multi_clients, message)
            
            # تولید لینک
            reply_markup, _ = await gen_link(_id=inserted_id)
            
            logger.info(f"File added from channel {message.chat.id} with ID: {inserted_id}")

            # افزودن دکمه دانلود به پیام کانال
            try:
                await bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=message.id,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "📥 دریافت فایل", 
                                url=f"https://t.me/{FileStream.username}?start=stream_{inserted_id}"
                            )
                        ]
                    ])
                )
                logger.info(f"Added download button to message {message.id} in channel {message.chat.id}")
                
            except Exception as edit_error:
                # اگر ویرایش پیام ممکن نبود، پیام جدید ارسال کن
                logger.warning(f"Could not edit message in channel {message.chat.id}: {edit_error}")
                await bot.send_message(
                    chat_id=message.chat.id,
                    text="📥 لینک دریافت فایل:",
                    reply_to_message_id=message.id,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "دانلود فایل", 
                                url=f"https://t.me/{FileStream.username}?start=stream_{inserted_id}"
                            )
                        ]
                    ])
                )

        except FloodWait as w:
            logger.warning(f"FloodWait in channel {message.chat.id} for {w.value}s")
            await asyncio.sleep(w.value)
            
            # گزارش به کانال لاگ
            try:
                await bot.send_message(
                    chat_id=Telegram.ULOG_CHANNEL, 
                    text=f"⏳ FloodWait {w.value}s in channel {message.chat.title}"
                )
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Error processing file from channel {message.chat.id}: {e}")
            
            # گزارش خطا به کانال لاگ
            try:
                await bot.send_message(
                    chat_id=Telegram.ULOG_CHANNEL,
                    text=f"❌ Error in channel {message.chat.title} ({message.chat.id}): {str(e)}"
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Unexpected error in channel_receive_handler: {e}")


# ====================== FILE VALIDATION ======================
def validate_file_size(file_size: int) -> bool:
    """
    اعتبارسنجی حجم فایل
    """
    max_size = getattr(Telegram, 'MAX_FILE_SIZE', 2 * 1024 * 1024 * 1024)  # پیش‌فرض 2GB
    return file_size <= max_size


def validate_file_type(mime_type: str) -> bool:
    """
    اعتبارسنجی نوع فایل
    """
    blocked_types = getattr(Telegram, 'BLOCKED_MIME_TYPES', [
        'application/x-msdownload',
        'application/x-dosexec',
        'application/x-executable'
    ])
    return mime_type not in blocked_types


# ====================== CLEANUP TASK ======================
async def periodic_cleanup():
    """
    پاکسازی دوره‌ای فایل‌های منقضی
    """
    while True:
        try:
            await asyncio.sleep(1800)  # هر 30 دقیقه
            await db.cleanup_expired_files()
            logger.info("Periodic cleanup completed")
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
            await asyncio.sleep(300)  # در صورت خطا، 5 دقیقه صبر کن


# شروع تسک پاکسازی دوره‌ای
asyncio.create_task(periodic_cleanup())


# ====================== BROADCAST HANDLER ======================
@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID))
async def broadcast_handler(bot: Client, message: Message):
    """
    هندلر ارسال پیام همگانی (برای ادمین)
    """
    try:
        if not message.reply_to_message:
            await message.reply_text("❌ لطفاً به پیامی که می‌خواهید ارسال کنید، ریپلای کنید.")
            return

        from FileStream.utils.broadcast_helper import send_msg
        
        all_users = await db.get_all_users()
        broadcast_msg = message.reply_to_message
        
        # ایجاد ID یکتا برای broadcast
        import string
        import random
        broadcast_id = ''.join(random.choices(string.ascii_letters, k=6))
        
        progress_msg = await message.reply_text("🔄 شروع ارسال همگانی...")
        
        total_users = await db.total_users_count()
        done = 0
        failed = 0
        success = 0
        
        async for user in all_users:
            try:
                sts, msg = await send_msg(user_id=int(user['id']), message=broadcast_msg)
                
                if sts == 200:
                    success += 1
                else:
                    failed += 1
                    if sts == 400:  # کاربر غیرفعال
                        await db.delete_user(user['id'])
                
                done += 1
                
                # آپدیت پیشرفت هر 10 کاربر
                if done % 10 == 0:
                    try:
                        await progress_msg.edit_text(
                            f"📤 ارسال همگانی در حال انجام...\n\n"
                            f"✅ ارسال شده: {done}/{total_users}\n"
                            f"✔️ موفق: {success}\n"
                            f"❌ ناموفق: {failed}"
                        )
                    except Exception:
                        pass
                        
            except Exception as e:
                failed += 1
                logger.error(f"Error sending broadcast to user {user['id']}: {e}")
        
        # گزارش نهایی
        await progress_msg.delete()
        await message.reply_text(
            f"✅ ارسال همگانی تکمیل شد!\n\n"
            f"👥 کل کاربران: {total_users}\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {failed}"
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast handler: {e}")
        await message.reply_text("❌ خطا در ارسال همگانی!")


logger.info("Stream handlers initialized successfully")