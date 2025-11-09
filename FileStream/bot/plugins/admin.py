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
async def broadcast_handler(c: Client, m: Message):
    """
    هندلر ارسال پیام همگانی - نسخه کاملاً اصلاح شده
    """
    try:
        # بررسی ریپلای
        if not m.reply_to_message:
            await m.reply_text(
                "❌ لطفاً به پیامی که می‌خواهید ارسال کنید ریپلای کنید.",
                quote=True
            )
            return

        # دریافت تمام کاربران
        all_users = await db.get_all_users()
        broadcast_msg = m.reply_to_message
        total_users = await db.total_users_count()
        
        if total_users == 0:
            await m.reply_text("❌ هیچ کاربری در دیتابیس وجود ندارد.", quote=True)
            return

        # تولید ID یکتا برای broadcast
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(8)])
        
        # پیام شروع
        progress_msg = await m.reply_text(
            "🔄 **در حال شروع ارسال همگانی...**\n\n"
            f"👥 کاربران: {total_users}\n"
            "⏳ در حال آماده‌سازی...",
            quote=True
        )

        start_time = time.time()
        done = 0
        failed = 0
        success = 0
        
        # فایل لاگ
        log_filename = f'broadcast_{broadcast_id}.txt'
        
        async with aiofiles.open(log_filename, 'w', encoding='utf-8') as log_file:
            await log_file.write(f"Broadcast Log - {datetime.datetime.now()}\n")
            await log_file.write(f"Total Users: {total_users}\n")
            await log_file.write("=" * 50 + "\n\n")
            
            # ارسال به کاربران
            async for user in all_users:
                try:
                    user_id = int(user['id'])
                    
                    # تاخیر برای جلوگیری از FloodWait (افزایش به 200ms)
                    if done > 0:  # فقط بعد از کاربر اول تاخیر داشته باش
                        await asyncio.sleep(0.2)
                    
                    # ارسال پیام
                    status, error_msg = await send_msg(user_id=user_id, message=broadcast_msg)
                    
                    # بررسی نتیجه ارسال
                    if status == 200:
                        success += 1
                        print(f"✅ ارسال شد به {user_id}")
                    else:
                        failed += 1
                        if error_msg:
                            await log_file.write(error_msg)
                        print(f"❌ خطا برای {user_id}: {error_msg}")
                        
                        # حذف کاربر اگر غیرفعال است
                        if status == 400:
                            try:
                                await db.delete_user(user_id)
                                await log_file.write(f"{user_id} : حذف شد از دیتابیس\n")
                            except Exception as delete_error:
                                await log_file.write(f"{user_id} : خطا در حذف: {delete_error}\n")
                    
                    done += 1
                    
                    # بروزرسانی پیشرفت هر 5 کاربر
                    if done % 5 == 0 or done == total_users:
                        elapsed = time.time() - start_time
                        progress_text = await generate_progress_text(done, total_users, success, failed, elapsed)
                        
                        try:
                            await progress_msg.edit_text(progress_text)
                        except Exception as edit_error:
                            print(f"خطا در بروزرسانی پیشرفت: {edit_error}")
                            
                except Exception as e:
                    failed += 1
                    error_text = f"{user.get('id', 'Unknown')} : خطای عمومی: {str(e)}\n"
                    await log_file.write(error_text)
                    print(f"خطای عمومی برای کاربر: {e}")
                    continue

        # محاسبه زمان کل
        total_time = datetime.timedelta(seconds=int(time.time() - start_time))
        
        # گزارش نهایی
        final_report = await generate_final_report(total_users, done, success, failed, total_time)
        
        # حذف پیام پیشرفت
        try:
            await progress_msg.delete()
        except Exception:
            pass

        # ارسال گزارش نهایی
        if failed == 0:
            await m.reply_text(final_report, quote=True)
            # حذف فایل لاگ اگر خطایی نبود
            try:
                os.remove(log_filename)
            except Exception:
                pass
        else:
            await m.reply_document(
                document=log_filename,
                caption=final_report,
                quote=True
            )
            # حذف فایل لاگ پس از 30 ثانیه
            await asyncio.sleep(30)
            try:
                os.remove(log_filename)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"خطای کلی در broadcast: {e}")
        await m.reply_text(
            f"❌ **خطای سیستمی در ارسال همگانی:**\n`{str(e)}`",
            quote=True
        )


