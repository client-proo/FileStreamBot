import os
import time
import string
import random
import asyncio
import aiofiles
import datetime
import pickle
from pathlib import Path

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram, Server
from pyrogram import filters, Client
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums.parse_mode import ParseMode

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# فایل برای ذخیره وضعیت ربات
BOT_STATUS_FILE = "bot_status.pkl"

# فایل برای ذخیره لیست ادمین‌ها
ADMINS_FILE = "admins.pkl"

# لیست دسترسی‌ها
PERMISSIONS_LIST = [
    ('change_settings', 'تغییر تنظیمات ربات'),
    ('view_stats', 'مشاهده آمار ربات'),
    ('broadcast', 'ارسال پیام همگانی'),
    ('delete_files', 'حذف فایل ها'),
    ('toggle_bot', 'خاموش و روشن کردن ربات'),
    ('manage_admins', 'مدیریت ادمین ها'),
    ('manage_comments', 'دریافت و پاسخ به کامنت ها')
]

# حالت‌های کاربران
user_states = {}

def load_bot_status():
    """بارگذاری وضعیت ربات از فایل"""
    try:
        if Path(BOT_STATUS_FILE).exists():
            with open(BOT_STATUS_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    return True  # حالت پیش‌فرض: روشن

def save_bot_status(status):
    """ذخیره وضعیت ربات در فایل"""
    try:
        with open(BOT_STATUS_FILE, 'wb') as f:
            pickle.dump(status, f)
    except Exception as e:
        print(f"Error saving bot status: {e}")

def load_admins():
    """بارگذاری لیست ادمین‌ها از فایل"""
    try:
        if Path(ADMINS_FILE).exists():
            with open(ADMINS_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    # اگر فایل وجود ندارد، صاحب ربات را به عنوان ادمین اصلی اضافه کن
    admins = {
        Telegram.OWNER_ID: {
            'name': 'صاحب ربات',
            'username': 'owner',
            'permissions': ['all']
        }
    }
    save_admins(admins)
    return admins

def save_admins(admins):
    """ذخیره لیست ادمین‌ها در فایل"""
    try:
        with open(ADMINS_FILE, 'wb') as f:
            pickle.dump(admins, f)
    except Exception as e:
        print(f"Error saving admins: {e}")

# وضعیت ربات
bot_status = load_bot_status()

# لیست ادمین‌ها
admins_data = load_admins()

# تابع برای چک کردن دسترسی ادمین
def is_admin(user_id: int) -> bool:
    """چک کردن آیا کاربر ادمین است یا نه"""
    return user_id == Telegram.OWNER_ID or user_id in admins_data

# تابع برای چک کردن دسترسی خاص
def has_permission(user_id: int, permission: str) -> bool:
    """چک کردن دسترسی ادمین به یک قابلیت خاص"""
    if user_id == Telegram.OWNER_ID:
        return True
    
    admin_info = admins_data.get(user_id)
    if not admin_info:
        return False
    
    permissions = admin_info.get('permissions', [])
    return 'all' in permissions or permission in permissions

# دکوراتور برای چک کردن دسترسی
def require_permission(permission: str):
    """دکوراتور برای چک کردن دسترسی"""
    def decorator(func):
        async def wrapper(client, message):
            if not has_permission(message.from_user.id, permission):
                await message.reply_text("❌ شما دسترسی به این قابلیت را ندارید.")
                return
            return await func(client, message)
        return wrapper
    return decorator

# کیبورد مدیریت ادمین
ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton("📊 مشاهده فایل ها و آمار"),
            KeyboardButton("🔊 ارسال پیام همگانی")
        ],
        [
            KeyboardButton("⚙️ تنظیمات"), 
            KeyboardButton("🔴 خاموش/روشن کردن ربات")
        ]
    ],
    resize_keyboard=True,
    selective=True
)

