import time
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from FileStream.config import Telegram, Server
from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes

logger = logging.getLogger(__name__)
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

async def gen_link(_id):
    try:
        logger.info(f"🔗 Starting link generation for file ID: {_id}")
        
        # بررسی وجود _id
        if not _id:
            logger.error("❌ File ID is empty")
            return None, "❌ خطا: آیدی فایل نامعتبر است"
        
        # بررسی اتصال دیتابیس
        try:
            file_info = await db.get_file(_id)
            logger.info(f"📄 File info retrieved: {file_info}")
        except Exception as db_error:
            logger.error(f"❌ Database error: {db_error}")
            return None, "❌ خطا در ارتباط با دیتابیس"
        
        if not file_info:
            logger.error("❌ File not found in database")
            return None, "❌ فایل پیدا نشد"
        
        # بررسی اطلاعات ضروری فایل
        required_fields = ['file_name', 'file_size', 'time']
        for field in required_fields:
            if field not in file_info:
                logger.error(f"❌ Missing field: {field}")
                return None, f"❌ فیلد {field} در اطلاعات فایل وجود ندارد"
        
        create_time = file_info['time']
        expire_time = create_time + Telegram.EXPIRE_TIME
        remaining_seconds = int(expire_time - time.time())

        if remaining_seconds <= 0:
            logger.warning("⏰ Link expired")
            return None, "❌ لینک منقضی شده است"

        # تولید لینک‌ها
        try:
            page_link = f"{Server.URL}watch/{_id}"
            stream_link = f"{Server.URL}dl/{_id}"
            file_link = f"https://t.me/{FileStream.username}?start=file_{_id}"
            
            logger.info(f"🔗 Generated links - Page: {page_link}, Download: {stream_link}")
        except Exception as link_error:
            logger.error(f"❌ Link generation error: {link_error}")
            return None, "❌ خطا در تولید لینک‌ها"

        file_name = file_info['file_name']
        file_size = humanbytes(file_info['file_size'])
        mime_type = file_info.get('mime_type', 'unknown')

        # متن پیام
        if "video" in mime_type.lower():
            stream_text = f"""**📹 فایل ویدیویی**

**📄 نام فایل:** `{file_name}`
**📦 حجم فایل:** `{file_size}`
**⏰ زمان باقی‌مانده:** `{seconds_to_hms(remaining_seconds)}`

**🔗 لینک‌ها:**
🖥️ پخش آنلاین: `{page_link}`
📥 دانلود مستقیم: `{stream_link}`
📤 اشتراک‌گذاری: `{file_link}`"""
            
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ پخش آنلاین", url=page_link), 
                 InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📤 اشتراک‌گذاری", url=file_link)]
            ])
        else:
            stream_text = f"""**📄 فایل مدیا**

**📄 نام فایل:** `{file_name}`
**📦 حجم فایل:** `{file_size}`
**⏰ زمان باقی‌مانده:** `{seconds_to_hms(remaining_seconds)}`

**🔗 لینک‌ها:**
📥 دانلود مستقیم: `{stream_link}`
📤 اشتراک‌گذاری: `{file_link}`"""
            
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📤 اشتراک‌گذاری", url=file_link)]
            ])

        logger.info("✅ Link generated successfully")
        return reply_markup, stream_text

    except Exception as e:
        logger.error(f"❌ Critical error in gen_link: {str(e)}")
        logger.error(traceback.format_exc())
        return None, f"❌ خطای سیستمی: {str(e)}"

def seconds_to_hms(seconds: int) -> str:
    """تبدیل ثانیه به فرمت خوانا"""
    try:
        if seconds <= 0:
            return "0 ثانیه"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours} ساعت")
        if minutes > 0:
            parts.append(f"{minutes} دقیقه")
        if secs > 0:
            parts.append(f"{secs} ثانیه")

        return " و ".join(parts) if parts else "0 ثانیه"
    except Exception as e:
        logger.error(f"Error in seconds_to_hms: {e}")
        return "زمان نامعلوم"

async def verify_user(client, message):
    """بررسی کاربر"""
    try:
        # در اینجا می‌توانید شرایط خاص اضافه کنید
        return True
    except Exception as e:
        logger.error(f"Error in verify_user: {e