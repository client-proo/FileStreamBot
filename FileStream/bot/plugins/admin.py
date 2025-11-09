import os
import time
import string
import random
import asyncio
import aiofiles
import datetime
import logging

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram, Server
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

# تنظیم لاگ‌گیری
logger = logging.getLogger(__name__)

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    await m.reply_text(text=f"""**👥 کل کاربران:** `{await db.total_users_count()}`
**🚫 کاربران مسدود شده:** `{await db.total_banned_users_count()}`
**🔗 لینک‌های تولید شده: ** `{await db.total_files()}`"""
                       , parse_mode=ParseMode.MARKDOWN, quote=True)


@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(b, m: Message):
    id = m.text.split("/ban ")[-1]
    if not await db.is_user_banned(int(id)):
        try:
            await db.ban_user(int(id))
            await db.delete_user(int(id))
            await m.reply_text(text=f"`{id}`** مسدود شده است** ", parse_mode=ParseMode.MARKDOWN, quote=True)
            if not str(id).startswith('-100'):
                await b.send_message(
                    chat_id=id,
                    text="**حساب کاربری شما مسدود شده است**",
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
        except Exception as e:
            await m.reply_text(text=f"**عملیات با خطا مواجه شد: {e}** ", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{id}`** قبلاً مسدود شده است** ", parse_mode=ParseMode.MARKDOWN, quote=True)


@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(b, m: Message):
    id = m.text.split("/unban ")[-1]
    if await db.is_user_banned(int(id)):
        try:
            await db.unban_user(int(id))
            await m.reply_text(text=f"`{id}`** مسدودیت با موفقیت برداشته شد** ", parse_mode=ParseMode.MARKDOWN, quote=True)
            if not str(id).startswith('-100'):
                await b.send_message(
                    chat_id=id,
                    text="**مسدودیت شما برداشته شد. می‌توانید از ربات استفاده کنید**",
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
        except Exception as e:
            await m.reply_text(text=f"** عملیات با خطا مواجه شد: {e}**", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{id}`** مسدود نشده است** ", parse_mode=ParseMode.MARKDOWN, quote=True)


@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID) & filters.reply)
async def broadcast_handler(c, m: Message):
    """
    هندلر ارسال پیام همگانی - نسخه بهبود یافته
    """
    try:
        # بررسی اینکه پیام ریپلای شده است
        if not m.reply_to_message:
            await m.reply_text(
                "❌ لطفاً به پیامی که می‌خواهید برای همه کاربران ارسال کنید، ریپلای کنید.",
                quote=True
            )
            return

        # دریافت تمام کاربران
        all_users = await db.get_all_users()
        broadcast_msg = m.reply_to_message
        
        # تولید ID یکتا برای broadcast
        while True:
            broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(6)])
            if not broadcast_ids.get(broadcast_id):
                break

        # پیام شروع
        out = await m.reply_text(
            text="🔄 **شروع ارسال همگانی...**\n\nدر حال آماده‌سازی...",
            quote=True
        )

        start_time = time.time()
        total_users = await db.total_users_count()
        done = 0
        failed = 0
        success = 0
        
        # ذخیره اطلاعات broadcast
        broadcast_ids[broadcast_id] = {
            'total': total_users,
            'current': done,
            'failed': failed,
            'success': success,
            'start_time': start_time
        }

        # فایل لاگ
        log_filename = f'broadcast_{broadcast_id}.txt'
        
        async with aiofiles.open(log_filename, 'w', encoding='utf-8') as broadcast_log_file:
            await broadcast_log_file.write(f"Broadcast Log - {datetime.datetime.now()}\n")
            await broadcast_log_file.write(f"Total Users: {total_users}\n")
            await broadcast_log_file.write("=" * 50 + "\n")
            
            # ارسال به کاربران
            async for user in all_users:
                try:
                    user_id = int(user['id'])
                    
                    # ارسال پیام با تاخیر برای جلوگیری از FloodWait
                    await asyncio.sleep(0.1)  # تاخیر 100ms بین ارسال‌ها
                    
                    sts, msg = await send_msg(user_id=user_id, message=broadcast_msg)
                    
                    # نوشتن در لاگ اگر خطایی وجود دارد
                    if msg is not None:
                        await broadcast_log_file.write(msg)
                    
                    # بررسی وضعیت ارسال
                    if sts == 200:
                        success += 1
                    else:
                        failed += 1
                        # حذف کاربر اگر غیرفعال است
                        if sts == 400:
                            await db.delete_user(user_id)
                    
                    done += 1
                    
                    # بروزرسانی آمار هر 10 کاربر
                    if done % 10 == 0:
                        elapsed_time = time.time() - start_time
                        progress_msg = await generate_progress_message(done, total_users, success, failed, elapsed_time)
                        
                        try:
                            await out.edit_text(progress_msg)
                        except Exception as e:
                            logger.error(f"Error updating progress: {e}")
                    
                    # بررسی لغو broadcast
                    if broadcast_ids.get(broadcast_id) is None:
                        break
                        
                except Exception as e:
                    failed += 1
                    error_msg = f"{user['id']} : خطای غیرمنتظره: {str(e)}\n"
                    await broadcast_log_file.write(error_msg)
                    logger.error(f"Error in broadcast for user {user['id']}: {e}")

        # محاسبه زمان کل
        completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
        
        # حذف از لیست broadcastهای فعال
        if broadcast_ids.get(broadcast_id):
            broadcast_ids.pop(broadcast_id)

        # حذف پیام پیشرفت
        await asyncio.sleep(2)
        try:
            await out.delete()
        except Exception:
            pass

        # گزارش نهایی
        final_message = await generate_final_message(total_users, done, success, failed, completed_in)
        
        if failed == 0:
            await m.reply_text(
                text=final_message,
                quote=True
            )
            # حذف فایل لاگ اگر خطایی نبوده
            try:
                os.remove(log_filename)
            except Exception:
                pass
        else:
            await m.reply_document(
                document=log_filename,
                caption=final_message,
                quote=True
            )
            # حذف فایل لاگ پس از ارسال
            try:
                os.remove(log_filename)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error in broadcast handler: {e}")
        await m.reply_text(
            text=f"❌ **خطا در ارسال همگانی:**\n`{str(e)}`",
            quote=True
        )