@FileStream.on_message(filters.command("panel") & filters.private)
async def admin_panel_handler(bot: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ شما دسترسی به پنل مدیریت ندارید.")
        return
        
    await message.reply_text(
        "🏠 **صفحه اصلی**\n\n"
        "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=ADMIN_KEYBOARD
    )

@FileStream.on_message(filters.private)
async def admin_message_handler(bot: Client, message: Message):
    # چک کردن آیا کاربر ادمین است
    if not is_admin(message.from_user.id):
        return
        
    global bot_status
    user_id = message.from_user.id
    
    # اگر کاربر در حالت ارسال پیام همگانی است
    if user_id in user_states and user_states[user_id] == "awaiting_broadcast":
        if message.text == "🔙 بازگشت":
            del user_states[user_id]
            await message.reply_text(
                "🏠 به صفحه اصلی بازگشتید",
                reply_markup=ADMIN_KEYBOARD
            )
            return
        
        # چک دسترسی ارسال همگانی
        if not has_permission(user_id, 'broadcast'):
            await message.reply_text("❌ شما دسترسی به ارسال پیام همگانی ندارید.")
            del user_states[user_id]
            await message.reply_text(
                "🏠 به صفحه اصلی بازگشتید",
                reply_markup=ADMIN_KEYBOARD
            )
            return
        
        # ارسال مستقیم پیام (بدون نیاز به ریپلای)
        await start_broadcast(bot, message, message)
        return

    # اگر کاربر در حالت افزودن ادمین است
    if user_id in user_states and user_states[user_id] == "adding_admin":
        if message.text and message.text == "/cancel":
            del user_states[user_id]
            await message.reply_text(
                "❌ عملیات افزودن ادمین لغو شد.",
                reply_markup=ADMIN_KEYBOARD
            )
            return
        
        await process_add_admin(bot, message)
        return

    # پردازش دکمه‌های کیبورد
    if message.text == "📊 مشاهده فایل ها و آمار":
        # چک دسترسی مشاهده آمار
        if not has_permission(user_id, 'view_stats'):
            await message.reply_text("❌ شما دسترسی به مشاهده آمار را ندارید.")
            return
            
        total_users = await db.total_users_count()
        total_banned = await db.total_banned_users_count()
        total_files = await db.total_files()
        
        stats_text = (
            "📊 **آمار کلی ربات:**\n\n"
            f"👥 کل کاربران: `{total_users}`\n"
            f"🚫 کاربران مسدود شده: `{total_banned}`\n" 
            f"📁 کل فایل‌ها: `{total_files}`\n"
            f"🔌 وضعیت ربات: `{'🟢 روشن' if bot_status else '🔴 خاموش'}`"
        )
        
        await message.reply_text(stats_text, reply_markup=ADMIN_KEYBOARD)
    
    elif message.text == "🔊 ارسال پیام همگانی":
        # چک دسترسی ارسال همگانی
        if not has_permission(user_id, 'broadcast'):
            await message.reply_text("❌ شما دسترسی به ارسال پیام همگانی ندارید.")
            return
            
        user_states[user_id] = "awaiting_broadcast"
        await message.reply_text(
            "📨 **ارسال پیام همگانی**\n\n"
            "✅ اکنون می‌توانید:\n"
            "• پیام جدید تایپ کنید 📝\n" 
            "• عکس/ویدیو ارسال کنید 🖼️\n"
            "• فایل فوروارد کنید 📎\n\n"
            "پیام شما مستقیماً برای همه کاربران ارسال خواهد شد.\n\n"
            "برای بازگشت از دکمه 🔙 استفاده کنید.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 بازگشت")]], resize_keyboard=True)
        )
    
    elif message.text == "⚙️ تنظیمات":
        # چک دسترسی تغییر تنظیمات
        if not has_permission(user_id, 'change_settings'):
            await message.reply_text("❌ شما دسترسی به تنظیمات را ندارید.")
            return
            
        # ایجاد کیبورد اینلاین برای تنظیمات
        settings_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("عضویت اجباری🔒", callback_data="settings_force_sub"),
                InlineKeyboardButton("ادمین ها👥", callback_data="settings_admins")
            ],
            [
                InlineKeyboardButton("لیست کاربران👥", callback_data="settings_users_list"),
                InlineKeyboardButton("لیست کاربران مسدود شده🚫", callback_data="settings_banned_list")
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")
            ]
        ])
        
        settings_text = (
            "⚙️ **تنظیمات ربات**\n\n"
            f"⏰ زمان انقضای لینک‌ها: `{Telegram.EXPIRE_TIME} ثانیه`\n"
            f"🚫 زمان ضد اسپم: `{Telegram.ANTI_SPAM_TIME} ثانیه`\n"
            f"👥 کاربران مجاز: `{len(Telegram.AUTH_USERS) if Telegram.AUTH_USERS else 'همه'}`\n"
            f"📢 عضویت اجباری: `{'فعال' if Telegram.FORCE_SUB else 'غیرفعال'}`\n"
            f"🔌 وضعیت ربات: `{'🟢 روشن' if bot_status else '🔴 خاموش'}`\n\n"
            "**یکی از گزینه های زیر را انتخاب کنید👇👇**"
        )
        
        await message.reply_text(settings_text, reply_markup=settings_keyboard)
    
    elif message.text == "🔴 خاموش/روشن کردن ربات":
        # چک دسترسی خاموش/روشن کردن
        if not has_permission(user_id, 'toggle_bot'):
            await message.reply_text("❌ شما دسترسی به خاموش/روشن کردن ربات را ندارید.")
            return
            
        # تغییر وضعیت ربات
        bot_status = not bot_status
        save_bot_status(bot_status)  # ذخیره در فایل
        
        if bot_status:
            status_text = "🟢 **ربات روشن شد**\n\nکاربران اکنون می‌توانند فایل‌ها را دریافت کنند."
        else:
            status_text = "🔴 **ربات خاموش شد**\n\nکاربران دیگر نمی‌توانند فایل‌ها را دریافت کنند."
        
        await message.reply_text(status_text, reply_markup=ADMIN_KEYBOARD)
    
    elif message.text == "🔙 بازگشت":
        if user_id in user_states:
            del user_states[user_id]
        await message.reply_text(
            "🏠 به صفحه اصلی بازگشتید",
            reply_markup=ADMIN_KEYBOARD
        )