async def generate_progress_text(done, total, success, failed, elapsed_time):
    """تولید متن پیشرفت"""
    progress_percent = (done / total) * 100
    elapsed_str = str(datetime.timedelta(seconds=int(elapsed_time)))
    speed = done / elapsed_time if elapsed_time > 0 else 0
    
    return f"""🔄 **در حال ارسال همگانی...**

📊 **پیشرفت:** {done}/{total} ({progress_percent:.1f}%)
✅ **موفق:** {success}
❌ **ناموفق:** {failed}
⏱️ **زمان:** {elapsed_str}
🚀 **سرعت:** {speed:.1f} کاربر/ثانیه

لطفاً شکیبا باشید..."""


async def generate_final_report(total_users, done, success, failed, total_time):
    """تولید گزارش نهایی"""
    success_rate = (success / total_users) * 100 if total_users > 0 else 0
    
    return f"""✅ **ارسال همگانی تکمیل شد!**

📈 **گزارش نهایی:**
├ 👥 کاربران کل: {total_users}
├ 📤 ارسال شده: {done}
├ ✅ موفق: {success}
├ ❌ ناموفق: {failed}
├ ⏱️ زمان کل: {total_time}
└ 📊 نرخ موفقیت: {success_rate:.1f}%

{"🎉 ارسال با موفقیت کامل شد!" if failed == 0 else "⚠️ برخی پیام‌ها ارسال نشدند. فایل لاگ ضمیمه شده است."}"""


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


# دستور تست broadcast
@FileStream.on_message(filters.command("test_broadcast") & filters.private & filters.user(Telegram.OWNER_ID))
async def test_broadcast(c: Client, m: Message):
    """تست ارسال همگانی با پیام تست"""
    try:
        # ایجاد پیام تست
        test_message = await m.reply_text(
            "🧪 **این یک پیام تست برای broadcast است**\n\n"
            "تاریخ: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            quote=True
        )
        
        # استفاده از هندلر broadcast اصلی
        m.reply_to_message = test_message
        await broadcast_handler(c, m)
        
    except Exception as e:
        await m.reply_text(f"❌ خطا در تست: {e}", quote=True)


# دستور مشاهده آمار کاربران
@FileStream.on_message(filters.command("user_stats") & filters.private & filters.user(Telegram.OWNER_ID))
async def user_stats(c: Client, m: Message):
    """نمایش آمار دقیق کاربران"""
    try:
        total_users = await db.total_users_count()
        banned_users = await db.total_banned_users_count()
        active_users = total_users - banned_users
        
        # نمونه‌گیری از کاربران اخیر
        recent_users = []
        all_users = await db.get_all_users()
        count = 0
        async for user in all_users:
            if count < 5:  # فقط 5 کاربر آخر
                recent_users.append(user)
                count += 1
            else:
                break
        
        stats_text = f"""📊 **آمار دقیق کاربران**

👥 **کاربران کل:** `{total_users}`
✅ **کاربران فعال:** `{active_users}`
🚫 **کاربران مسدود:** `{banned_users}`

**کاربران اخیر:**
"""
        
        for user in recent_users:
            user_id = user['id']
            join_date = datetime.datetime.fromtimestamp(user.get('join_date', time.time()))
            stats_text += f"├ 👤 `{user_id}` - {join_date.strftime('%Y-%m-%d')}\n"
        
        stats_text += f"\n📈 **برای تست broadcast از دستور /test_broadcast استفاده کنید**"
        
        await m.reply_text(stats_text, quote=True)
        
    except Exception as e:
        await m.reply_text(f"❌ خطا در دریافت آمار: {e}", quote=True)