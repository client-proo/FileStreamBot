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
from FileStream.bot.plugins.admin import is_bot_active

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# فایل برای ذخیره وضعیت ربات
BOT_STATUS_FILE = "bot_status.pkl"

# فایل برای ذخیره لیست ادمین‌ها
ADMINS_FILE = "admins.pkl"

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
            [InlineKeyboardButton("افزودن ادمین جدید➕", callback_data="add_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")]
        ])

        text = "**لیست ادمین های ثبت شده در ربات👇👇**\n\nدر حال حاضر هیچ ادمینی ثبت نشده است."
    else:
        # ایجاد کیبورد برای ادمین‌ها
        keyboard_buttons = []
        for admin_id, admin_info in display_admins.items():
            # کوتاه کردن نام اگر طولانی باشد
            name_display = admin_info['name']
            if len(name_display) > 15:
                name_display = name_display[:12] + "..."

            # دکمه تنظیمات برای هر ادمین
            keyboard_buttons.append([
                InlineKeyboardButton(f"⚙️ {name_display}", callback_data=f"admin_settings_{admin_id}")
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

async def show_admin_settings(bot: Client, admin_id: int, callback_query: CallbackQuery):
    """نمایش تنظیمات ادمین با دکمه‌های edit_message_reply_markup"""
    admin_info = admins_data.get(admin_id)
    if not admin_info:
        await callback_query.answer("❌ ادمین یافت نشد!", show_alert=True)
        return

    # دریافت دسترسی‌های فعلی
    current_permissions = admin_info.get('permissions', [])

    # ایجاد متن وضعیت دسترسی‌ها
    permissions_status = ""
    for perm_key, perm_name in PERMISSIONS_LIST:
        has_perm = 'all' in current_permissions or perm_key in current_permissions
        status_icon = "✅" if has_perm else "❌"
        permissions_status += f"{status_icon} {perm_name}\n"

    text = (
        f"**تنظیمات دسترسی های ادمین**\n\n"
        f"👤 **نام:** {admin_info['name']}\n"
        f"📱 **یوزرنیم:** @{admin_info['username']}\n"
        f"🆔 **آیدی:** `{admin_id}`\n\n"
        f"**وضعیت دسترسی‌ها:**\n{permissions_status}\n"
        "برای تغییر دسترسی‌ها از دکمه‌های زیر استفاده کنید:"
    )

    # ایجاد دکمه‌های مدیریت دسترسی
    permission_buttons = [
        [InlineKeyboardButton("🎯 فعال کردن همه دسترسی‌ها", callback_data=f"perm_all_{admin_id}")],
        [InlineKeyboardButton("🚫 غیرفعال کردن همه دسترسی‌ها", callback_data=f"perm_none_{admin_id}")]
    ]

    # اضافه کردن دکمه‌های کنترل
    permission_buttons.extend([
        [InlineKeyboardButton("🗑️ حذف ادمین", callback_data=f"admin_delete_confirm_{admin_id}")],
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
        elif data.startswith(("add_admin", "admin_", "perm_")):
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

    elif data.startswith("perm_all_"):
        # فعال کردن همه دسترسی‌ها
        admin_id = int(data.split('_')[2])
        
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return

        admin_info = admins_data.get(admin_id)
        if not admin_info:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)
            return

        admin_info['permissions'] = ['all']
        save_admins(admins_data)
        
        await update.answer("✅ همه دسترسی‌ها فعال شد", show_alert=True)
        # به‌روزرسانی صفحه با وضعیت جدید
        await show_admin_settings(bot, admin_id, update)

    elif data.startswith("perm_none_"):
        # غیرفعال کردن همه دسترسی‌ها
        admin_id = int(data.split('_')[2])
        
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return

        admin_info = admins_data.get(admin_id)
        if not admin_info:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)
            return

        admin_info['permissions'] = []
        save_admins(admins_data)
        
        await update.answer("🚫 همه دسترسی‌ها غیرفعال شد", show_alert=True)
        await show_admin_settings(bot, admin_id, update)

    elif data.startswith("admin_delete_confirm_"):
        # نمایش تأیید حذف ادمین
        admin_id = int(data.split('_')[3])
        admin_info = admins_data.get(admin_id)
        
        if not admin_info:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)
            return

        confirm_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admin_delete_{admin_id}"),
                InlineKeyboardButton("❌ خیر، بازگشت", callback_data=f"admin_settings_{admin_id}")
            ]
        ])
        
        await update.message.edit_text(
            f"⚠️ **آیا از حذف ادمین مطمئن هستید؟**\n\n"
            f"👤 نام: {admin_info['name']}\n"
            f"📱 یوزرنیم: @{admin_info['username']}\n\n"
            "این عمل قابل بازگشت نیست!",
            reply_markup=confirm_keyboard
        )

    elif data.startswith("admin_delete_"):
        # حذف ادمین
        admin_id = int(data.split('_')[2])
        
        if not has_permission(update.from_user.id, 'manage_admins'):
            await update.answer("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.", show_alert=True)
            return

        if admin_id in admins_data:
            del admins_data[admin_id]
            save_admins(admins_data)
            await update.answer("✅ ادمین با موفقیت حذف شد", show_alert=True)
            await show_admins_list(bot, callback_query=update)
        else:
            await update.answer("❌ ادمین یافت نشد!", show_alert=True)

    elif data.startswith("admin_settings_"):
        # نمایش تنظیمات ادمین
        admin_id = int(data.split('_')[2])
        await show_admin_settings(bot, admin_id, update)