async def process_add_admin(bot: Client, message: Message):
    """پردازش افزودن ادمین جدید"""
    user_id = message.from_user.id
    
    # چک دسترسی مدیریت ادمین‌ها
    if not has_permission(user_id, 'manage_admins'):
        await message.reply_text("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.")
        del user_states[user_id]
        return
        
    target_user = None
    
    try:
        # بررسی اگر پیام فوروارد شده است
        if message.forward_from:
            target_user = message.forward_from
            print(f"Found user from forward: {target_user.id} - {target_user.first_name}")
        # بررسی اگر یوزرنیم ارسال شده
        elif message.text and message.text.startswith('@'):
            username = message.text[1:].strip()
            print(f"Looking up username: {username}")
            try:
                target_user = await bot.get_users(username)
                print(f"Found user by username: {target_user.id} - {target_user.first_name}")
            except Exception as e:
                print(f"Error looking up username: {e}")
                await message.reply_text("❌ کاربری با این یوزرنیم یافت نشد.")
                return
        # بررسی اگر آیدی عددی ارسال شده
        elif message.text and message.text.strip().replace(' ', '').isdigit():
            user_id_str = message.text.strip().replace(' ', '')
            user_id_int = int(user_id_str)
            print(f"Looking up user ID: {user_id_int}")
            try:
                target_user = await bot.get_users(user_id_int)
                print(f"Found user by ID: {target_user.id} - {target_user.first_name}")
            except Exception as e:
                print(f"Error looking up user ID: {e}")
                await message.reply_text("❌ کاربری با این آیدی یافت نشد.")
                return
        else:
            print(f"No valid method detected. Text: '{message.text}', Forward: {message.forward_from}")
            await message.reply_text(
                "❌ لطفاً یک روش معتبر برای افزودن ادمین استفاده کنید:\n\n"
                "• یک پیام از کاربر مورد نظر فوروارد کنید\n"
                "• یوزرنیم کاربر را با @ ارسال کنید\n" 
                "• آیدی عددی کاربر را ارسال کنید\n\n"
                "برای لغو /cancel را بزنید."
            )
            return
        
        if target_user:
            # اضافه کردن کاربر به لیست ادمین‌ها با دسترسی کامل
            admins_data[target_user.id] = {
                'name': target_user.first_name or "بدون نام",
                'username': target_user.username or 'ندارد',
                'permissions': ['all']  # دسترسی کامل مانند صاحب ربات
            }
            save_admins(admins_data)
            
            # حذف حالت
            del user_states[user_id]
            
            # نمایش پیام موفقیت
            success_text = (
                "✅ **ادمین با موفقیت افزوده شد.**\n\n"
                f"👤 **نام:** {target_user.first_name or 'بدون نام'}\n"
                f"🆔 **آیدی:** `{target_user.id}`"
            )
            
            await message.reply_text(success_text)
            
            # نمایش لیست ادمین‌های به‌روز شده
            await show_admins_list(bot, message=message)
            
    except Exception as e:
        print(f"Error in process_add_admin: {e}")
        await message.reply_text(f"❌ خطا در پردازش: {str(e)}")

