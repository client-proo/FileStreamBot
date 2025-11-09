import os
import time
import asyncio
import logging
import datetime
import pytz
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram, Server
from pyrogram import filters, Client
from pyrogram.enums.parse_mode import ParseMode

logger = logging.getLogger(__name__)
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
tehran_tz = pytz.timezone('Asia/Tehran')

# ==================== توابع کمکی ====================

def get_tehran_time():
    return datetime.datetime.now(tehran_tz)

def get_jalali_datetime():
    try:
        import jdatetime
        tehran_time = get_tehran_time()
        jalali_date = jdatetime.datetime.fromgregorian(datetime=tehran_time)
        return jalali_date.strftime('%Y/%m/%d - %H:%M:%S')
    except ImportError:
        return get_tehran_time().strftime('%Y-%m-%d %H:%M:%S')

def get_readable_time(seconds: int) -> str:
    result = ''
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        result += f'{int(days)} روز '
    if hours > 0:
        result += f'{int(hours)} ساعت '
    if minutes > 0:
        result += f'{int(minutes)} دقیقه '
    if seconds > 0 or not result:
        result += f'{int(seconds)} ثانیه'
    
    return result.strip()

# ==================== پنل مدیریت اصلی ====================

@FileStream.on_message(filters.command("admin") & filters.private & filters.user(Telegram.OWNER_ID))
async def admin_panel(c: Client, m: Message):
    total_users = await db.total_users_count()
    total_files = await db.total_files()
    banned_users = await db.total_banned_users_count()

    text = f"""**🛠️ پنل مدیریت ربات**

📊 **آمار کلی:**
├ 👥 کاربران: `{total_users}`
├ 📁 فایل‌ها: `{total_files}`
├ 🚫 مسدود شده: `{banned_users}`
└ 🕒 زمان: `{get_jalali_datetime()}`

**لطفاً یکی از گزینه‌ها را انتخاب کنید:**"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار کامل", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("📢 ارسال همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔍 اطلاعات کاربر", callback_data="admin_userinfo")],
        [InlineKeyboardButton("🗑️ حذف فایل", callback_data="admin_delfile")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_refresh")]
    ])

    await m.reply_text(text, reply_markup=keyboard, quote=True)

# ==================== دستورات اصلی ====================

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def status_command(c: Client, m: Message):
    total_users = await db.total_users_count()
    banned_users = await db.total_banned_users_count()
    total_files = await db.total_files()
    
    text = f"""**📊 وضعیت ربات:**

👥 کاربران کل: `{total_users}`
🚫 کاربران مسدود: `{banned_users}`
🔗 فایل‌های فعال: `{total_files}`
🕒 زمان: `{get_jalali_datetime()}`"""

    await m.reply_text(text, quote=True)

@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
async def ban_command(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("❌ لطفاً آیدی کاربر را وارد کنید:\n`/ban user_id`", quote=True)
        return
    
    user_id = m.command[1]
    
    try:
        user_id = int(user_id)
        if await db.is_user_banned(user_id):
            await m.reply_text(f"✅ کاربر `{user_id}` قبلاً مسدود شده است.", quote=True)
            return
        
        await db.ban_user(user_id)
        await m.reply_text(f"✅ کاربر `{user_id}` با موفقیت مسدود شد.", quote=True)
        
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد.", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}", quote=True)

@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
async def unban_command(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("❌ لطفاً آیدی کاربر را وارد کنید:\n`/unban user_id`", quote=True)
        return
    
    user_id = m.command[1]
    
    try:
        user_id = int(user_id)
        if not await db.is_user_banned(user_id):
            await m.reply_text(f"✅ کاربر `{user_id}` مسدود نیست.", quote=True)
            return
        
        await db.unban_user(user_id)
        await m.reply_text(f"✅ مسدودیت کاربر `{user_id}` برداشته شد.", quote=True)
        
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد.", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}", quote=True)

@FileStream.on_message(filters.command("userinfo") & filters.private & filters.user(Telegram.OWNER_ID))
async def userinfo_command(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("❌ لطفاً آیدی کاربر را وارد کنید:\n`/userinfo user_id`", quote=True)
        return
    
    user_id = m.command[1]
    
    try:
        user_id = int(user_id)
        user = await db.get_user(user_id)
        
        if not user:
            await m.reply_text(f"❌ کاربر با آیدی `{user_id}` پیدا نشد.", quote=True)
            return
        
        username = user.get('username', 'ندارد')
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')
        join_date = user.get('join_date', 0)
        links_count = user.get('Links', 0)
        is_banned = await db.is_user_banned(user_id)
        
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = "نامشخص"
        
        join_date_str = datetime.datetime.fromtimestamp(join_date).strftime('%Y-%m-%d %H:%M:%S') if join_date else "نامشخص"
        status = "🚫 مسدود" if is_banned else "✅ فعال"
        
        text = f"""**👤 اطلاعات کاربر:**