# تابع ارسال پیام همگانی
async def start_broadcast(bot: Client, message: Message, broadcast_message: Message):
    """شروع ارسال پیام همگانی"""
    user_id = message.from_user.id
    
    try:
        # دریافت تمام کاربران از دیتابیس
        all_users = await db.get_all_users()
        
        broadcast_msg = await message.reply_text(
            "🔄 **در حال ارسال پیام همگانی...**\n"
            f"📊 تعداد کاربران: {len(all_users)}\n"
            "⏳ لطفاً منتظر بمانید..."
        )
        
        start_time = time.time()
        total_users = len(all_users)
        done = 0
        failed = 0
        success = 0
        
        # ذخیره اطلاعات برادکست
        broadcast_id = int(time.time() * 1000)
        broadcast_ids[broadcast_id] = {
            'total': total_users,
            'done': done,
            'failed': failed,
            'success': success
        }
        
        # ارسال پیام به کاربران
        for user in all_users:
            user_id_str = str(user['id'])
            
            try:
                # کپی پیام اصلی و ارسال به کاربر
                if broadcast_message.text:
                    await bot.send_message(
                        chat_id=int(user_id_str),
                        text=broadcast_message.text
                    )
                elif broadcast_message.photo:
                    await bot.send_photo(
                        chat_id=int(user_id_str),
                        photo=broadcast_message.photo.file_id,
                        caption=broadcast_message.caption if broadcast_message.caption else ""
                    )
                elif broadcast_message.video:
                    await bot.send_video(
                        chat_id=int(user_id_str),
                        video=broadcast_message.video.file_id,
                        caption=broadcast_message.caption if broadcast_message.caption else ""
                    )
                elif broadcast_message.document:
                    await bot.send_document(
                        chat_id=int(user_id_str),
                        document=broadcast_message.document.file_id,
                        caption=broadcast_message.caption if broadcast_message.caption else ""
                    )
                
                success += 1
                
            except Exception as e:
                failed += 1
                print(f"Failed to send to {user_id_str}: {e}")
            
            done += 1
            
            # به‌روزرسانی وضعیت هر 10 کاربر
            if done % 10 == 0:
                try:
                    await broadcast_msg.edit_text(
                        f"🔄 **در حال ارسال پیام همگانی...**\n\n"
                        f"📊 کل کاربران: {total_users}\n"
                        f"✅ موفق: {success}\n"
                        f"❌ ناموفق: {failed}\n"
                        f"📤 ارسال شده: {done}\n"
                        f"⏳ باقی‌مانده: {total_users - done}"
                    )
                except:
                    pass
            
            # تأخیر کوچک برای جلوگیری از اسپم
            await asyncio.sleep(0.1)
        
        # محاسبه زمان انجام
        time_taken = int(time.time() - start_time)
        
        # پیام نهایی
        await broadcast_msg.edit_text(
            f"✅ **ارسال پیام همگانی تکمیل شد!**\n\n"
            f"📊 کل کاربران: {total_users}\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {failed}\n"
            f"⏱️ زمان انجام: {time_taken} ثانیه"
        )
        
        # حذف حالت کاربر
        if user_id in user_states:
            del user_states[user_id]
            
        # بازگشت به پنل مدیریت
        await message.reply_text(
            "🏠 به صفحه اصلی بازگشتید",
            reply_markup=ADMIN_KEYBOARD
        )
        
    except Exception as e:
        await message.reply_text(f"❌ خطا در ارسال پیام همگانی: {str(e)}")
        if user_id in user_states:
            del user_states[user_id]