async def show_admins_list(bot: Client, message: Message = None, callback_query: CallbackQuery = None):
    """نمایش لیست ادمین‌ها"""
    global admins_data
    
    # فیلتر کردن صاحب ربات از لیست نمایش
    display_admins = {k: v for k, v in admins_data.items() if k != Telegram.OWNER_ID}
    
    if not display_admins:
        admins_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ادمینی ثبت نشده است", callback_data="N/A")],
            [InlineKeyboardButton("افزودن ادمین جدید➕", callback_data="add_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")]
        ])
        
        text = "**لیست ادمین های ثبت شده در ربات👇👇**\n\nدر حال حاضر هیچ ادمینی ثبت نشده است."
    else:
        # ایجاد کیبورد برای ادمین‌ها - چهار دکمه جداگانه
        keyboard_buttons = []
        for admin_id, admin_info in display_admins.items():
            # کوتاه کردن نام اگر طولانی باشد
            name_display = admin_info['name']
            if len(name_display) > 15:
                name_display = name_display[:12] + "..."
            
            # چهار دکمه جداگانه در یک ردیف
            keyboard_buttons.append([
                InlineKeyboardButton(str(admin_id), callback_data=f"admin_info_{admin_id}"),
                InlineKeyboardButton(name_display, callback_data=f"admin_info_{admin_id}"),
                InlineKeyboardButton("⚙", callback_data=f"admin_settings_{admin_id}"),
                InlineKeyboardButton("❌", callback_data=f"admin_delete_{admin_id}")
            ])
        
        # دکمه افزودن ادمین جدید
        keyboard_buttons.append([InlineKeyboardButton("افزودن ادمین جدید➕", callback_data="add_admin")])
        keyboard_buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")])
        
        admins_keyboard = InlineKeyboardMarkup(keyboard_buttons)
        text = "**لیست ادمین های ثبت شده در ربات👇👇**"
    
    if message:
        await message.reply_text(text, reply_markup=admins_keyboard)
    elif callback_query:
        try:
            await callback_query.message.edit_text(text, reply_markup=admins_keyboard)
        except Exception as e:
            # اگر ویرایش پیام ممکن نبود، پیام جدید ارسال کن
            await callback_query.message.reply_text(text, reply_markup=admins_keyboard)