🆔 آیدی: `{user_id}`
👤 نام: `{full_name}`
📧 یوزرنیم: `{username}`
📊 تعداد فایل‌ها: `{links_count}`
📅 تاریخ عضویت: `{join_date_str}`
🎯 وضعیت: {status}"""

        await m.reply_text(text, quote=True)
        
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد.", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}", quote=True)

@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def delete_file_command(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("❌ لطفاً آیدی فایل را وارد کنید:\n`/del file_id`", quote=True)
        return
    
    file_id = m.command[1]
    
    try:
        file_info = await db.get_file(file_id)
    except FIleNotFound:
        await m.reply_text("❌ فایل پیدا نشد یا قبلاً حذف شده است.", quote=True)
        return
    
    try:
        await db.delete_one_file(file_info['_id'])
        await db.count_links(file_info['user_id'], "-")
        await m.reply_text("✅ فایل با موفقیت حذف شد.", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا در حذف فایل: {e}", quote=True)

@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID) & filters.reply)
async def broadcast_handler(c: Client, m: Message):
    if not m.reply_to_message:
        await m.reply_text("❌ لطفاً به پیامی که می‌خواهید ارسال کنید ریپلای کنید.", quote=True)
        return

    all_users = await db.get_all_users()
    broadcast_msg = m.reply_to_message
    total_users = await db.total_users_count()

    if total_users == 0:
        await m.reply_text("❌ هیچ کاربری در دیتابیس وجود ندارد.", quote=True)
        return

    progress_msg = await m.reply_text("🔄 شروع ارسال همگانی...", quote=True)

    start_time = time.time()
    done = 0
    failed = 0
    success = 0

    async for user in all_users:
        try:
            user_id = int(user['id'])
            await asyncio.sleep(0.1)
            status, error_msg = await send_msg(user_id=user_id, message=broadcast_msg)

            if status == 200:
                success += 1
            else:
                failed += 1
                if status == 400:
                    await db.delete_user(user_id)

            done += 1

            if done % 10 == 0:
                await progress_msg.edit_text(f"📤 ارسال شده: {done}/{total_users}\n✅ موفق: {success}\n❌ ناموفق: {failed}")

        except Exception as e:
            failed += 1
            continue

    total_time = get_readable_time(int(time.time() - start_time))
    await progress_msg.delete()

    final_report = f"""✅ **ارسال همگانی تکمیل شد!**

👥 کاربران کل: {total_users}
📤 ارسال شده: {done}
✅ موفق: {success}
❌ ناموفق: {failed}
⏱️ زمان کل: {total_time}
🗓️ تاریخ: {get_jalali_datetime()}"""

    await m.reply_text(final_report, quote=True)

# ==================== هندلرهای کال‌بک ====================

@FileStream.on_callback_query(filters.regex(r"^admin_"))
async def admin_callback_handler(c: Client, query: CallbackQuery):
    data = query.data
    
    if data == "admin_stats":
        await show_complete_stats(query)
    
    elif data == "admin_users":
        await show_users_management(query)
    
    elif data == "admin_broadcast":
        await broadcast_guide(query)
    
    elif data == "admin_userinfo":
        await userinfo_guide(query)
    
    elif data == "admin_delfile":
        await delfile_guide(query)
    
    elif data == "admin_refresh":
        await admin_panel(c, query.message)
        await query.answer("✅ پنل بروزرسانی شد")

async def show_complete_stats(query: CallbackQuery):
    total_users = await db.total_users_count()
    total_files = await db.total_files()
    banned_users = await db.total_banned_users_count()
    active_users = total_users - banned_users
    
    all_users = await db.get_all_users()
    today = time.time() - 86400
    today_users = 0
    total_links = 0
    
    async for user in all_users:
        if user.get('join_date', 0) > today:
            today_users += 1
        total_links += user.get('Links', 0)

    text = f"""**📊 آمار کامل ربات**

👥 **کاربران:**
├ کل کاربران: `{total_users}`
├ کاربران فعال: `{active_users}`
├ کاربران امروز: `{today_users}`
└ کاربران مسدود: `{banned_users}`

📁 **فایل‌ها:**
├ کل فایل‌ها: `{total_files}`
└ کل لینک‌ها: `{total_links}`

🕒 **زمان:** `{get_jalali_datetime()}`"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

async def show_users_management(query: CallbackQuery):
    text = """**👥 مدیریت کاربران**

برای مدیریت کاربران از دستورات زیر استفاده کنید:

🚫 **مسدود کردن کاربر:**
`/ban user_id`

✅ **رفع مسدودیت:**
`/unban user_id`

🔍 **اطلاعات کاربر:**
`/userinfo user_id`"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

async def broadcast_guide(query: CallbackQuery):
    text = """**📢 ارسال پیام همگانی**

1. پیام خود را بنویسید
2. روی آن ریپلای کنید  
3. از دستور زیر استفاده کنید: