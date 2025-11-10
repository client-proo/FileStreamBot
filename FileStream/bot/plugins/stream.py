import time
import asyncio
import logging
import traceback
from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.bot_utils import gen_link
from FileStream.utils.file_properties import get_file_info
from FileStream.config import Telegram
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

logger = logging.getLogger(__name__)
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

@FileStream.on_message(
    filters.private & (
        filters.document | filters.video | filters.audio | filters.voice | filters.photo | filters.animation
    )
)
async def file_handler(client: Client, message: Message):
    try:
        logger.info(f"📨 Received file from user {message.from_user.id}")
        
        # بررسی نوع فایل
        if message.document:
            file_type = "document"
            file_name = message.document.file_name
            file_size = message.document.file_size
        elif message.video:
            file_type = "video"
            file_name = message.video.file_name or "video.mp4"
            file_size = message.video.file_size
        elif message.audio:
            file_type = "audio"
            file_name = message.audio.file_name or "audio.mp3"
            file_size = message.audio.file_size
        elif message.photo:
            file_type = "photo"
            file_name = "photo.jpg"
            file_size = 0  # برای عکس سایز دقیق نداریم
        else:
            file_type = "unknown"
            file_name = "file"
            file_size = 0

        logger.info(f"📄 File info - Type: {file_type}, Name: {file_name}, Size: {file_size}")

        # ذخیره در دیتابیس
        try:
            file_data = {
                "user_id": message.from_user.id,
                "file_name": file_name,
                "file_size": file_size,
                "file_id": getattr(message, file_type).file_id,
                "file_unique_id": getattr(message, file_type).file_unique_id,
                "mime_type": getattr(message, file_type).mime_type if hasattr(getattr(message, file_type), 'mime_type') else file_type,
                "time": time.time()
            }
            
            logger.info(f"💾 Saving file to database: {file_data}")
            inserted_id = await db.add_file(file_data)
            logger.info(f"✅ File saved with ID: {inserted_id}")
            
        except Exception as db_error:
            logger.error(f"❌ Database error: {db_error}")
            await message.reply_text("❌ خطا در ذخیره‌سازی فایل", quote=True)
            return

        # تولید لینک
        logger.info(f"🔗 Generating link for file ID: {inserted_id}")
        reply_markup, text = await gen_link(str(inserted_id))
        
        if reply_markup and text:
            logger.info("✅ Sending link to user")
            await message.reply_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
                quote=True
            )
        else:
            logger.error(f"❌ Link generation failed: {text}")
            await message.reply_text(
                f"❌ {text}\n\nلطفاً بعداً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
                quote=True
            )
            
    except Exception as e:
        logger.error(f"❌ Critical error in file_handler: {str(e)}")
        logger.error(traceback.format_exc())
        await message.reply_text(
            "❌ خطای سیستمی در پردازش فایل\nلطفاً بعداً دوباره تلاش کنید.",
            quote=True
        )