async def show_admin_settings(bot: Client, admin_id: int, callback_query: CallbackQuery):
    """نمایش تنظیمات ادمین"""
    admin_info = admins_data.get(admin_id)
    if not admin_info:
        await callback_query.answer("❌ ادمین یافت نشد!", show_alert=True)
        return
    
    # Get current permissions
    current_permissions = admin_info.get('permissions', [])
    
    text = (
        f"**تنظیمات دسترسی های ادمین ({admin_id}) در ربات👇👇**\n\n"
        f"**نام:** {admin_info['name']}\n"
        f"**یوزرنیم:** @{admin_info['username']}\n\n"
        "**دسترسی‌ها:**"
    )
    
    # Create permission buttons with ✅/❌ icons
    permission_buttons = []
    for perm_key, perm_name in PERMISSIONS_LIST:
        has_permission = 'all' in current_permissions or perm_key in current_permissions
        icon = "✅" if has_permission else "❌"
        button_text = f"{icon} {perm_name}"
        permission_buttons.append([
            InlineKeyboardButton(button_text, callback_data=f"perm_toggle_{admin_id}_{perm_key}")
        ])
    
    # Add other buttons
    permission_buttons.extend([
        [InlineKeyboardButton("🔄 تغییر ادمین به صاحب ربات", callback_data=f"make_owner_{admin_id}")],
        [InlineKeyboardButton("🗑️ حذف از لیست ادمین ها", callback_data=f"admin_delete_confirm_{admin_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_admins")]
    ])
    
    permissions_keyboard = InlineKeyboardMarkup(permission_buttons)
    
    try:
        await callback_query.message.edit_text(text, reply_markup=permissions_keyboard)
    except Exception as e:
        await callback_query.message.reply_text(text, reply_markup=permissions_keyboard)

# هندلر برای callback_query های تنظیمات
@FileStream.on_callback_query()
async def callback_query_handler(bot: Client, update: CallbackQuery):
    # چک کردن آیا کاربر ادمین است
    if not is_admin(update.from_user.id):
        await update.answer("❌ شما دسترسی به این بخش ندارید.", show_alert=True)
        return
        
    data = update.data
    
    try:
        if data.startswith("settings_"):
            await handle_settings_callback(bot, update, data)
        elif data.startswith(("add_admin", "admin_", "perm_", "make_owner")):
            await handle_admin_management_callback(bot, update, data)
        elif data == "N/A":
            await update.answer("این گزینه در دسترس نیست", show_alert=True)
    except Exception as e:
        print(f"Error in callback handler: {e}")
        await update.answer("❌ خطا در پردازش درخواست", show_alert=True)

async def handle_settings_callback(bot: Client, update: CallbackQuery, data: str):
    """مدیریت callback‌های مربوط به تنظیمات"""
    if data == "settings_force_sub":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_admins":
        # چک دسترسی مدیریت ادمین‌ها
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return
        await show_admins_list(bot, callback_query=update)
    
    elif data == "settings_users_list":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_banned_list":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_back":
        try:
            await update.message.edit_text(
                "🏠 **صفحه اصلی**\n\n"
                "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=ADMIN_KEYBOARD
            )
        except Exception as e:
            await update.message.reply_text(
                "🏠 **صفحه اصلی**\n\n"
                "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=ADMIN_KEYBOARD
            )

