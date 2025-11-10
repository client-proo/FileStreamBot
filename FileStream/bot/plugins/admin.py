import os
import time
import string
import random
import asyncio
import aiofiles
import datetime
import logging
import pytz
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram, Server
from pyrogram import filters, Client
from pyrogram.enums.parse_mode import ParseMode

# تنظیم لاگ‌گیری
logger = logging.getLogger(__name__)

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# تنظیم منطقه زمانی تهران
tehran_tz = pytz.timezone('Asia/Tehran')

def get_tehran_time():
    """دریافت زمان فعلی تهران"""
    return datetime.datetime.now(tehran_tz)

def get_jalali_datetime():
    """دریافت تاریخ و زمان شمسی تهران"""
    try:
        import jdatetime
        tehran_time = get_tehran_time()
        jalali_date = jdatetime.datetime.fromgregorian(
            year=tehran_time.year,
            month=tehran_time.month,
            day=tehran_time.day,
            hour=tehran_time.hour,
            minute=tehran_time.minute,
            second=tehran_time.second
        )
        return jalali_date.strftime('%Y/%m/%d - %H:%M:%S')
    except ImportError:
        # اگر jdatetime نصب نبود، از تاریخ میلادی استفاده کن
        return get_tehran_time().strftime('%Y-%m-%d %H:%M:%S')

def convert_to_jalali(timestamp):
    """تبدیل timestamp به تاریخ شمسی تهران"""
    try:
        import jdatetime
        if not timestamp:
            return "نامشخص"
        
        gregorian_date = datetime.datetime.fromtimestamp(timestamp, tehran_tz)
        jalali_date = jdatetime.datetime.fromgregorian(datetime=gregorian_date)
        return jalali_date.strftime('%Y/%m/%d - %H:%M:%S')
    except ImportError:
        # اگر jdatetime نصب نبود، از تاریخ میلادی استفاده کن
        if timestamp:
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return "نامشخص"

def get_time_ago(timestamp: float) -> str:
    """تبدیل timestamp به زمان گذشته"""
    if not timestamp:
        return "نامشخص"
        
    now = time.time()
    diff = now - timestamp
    
    if diff < 60:
        return "همین الان"
    elif diff < 3600:
        return f"{int(diff // 60)} دقیقه قبل"
    elif diff < 86400:
        return f"{int(diff // 3600)} ساعت قبل"
    elif diff < 2592000:
        return f"{int(diff // 86400)} روز قبل"
    else:
        return f"{int(diff // 2592000)} ماه قبل"

