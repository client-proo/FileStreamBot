import os
import time
import string
import random
import asyncio
import aiofiles
import datetime
import logging
import jdatetime
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

def get_jalali_date():
    """دریافت تاریخ و زمان شمسی فعلی"""
    return jdatetime.datetime.now().strftime('%Y/%m/%d - %H:%M:%S')

def convert_to_jalali(timestamp):
    """تبدیل timestamp میلادی به تاریخ شمسی"""
    if not timestamp:
        return "نامشخص"
    
    try:
        gregorian_date = datetime.datetime.fromtimestamp(timestamp)
        jalali_date = jdatetime.datetime.fromgregorian(datetime=gregorian_date)
        return jalali_date.strftime('%Y/%m/%d - %H:%M:%S')
    except:
        return "خطا در تبدیل"

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    current_date = get_jalali_date()
    
    await m.reply_text(text=f"""**👥 کل کاربران:** `{await db.total_users_count()}`
**🚫 کاربران مسدود شده:** `{await db.total_banned_users_count()}`
**🔗 لینک‌های تولید شده:** `{await db.total_files()}`
**🗓️ تاریخ:** `{current_date}`"""
                       , parse_mode=ParseMode.MARKDOWN, quote=True)

# ... (بقیه توابع بدون تغییر تا تابع show_users_page)

async def show_users_page(c: Client, m: Message, users_list: list, page: int, total_users: int):
    """نمایش یک صفحه از کاربران با تاریخ شمسی"""
    try:
        users_per_page = 10
        start_idx = (page - 1) * users_per_page
        end_idx = start_idx + users_per_page
        page_users = users_list[start_idx:end_idx]
        
        total_pages = (total_users + users_per_page - 1) // users_per_page
        
        # ایجاد متن صفحه
        text = f"**👥 لیست کاربران ربات**\n\n"
        text += f"📊 **آمار کلی:**\n"
        text += f"├ 👤 کاربران کل: `{total_users}`\n"
        text += f"├ 📄 صفحه: `{page}/{total_pages}`\n"
        text += f"└ 🗓️ تاریخ: `{get_jalali_date()}`\n\n"
        text += "**━━━━━━━━━━━━━━━━━━━━**\n\n"
        
        # افزودن اطلاعات هر کاربر
        for i, user in enumerate(page_users, start=start_idx + 1):
            user_id = user['id']
            join_date = user.get('join_date', 0)
            links_count = user.get('Links', 0)
            
            # تبدیل تاریخ به شمسی
            join_date_str = convert_to_jalali(join_date)
            
            # بررسی وضعیت بن
            is_banned = await db.is_user_banned(user_id)
            status = "🚫 مسدود" if is_banned else "✅ فعال"
            
            text += f"**{i}. کاربر 🆔 `{user_id}`**\n"
            text += f"   ├ 📅 تاریخ عضویت: `{join_date_str}`\n"
            text += f"   ├ 🔗 فایل‌های آپلود شده: `{links_count}`\n"
            text += f"   └ 🎯 وضعیت: {status}\n\n"
            
            # اگر کاربر آخر صفحه نیست، خط جداکننده اضافه کن
            if i < min(end_idx, total_users):
                text += "───\n\n"
        
        # ایجاد دکمه‌های صفحه‌بندی
        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"users_{page-1}"))
        
        buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="users_current"))
        
        if page < total_pages:
            buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"users_{page+1}"))
        
        keyboard = []
        if buttons:
            keyboard.append(buttons)
        
        # دکمه‌های اضافی
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
    """نمایش اطلاعات کامل یک کاربر خاص با تاریخ شمسی"""
    try:
        if len(m.command) < 2:
            await m.reply_text(
                "❌ لطفاً آیدی کاربر را وارد کنید:\n"
                "مثال: `/userinfo 123456789`",
                quote=True
            )
            return
        
        user_id = int(m.command[1])
        user = await db.get_user(user_id)
        
        if not user:
            await m.reply_text(f"❌ کاربر با آیدی `{user_id}` پیدا نشد.", quote=True)
            return
        
        # دریافت اطلاعات کامل کاربر
        join_date = user.get('join_date', 0)
        links_count = user.get('Links', 0)
        last_send_time = user.get('last_send_time', 0)
        is_banned = await db.is_user_banned(user_id)
        
        # تبدیل تاریخ‌ها به شمسی
        join_date_str = convert_to_jalali(join_date)
        last_active_str = convert_to_jalali(last_send_time) if last_send_time else "هرگز"
        
        join_ago = await get_time_ago(join_date)
        last_active_ago = await get_time_ago(last_send_time) if last_send_time else "فعالیت نداشته"
        
        # ایجاد متن اطلاعات کاربر
        text = f"**👤 اطلاعات کامل کاربر**\n\n"
        text += f"**🆔 آیدی کاربر:** `{user_id}`\n"
        text += f"**🎯 وضعیت:** {'🚫 مسدود' if is_banned else '✅ فعال'}\n\n"
        
        text += f"**📅 تاریخ عضویت:**\n"
        text += f"├ 📝 تاریخ: `{join_date_str}`\n"
        text += f"└ ⏳ مدت: `{join_ago}`\n\n"
        
        text += f"**📊 آمار فعالیت:**\n"
        text += f"├ 🔗 فایل‌های آپلود شده: `{links_count}`\n"
        text += f"├ 📍 آخرین فعالیت: `{last_active_str}`\n"
        text += f"└ 🕒 زمان گذشته: `{last_active_ago}`\n\n"
        
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

# در تابع users_callback_handler
@FileStream.on_callback_query(filters.regex(r"^users_"))
async def users_callback_handler(c: Client, query: CallbackQuery):
    """مدیریت callbackهای مربوط به کاربران"""
    try:
        data = query.data
        
        if data == "users_stats":
            # نمایش آمار کامل
            total_users = await db.total_users_count()
            banned_count = await db.total_banned_users_count()
            active_count = total_users - banned_count
            
            stats_text = f"**📊 آمار کامل کاربران**\n\n"
            stats_text += f"👥 کاربران کل: `{total_users}`\n"
            stats_text += f"✅ کاربران فعال: `{active_count}`\n"
            stats_text += f"🚫 کاربران مسدود: `{banned_count}`\n"
            stats_text += f"📈 درصد فعال: `{(active_count/total_users)*100:.1f}%`\n\n"
            stats_text += f"🗓️ **تاریخ:** `{get_jalali_date()}`"
            
            await query.message.edit_text(
                text=stats_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="users_back")],
                    [InlineKeyboardButton("❌ بستن", callback_data="users_close")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            await query.answer()
            
        # بقیه توابع callback بدون تغییر...
        
    except Exception as e:
        logger.error(f"خطا در مدیریت callback کاربران: {e}")
        await query.answer("❌ خطا در پردازش درخواست", show_alert=True)

# ... (بقیه توابع بدون تغییر)