async def handle_admin_management_callback(bot: Client, update: CallbackQuery, data: str):
    """مدیریت callback‌های مربوط به ادمین‌ها"""
    if data == "add_admin":
        # چک دسترسی مدیریت ادمین‌ها
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return
            
        user_states[update.from_user.id] = "adding_admin"
        try:
            await update.message.edit_text(
                "➕ **افزودن ادمین جدید**\n\n"
                "برای افزودن ادمین، یکی از روش‌های زیر را استفاده کنید:\n"
                "- یک پیام از کاربر مورد نظر فوروارد کنید\n"
                "- یوزرنیم کاربر را با @ ارسال کنید\n" 
                "- آیدی عددی کاربر را ارسال کنید\n\n"
                "برای لغو /cancel را بزنید."
            )
        except Exception as e:
            await update.message.reply_text(
                "➕ **افزودن ادمین جدید**\n\n"
                "برای افزودن ادمین، یکی از روش‌های زیر را استفاده کنید:\n"
                "- یک پیام از کاربر مورد نظر فوروارد کنید\n"
                "- یوزرنیم کاربر را با @ ارسال کنید\n"
                "- آیدی عددی کاربر را ارسال کنید\n\n"
                "برای لغو /cancel را بزنید."
            )
    
    elif data.startswith("admin_info_"):
        admin_id = int(data.split("_")[2])
        admin_info = admins_data.get(admin_id)
        if admin_info:
            await update.answer(f"اطلاعات ادمین:\nنام: {admin_info['name']}\nیوزرنیم: @{admin_info['username']}", show_alert=True)
        else:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)
    
    elif data.startswith("admin_settings_"):
        # چک دسترسی مدیریت ادمین‌ها
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return
            
        admin_id = int(data.split("_")[2])
        await show_admin_settings(bot, admin_id, update)
    
    elif data.startswith("admin_delete_"):
        # چک دسترسی مدیریت ادمین‌ها
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return
            
        admin_id = int(data.split("_")[2])
        if admin_id == Telegram.OWNER_ID:
            await update.answer("❌ نمی‌توانید صاحب ربات را حذف کنید!", show_alert=True)
            return
        
        if admin_id in admins_data:
            del admins_data[admin_id]
            save_admins(admins_data)
            await update.answer("✅ ادمین با موفقیت حذف شد!", show_alert=True)
            await show_admins_list(bot, callback_query=update)
        else:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)
    
    elif data.startswith("admin_delete_confirm_"):
        # چک دسترسی مدیریت ادمین‌ها
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return
            
        admin_id = int(data.split("_")[3])
        if admin_id == Telegram.OWNER_ID:
            await update.answer("❌ نمی‌توانید صاحب ربات را حذف کنید!", show_alert=True)
            return
        
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admin_delete_{admin_id}")],
            [InlineKeyboardButton("❌ خیر، برگرد", callback_data=f"admin_settings_{admin_id}")]
        ])
        
        admin_info = admins_data.get(admin_id)
        if admin_info:
            try:
                await update.message.edit_text(
                    f"⚠️ **آیا مطمئن هستید که می‌خواهید ادمین زیر را حذف کنید؟**\n\n"
                    f"🆔 آیدی: `{admin_id}`\n"
                    f"👤 نام: {admin_info['name']}\n"
                    f"📱 یوزرنیم: @{admin_info['username']}",
                    reply_markup=confirm_keyboard
                )
            except Exception as e:
                await update.message.reply_text(
                    f"⚠️ **آیا مطمئن هستید که می‌خواهید ادمین زیر را حذف کنید؟**\n\n"
                    f"🆔 آیدی: `{admin_id}`\n"
                    f"👤 نام: {admin_info['name']}\n"
                    f"📱 یوزرنیم: @{admin_info['username']}",
                    reply_markup=confirm_keyboard
                )
    
    elif data.startswith("perm_toggle_"):
        # چک دسترسی مدیریت ادمین‌ها
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return
            
        parts = data.split("_")
        admin_id = int(parts[2])
        permission = parts[3]
        
        if admin_id in admins_data:
            admin_info = admins_data[admin_id]
            permissions = admin_info.get('permissions', [])
            
            # Toggle permission
            if permission in permissions:
                permissions.remove(permission)
                action = "غیرفعال"
            else:
                permissions.append(permission)
                action = "فعال"
            
            admin_info['permissions'] = permissions
            admins_data[admin_id] = admin_info
            save_admins(admins_data)
            
            # Update the settings page to show new status
            await show_admin_settings(bot, admin_id, update)
            
            await update.answer(f"✅ دسترسی {action} شد!", show_alert=True)
        else:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)
    
    elif data.startswith("make_owner_"):
        await update.answer("❌ این قابلیت در حال حاضر فعال نیست!", show_alert=True)