def format_user_info(user_data):
    """فرمت‌دهی اطلاعات کاربر"""
    user_id = user_data['id']
    username = user_data.get('username', 'ندارد')
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    
    # ساخت نام کامل
    full_name = f"{first_name} {last_name}".strip()
    if not full_name:
        full_name = "نامشخص"
    
    # ساخت لینک کاربر
    if username and username != 'ندارد':
        user_link = f"@{username}"
    else:
        user_link = f"[لینک کاربر](tg://user?id={user_id})"
    
    return full_name, user_link, username

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    current_date = get_jalali_datetime()
    
    await m.reply_text(text=f"""**👥 کل کاربران:** `{await db.total_users_count()}`
**🚫 کاربران مسدود شده:** `{await db.total_banned_users_count()}`
**🔗 لینک‌های تولید شده:** `{await db.total_files()}`
**🗓️ تاریخ:** `{current_date}`"""
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
    هندلر ارسال پیام همگانی
    """
    try:
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
                
                if done > 0:
                    await asyncio.sleep(0.2)
                
                status, error_msg = await send_msg(user_id=user_id, message=broadcast_msg)
                
                if status == 200:
                    success += 1
                else:
                    failed += 1
                    if status == 400:
                        await db.delete_user(user_id)
                
                done += 1
                
                if done % 5 == 0:
                    await progress_msg.edit_text(f"📤 ارسال شده: {done}/{total_users}\n✅ موفق: {success}\n❌ ناموفق: {failed}")
                        
            except Exception as e:
                failed += 1
                continue

        total_time = datetime.timedelta(seconds=int(time.time() - start_time))
        
        await progress_msg.delete()
        
        final_report = f"""✅ **ارسال همگانی تکمیل شد!**

👥 کاربران کل: {total_users}
📤 ارسال شده: {done}
✅ موفق: {success}
❌ ناموفق: {failed}
⏱️ زمان کل: {total_time}
🗓️ تاریخ: {get_jalali_datetime()}"""

        await m.reply_text(final_report, quote=True)

    except Exception as e:
        logger.error(f"خطای کلی در broadcast: {e}")
        await m.reply_text(f"❌ خطا در ارسال همگانی: {e}", quote=True)


@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    file_id = m.text.split(" ")[-1]
    try:
        file_info = await db.get_file(file_id)
    except FIleNotFound:
        await m.reply_text(text=f"**فایل قبلاً حذف شده است**", quote=True)
        return
    await db.delete_one_file(file_info['_id'])
    await db.count_links(file_info['user_id'], "-")
    await m.reply_text(text=f"**فایل با موفقیت حذف شد !** ", quote=True)


# ==================== دستورات مدیریت کاربران ====================

@FileStream.on_message(filters.command("users") & filters.private & filters.user(Telegram.OWNER_ID))
async def show_users(c: Client, m: Message):
    """نمایش لیست کاربران با اطلاعات کامل"""
    try:
        all_users = await db.get_all_users()
        total_users = await db.total_users_count()
        
        if total_users == 0:
            await m.reply_text("❌ هیچ کاربری در دیتابیس وجود ندارد.", quote=True)
            return

        users_list = []
        async for user in all_users:
            users_list.append(user)
        
        users_list.sort(key=lambda x: x.get('join_date', 0), reverse=True)
        
        await show_users_page(c, m, users_list, 1, total_users)
        
    except Exception as e:
        logger.error(f"خطا در نمایش کاربران: {e}")
        await m.reply_text(f"❌ خطا در دریافت لیست کاربران: {e}", quote=True)


async def show_users_page(c: Client, m: Message, users_list: list, page: int, total_users: int):
    """نمایش یک صفحه از کاربران با اطلاعات کامل"""
    try:
        users_per_page = 8  # کاهش به 8 کاربر در صفحه به دلیل اطلاعات بیشتر
        start_idx = (page - 1) * users_per_page
        end_idx = start_idx + users_per_page
        page_users = users_list[start_idx:end_idx]
        
        total_pages = (total_users + users_per_page - 1) // users_per_page
        
        text = f"**👥 لیست کاربران ربات**\n\n"
        text += f"📊 **آمار کلی:**\n"
        text += f"├ 👤 کاربران کل: `{total_users}`\n"
        text += f"├ 📄 صفحه: `{page}/{total_pages}`\n"
        text += f"└ 🗓️ تاریخ: `{get_jalali_datetime()}`\n\n"
        text += "**━━━━━━━━━━━━━━━━━━━━**\n\n"
        
        for i, user in enumerate(page_users, start=start_idx + 1):
            user_id = user['id']
            join_date = user.get('join_date', 0)
            links_count = user.get('Links', 0)
            
            # فرمت‌دهی اطلاعات کاربر
            full_name, user_link, username = format_user_info(user)
            join_date_str = convert_to_jalali(join_date)
            
            is_banned = await db.is_user_banned(user_id)
            status = "🚫 مسدود" if is_banned else "✅ فعال"
            
            text += f"**{i}. {full_name}**\n"
            text += f"   ├ 🆔 آیدی: `{user_id}`\n"
            text += f"   ├ 📧 یوزرنیم: {user_link}\n"
            text += f"   ├ 📅 عضویت: `{join_date_str}`\n"
            text += f"   ├ 🔗 فایل‌ها: `{links_count}`\n"
            text += f"   └ 🎯 وضعیت: {status}\n\n"
            
            if i < min(end_idx, total_users):
                text += "───\n\n"
        
        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"users_{page-1}"))
        
        buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="users_current"))
        
        if page < total_pages:
            buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"users_{page+1}"))
        
        keyboard = []
        if buttons:
            keyboard.append(buttons)
        
        keyboard.append([
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="users_refresh"),
            InlineKeyboardButton("📊 آمار کامل", callback_data="users_stats")
        ])
        
        keyboard.append([InlineKeyboardButton("❌ بستن", callback_data="users_close")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await m.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
            
    except Exception as e:
        logger.error(f"خطا در نمایش صفحه کاربران: {e}")
        await m.reply_text(f"❌ خطا در نمایش صفحه: {e}", quote=True)


@FileStream.on_message(filters.command("userinfo") & filters.private & filters.user(Telegram.OWNER_ID))
async def user_info(c: Client, m: Message):
    """نمایش اطلاعات کامل یک کاربر"""
    try:
        if len(m.command) < 2:
            await m.reply_text("❌ لطفاً آیدی کاربر را وارد کنید:\nمثال: `/userinfo 123456789`", quote=True)
            return
        
        user_id = int(m.command[1])
        user = await db.get_user(user_id)
        
        if not user:
            await m.reply_text(f"❌ کاربر با آیدی `{user_id}` پیدا نشد.", quote=True)
            return
        
        join_date = user.get('join_date', 0)
        links_count = user.get('Links', 0)
        last_send_time = user.get('last_send_time', 0)
        is_banned = await db.is_user_banned(user_id)
        
        # فرمت‌دهی اطلاعات کاربر
        full_name, user_link, username = format_user_info(user)
        join_date_str = convert_to_jalali(join_date)
        last_active_str = convert_to_jalali(last_send_time) if last_send_time else "هرگز"
        
        join_ago = get_time_ago(join_date)
        last_active_ago = get_time_ago(last_send_time) if last_send_time else "فعالیت نداشته"
        
        text = f"**👤 اطلاعات کامل کاربر**\n\n"
        text += f"**👤 نام کامل:** `{full_name}`\n"
        text += f"**🆔 آیدی کاربر:** `{user_id}`\n"
        text += f"**📧 یوزرنیم:** {user_link}\n"
        text += f"**🎯 وضعیت:** {'🚫 مسدود' if is_banned else '✅ فعال'}\n\n"
        
        text += f"**📅 تاریخ عضویت:**\n"
        text += f"├ 📝 تاریخ: `{join_date_str}`\n"
        text += f"└ ⏳ مدت: `{join_ago}`\n\n"
        
        text += f"**📊 آمار فعالیت:**\n"
        text += f"├ 🔗 فایل‌های آپلود شده: `{links_count}`\n"
        text += f"├ 📍 آخرین فعالیت: `{last_active_str}`\n"
        text += f"└ 🕒 زمان گذشته: `{last_active_ago}`\n\n"
        
        text += f"**🗓️ تاریخ گزارش:** `{get_jalali_datetime()}`"
        
        # دکمه‌های مدیریت کاربر
        keyboard = [
            [
                InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"ban_{user_id}"),
                InlineKeyboardButton("✅ رفع مسدودیت", callback_data=f"unban_{user_id}")
            ],
            [
                InlineKeyboardButton("🗑️ حذف کاربر", callback_data=f"delete_{user_id}"),
                InlineKeyboardButton("📨 پیام به کاربر", callback_data=f"message_{user_id}")
            ],
            [
                InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="users_back"),
                InlineKeyboardButton("❌ بستن", callback_data="users_close")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await m.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد.", quote=True)
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات کاربر: {e}")
        await m.reply_text(f"❌ خطا در دریافت اطلاعات: {e}", quote=True)


@FileStream.on_callback_query(filters.regex(r"^users_"))
async def users_callback_handler(c: Client, query: CallbackQuery):
    """مدیریت callbackهای کاربران"""
    try:
        data = query.data
        
        if data == "users_refresh":
            await show_users(c, query.message)
            await query.answer("✅ لیست بروزرسانی شد")
            
        elif data == "users_stats":
            total_users = await db.total_users_count()
            banned_count = await db.total_banned_users_count()
            active_count = total_users - banned_count
            
            # محاسبه کاربران با یوزرنیم
            all_users = await db.get_all_users()
            users_with_username = 0
            async for user in all_users:
                if user.get('username') and user.get('username') != 'ندارد':
                    users_with_username += 1
            
            stats_text = f"**📊 آمار کامل کاربران**\n\n"
            stats_text += f"👥 کاربران کل: `{total_users}`\n"
            stats_text += f"✅ کاربران فعال: `{active_count}`\n"
            stats_text += f"🚫 کاربران مسدود: `{banned_count}`\n"
            stats_text += f"📧 کاربران با یوزرنیم: `{users_with_username}`\n"
            stats_text += f"📈 درصد فعال: `{(active_count/total_users)*100:.1f}%`\n\n"
            stats_text += f"🗓️ **تاریخ:** `{get_jalali_datetime()}`"
            
            await query.message.edit_text(
                text=stats_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="users_back")],
                    [InlineKeyboardButton("❌ بستن", callback_data="users_close")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            await query.answer()
            
        elif data == "users_back":
            await show_users(c, query.message)
            await query.answer()
            
        elif data == "users_close":
            await query.message.delete()
            await query.answer()
            
        elif data.startswith("users_"):
            try:
                page = int(data.split("_")[1])
                all_users = await db.get_all_users()
                users_list = []
                async for user in all_users:
                    users_list.append(user)
                users_list.sort(key=lambda x: x.get('join_date', 0), reverse=True)
                total_users = await db.total_users_count()
                
                await show_users_page(c, query.message, users_list, page, total_users)
                await query.answer()
            except:
                await query.answer("❌ خطا در تغییر صفحه", show_alert=True)
            
    except Exception as e:
        logger.error(f"خطا در مدیریت callback کاربران: {e}")
        await query.answer("❌ خطا در پردازش درخواست", show_alert=True)


@FileStream.on_message(filters.command("user_stats") & filters.private & filters.user(Telegram.OWNER_ID))
async def user_stats(c: Client, m: Message):
    """نمایش آمار کاربران"""
    try:
        total_users = await db.total_users_count()
        banned_users = await db.total_banned_users_count()
        active_users = total_users - banned_users
        
        # محاسبه کاربران با یوزرنیم
        all_users = await db.get_all_users()
        users_with_username = 0
        recent_users = []
        count = 0
        
        async for user in all_users:
            if user.get('username') and user.get('username') != 'ندارد':
                users_with_username += 1
            
            if count < 5:
                recent_users.append(user)
                count += 1
        
        stats_text = f"""📊 **آمار دقیق کاربران**

👥 **کاربران کل:** `{total_users}`
✅ **کاربران فعال:** `{active_users}`
🚫 **کاربران مسدود:** `{banned_users}`
📧 **کاربران با یوزرنیم:** `{users_with_username}`

**کاربران اخیر:**
"""
        
        for user in recent_users:
            user_id = user['id']
            full_name, user_link, username = format_user_info(user)
            join_date_str = convert_to_jalali(user.get('join_date', time.time()))
            
            stats_text += f"├ 👤 {full_name}\n"
            stats_text += f"│  ├ 🆔 `{user_id}`\n"
            stats_text += f"│  └ {user_link} - {join_date_str}\n"
        
        stats_text += f"\n🗓️ **تاریخ گزارش:** `{get_jalali_datetime()}`"
        
        await m.reply_text(stats_text, quote=True)
        
    except Exception as e:
        await m.reply_text(f"❌ خطا در دریافت آمار: {e}", quote=True)