async def generate_progress_message(done, total, success, failed, elapsed_time):
    """تولید پیام پیشرفت"""
    progress = (done / total) * 100
    elapsed_str = str(datetime.timedelta(seconds=int(elapsed_time)))
    
    return f"""🔄 **در حال ارسال همگانی...**

📊 **پیشرفت:** `{done}/{total}` ({progress:.1f}%)
✅ **موفق:** `{success}`
❌ **ناموفق:** `{failed}`
⏱️ **زمان سپری شده:** `{elapsed_str}`

لطفاً منتظر بمانید..."""


async def generate_final_message(total_users, done, success, failed, completed_in):
    """تولید پیام نهایی"""
    return f"""✅ **ارسال همگانی تکمیل شد!**

👥 **کل کاربران:** `{total_users}`
📤 **ارسال شده:** `{done}`
✅ **موفق:** `{success}`
❌ **ناموفق:** `{failed}`
⏱️ **زمان کل:** `{completed_in}`

🎉 **نرخ موفقیت:** `{(success/total_users)*100:.1f}%`"""


@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    file_id = m.text.split(" ")[-1]
    try:
        file_info = await db.get_file(file_id)
    except FIleNotFound:
        await m.reply_text(
            text=f"**فایل قبلاً حذف شده است**",
            quote=True
        )
        return
    await db.delete_one_file(file_info['_id'])
    await db.count_links(file_info['user_id'], "-")
    await m.reply_text(
        text=f"**فایل با موفقیت حذف شد !** ",
        quote=True
    )


# دستور برای لغو broadcast
@FileStream.on_message(filters.command("bcancel") & filters.private & filters.user(Telegram.OWNER_ID))
async def cancel_broadcast(c, m: Message):
    """لغو ارسال همگانی"""
    if not broadcast_ids:
        await m.reply_text("❌ هیچ ارسال همگانی فعالی وجود ندارد.", quote=True)
        return
    
    # حذف اولین broadcast فعال
    broadcast_id = next(iter(broadcast_ids.keys()))
    broadcast_ids.pop(broadcast_id)
    
    await m.reply_text("✅ ارسال همگانی لغو شد.", quote=True)