async def start_broadcast(bot: Client, message: Message, broadcast_msg: Message):
    user_id = message.from_user.id
    
    # حذف حالت کاربر
    if user_id in user_states:
        del user_states[user_id]
    
    processing_msg = await message.reply_text("🔄 در حال ارسال پیام همگانی...")
    
    all_users = await db.get_all_users()
    
    # ایجاد ID برای پیگیری
    while True:
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(6)])
        if not broadcast_ids.get(broadcast_id):
            break
    
    start_time = time.time()
    total_users = await db.total_users_count()
    done = 0
    failed = 0
    success = 0
    
    broadcast_ids[broadcast_id] = dict(
        total=total_users,
        current=done,
        failed=failed,
        success=success
    )
    
    # فایل لاگ
    async with aiofiles.open('broadcast.txt', 'w', encoding='utf-8') as broadcast_log_file:
        async for user in all_users:
            try:
                # ارسال پیام به کاربر
                await broadcast_msg.copy(chat_id=int(user['id']))
                success += 1
            except Exception as e:
                failed += 1
                error_msg = f"{user['id']} : {str(e)}\n"
                await broadcast_log_file.write(error_msg)
                
                # اگر کاربر ربات را بلاک کرده یا خطای خاصی دارد
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    await db.delete_user(user['id'])
            
            done += 1
            
            # آپدیت وضعیت هر 10 کاربر
            if done % 10 == 0:
                if broadcast_ids.get(broadcast_id):
                    broadcast_ids[broadcast_id].update(
                        dict(current=done, failed=failed, success=success)
                    )
                    try:
                        await processing_msg.edit_text(
                            f"📤 ارسال پیام همگانی...\n\n"
                            f"✅ ارسال شده: {done}/{total_users}\n"
                            f"✔️ موفق: {success}\n"
                            f"❌ ناموفق: {failed}"
                        )
                    except:
                        pass
    
    # پاک کردن از حافظه
    if broadcast_ids.get(broadcast_id):
        broadcast_ids.pop(broadcast_id)
    
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await processing_msg.delete()
    
    if failed == 0:
        await message.reply_text(
            text=f"✅ ارسال همگانی در `{completed_in}` تکمیل شد!\n\n"
                 f"👥 کل کاربران: {total_users}\n"
                 f"📤 ارسال شده: {done}\n"
                 f"✅ موفق: {success}\n"
                 f"❌ ناموفق: {failed}",
            reply_markup=ADMIN_KEYBOARD,
            quote=True
        )
    else:
        await message.reply_document(
            document='broadcast.txt',
            caption=f"✅ ارسال همگانی در `{completed_in}` تکمیل شد!\n\n"
                    f"👥 کل کاربران: {total_users}\n"
                    f"📤 ارسال شده: {done}\n"
                    f"✅ موفق: {success}\n"
                    f"❌ ناموفق: {failed}",
            reply_markup=ADMIN_KEYBOARD,
            quote=True
        )
        try:
            os.remove('broadcast.txt')
        except:
            pass

@FileStream.on_message(filters.command("status") & filters.private)
@require_permission('view_stats')
async def sts(c: Client, m: Message):
    total_users = await db.total_users_count()
    total_banned = await db.total_banned_users_count()
    total_files = await db.total_files()
    
    await m.reply_text(
        text=f"**👥 کل کاربران:** `{total_users}`\n"
             f"**🚫 کاربران مسدود شده:** `{total_banned}`\n"
             f"**🔗 لینک‌های تولید شده:** `{total_files}`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )

@FileStream.on_message(filters.command("ban") & filters.private)
@require_permission('delete_files')
async def ban_handler(b, m: Message):
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

@FileStream.on_message(filters.command("unban") & filters.private)
@require_permission('delete_files')
async def unban_handler(b, m: Message):
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

@FileStream.on_message(filters.command("broadcast") & filters.private & filters.reply)
@require_permission('broadcast')
async def broadcast_command_handler(c, m):
    """هندلر برای دستور /broadcast با ریپلای"""
    await start_broadcast(c, m, m.reply_to_message)

@FileStream.on_message(filters.command("del") & filters.private)
@require_permission('delete_files')
async def delete_handler(c: Client, m: Message):
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

# تابع برای چک کردن وضعیت ربات (برای استفاده در سایر فایل‌ها)
def is_bot_active():
    global bot_status
    return bot_status