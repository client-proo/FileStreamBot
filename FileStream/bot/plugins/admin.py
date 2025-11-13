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

# فایل برای ذخیره وضعیت ربات
BOT_STATUS_FILE = "bot_status.pkl"
# فایل برای ذخیره لیست ادمین‌ها  
ADMINS_FILE = "admins.pkl"

# حالت‌های کاربران
user_states = {}
broadcast_ids = {}

# --- توابع پایه ---
def load_bot_status():
    try:
        if Path(BOT_STATUS_FILE).exists():
            with open(BOT_STATUS_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    return True

def save_bot_status(status):
    try:
        with open(BOT_STATUS_FILE, 'wb') as f:
            pickle.dump(status, f)
    except Exception as e:
        print(f"Error saving bot status: {e}")

def load_admins():
    try:
        if Path(ADMINS_FILE).exists():
            with open(ADMINS_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
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
    try:
        with open(ADMINS_FILE, 'wb') as f:
            pickle.dump(admins, f)
    except Exception as e:
        print(f"Error saving admins: {e}")

# --- داده‌های جهانی ---
bot_status = load_bot_status()
admins_data = load_admins()

# --- توابع کمکی ---
def is_admin(user_id: int) -> bool:
    return user_id == Telegram.OWNER_ID or user_id in admins_data

def has_permission(user_id: int, permission: str) -> bool:
    if user_id == Telegram.OWNER_ID:
        return True
    admin_info = admins_data.get(user_id)
    if not admin_info:
        return False
    permissions = admin_info.get('permissions', [])
    return 'all' in permissions or permission in permissions

def require_permission(permission: str):
    def decorator(func):
        async def wrapper(client, message):
            if not has_permission(message.from_user.id, permission):
                await message.reply_text("❌ شما دسترسی به این قابلیت را ندارید.")
                return
            return await func(client, message)
        return wrapper
    return decorator

# --- کیبورد اصلی ---
ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 مشاهده فایل ها و آمار"), KeyboardButton("🔊 ارسال پیام همگانی")],
        [KeyboardButton("⚙️ تنظیمات"), KeyboardButton("🔴 خاموش/روشن کردن ربات")]
    ],
    resize_keyboard=True,
    selective=True
)

# --- هندلرهای اصلی ---
@FileStream.on_message(filters.command("panel") & filters.private)
async def admin_panel_handler(bot: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ شما دسترسی به پنل مدیریت ندارید.")
        return
    await message.reply_text(
        "🏠 **صفحه اصلی**\n\nلطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=ADMIN_KEYBOARD
    )

@FileStream.on_message(filters.private)
async def admin_message_handler(bot: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
        
    user_id = message.from_user.id
    
    # حالت ارسال همگانی
    if user_id in user_states and user_states[user_id] == "awaiting_broadcast":
        if message.text == "🔙 بازگشت":
            del user_states[user_id]
            await message.reply_text("🏠 به صفحه اصلی بازگشتید", reply_markup=ADMIN_KEYBOARD)
            return
        
        if not has_permission(user_id, 'broadcast'):
            await message.reply_text("❌ شما دسترسی به ارسال پیام همگانی ندارید.")
            del user_states[user_id]
            await message.reply_text("🏠 به صفحه اصلی بازگشتید", reply_markup=ADMIN_KEYBOARD)
            return
        
        await start_broadcast(bot, message, message)
        return

    # حالت افزودن ادمین
    if user_id in user_states and user_states[user_id] == "adding_admin":
        if message.text and message.text == "/cancel":
            del user_states[user_id]
            await message.reply_text("❌ عملیات افزودن ادمین لغو شد.", reply_markup=ADMIN_KEYBOARD)
            return
        await process_add_admin(bot, message)
        return

    # پردازش دکمه‌های کیبورد
    if message.text == "📊 مشاهده فایل ها و آمار":
        if not has_permission(user_id, 'view_stats'):
            await message.reply_text("❌ شما دسترسی به مشاهده آمار را ندارید.")
            return
        await show_stats(bot, message)
    
    elif message.text == "🔊 ارسال پیام همگانی":
        if not has_permission(user_id, 'broadcast'):
            await message.reply_text("❌ شما دسترسی به ارسال پیام همگانی ندارید.")
            return
        user_states[user_id] = "awaiting_broadcast"
        await message.reply_text(
            "📨 **ارسال پیام همگانی**\n\nپیام خود را ارسال کنید...",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 بازگشت")]], resize_keyboard=True)
        )
    
    elif message.text == "⚙️ تنظیمات":
        await show_settings(bot, message)
    
    elif message.text == "🔴 خاموش/روشن کردن ربات":
        if not has_permission(user_id, 'toggle_bot'):
            await message.reply_text("❌ شما دسترسی به خاموش/روشن کردن ربات را ندارید.")
            return
        await toggle_bot(bot, message)
    
    elif message.text == "🔙 بازگشت":
        if user_id in user_states:
            del user_states[user_id]
        await message.reply_text("🏠 به صفحه اصلی بازگشتید", reply_markup=ADMIN_KEYBOARD)

# --- توابع کمکی ---
async def show_stats(bot: Client, message: Message):
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

async def show_settings(bot: Client, message: Message):
    settings_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ادمین ها👥", callback_data="settings_admins")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")]
    ])
    
    settings_text = (
        "⚙️ **تنظیمات ربات**\n\n"
        f"⏰ زمان انقضای لینک‌ها: `{Telegram.EXPIRE_TIME} ثانیه`\n"
        f"🔌 وضعیت ربات: `{'🟢 روشن' if bot_status else '🔴 خاموش'}`\n\n"
        "**یکی از گزینه های زیر را انتخاب کنید👇👇**"
    )
    await message.reply_text(settings_text, reply_markup=settings_keyboard)

async def toggle_bot(bot: Client, message: Message):
    global bot_status
    bot_status = not bot_status
    save_bot_status(bot_status)
    
    if bot_status:
        status_text = "🟢 **ربات روشن شد**\n\nکاربران اکنون می‌توانند فایل‌ها را دریافت کنند."
    else:
        status_text = "🔴 **ربات خاموش شد**\n\nکاربران دیگر نمی‌توانند فایل‌ها را دریافت کنند."
    await message.reply_text(status_text, reply_markup=ADMIN_KEYBOARD)

# --- مدیریت ادمین‌ها ---
async def process_add_admin(bot: Client, message: Message):
    user_id = message.from_user.id
    if not has_permission(user_id, 'manage_admins'):
        await message.reply_text("❌ شما دسترسی به مدیریت ادمین‌ها را ندارید.")
        del user_states[user_id]
        return
        
    target_user = None
    try:
        if message.forward_from:
            target_user = message.forward_from
        elif message.text and message.text.startswith('@'):
            username = message.text[1:].strip()
            target_user = await bot.get_users(username)
        elif message.text and message.text.strip().replace(' ', '').isdigit():
            user_id_str = message.text.strip().replace(' ', '')
            target_user = await bot.get_users(int(user_id_str))
        else:
            await message.reply_text("❌ لطفاً یک روش معتبر برای افزودن ادمین استفاده کنید.")
            return
        
        if target_user:
            admins_data[target_user.id] = {
                'name': target_user.first_name or "بدون نام",
                'username': target_user.username or 'ندارد',
                'permissions': []
            }
            save_admins(admins_data)
            del user_states[user_id]
            
            success_text = (
                "✅ **ادمین با موفقیت افزوده شد.**\n\n"
                f"👤 **نام:** {target_user.first_name or 'بدون نام'}\n"
                f"🆔 **آیدی:** `{target_user.id}`"
            )
            await message.reply_text(success_text)
            await show_admins_list(bot, message=message)
            
    except Exception as e:
        await message.reply_text(f"❌ خطا در پردازش: {str(e)}")

async def show_admins_list(bot: Client, message: Message = None, callback_query: CallbackQuery = None):
    display_admins = {k: v for k, v in admins_data.items() if k != Telegram.OWNER_ID}
    
    if not display_admins:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ افزودن ادمین جدید", callback_data="add_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")]
        ])
        text = "**لیست ادمین‌ها**\n\nدر حال حاضر هیچ ادمینی ثبت نشده است."
    else:
        keyboard_buttons = []
        for admin_id, admin_info in display_admins.items():
            name_display = admin_info['name']
            if len(name_display) > 15:
                name_display = name_display[:12] + "..."
            keyboard_buttons.append([
                InlineKeyboardButton(str(admin_id), callback_data=f"admin_info_{admin_id}"),
                InlineKeyboardButton(name_display, callback_data=f"admin_info_{admin_id}"),
                InlineKeyboardButton("⚙", callback_data=f"admin_settings_{admin_id}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("➕ افزودن ادمین جدید", callback_data="add_admin")])
        keyboard_buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_back")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        text = "**لیست ادمین‌ها**"
    
    if message:
        await message.reply_text(text, reply_markup=keyboard)
    elif callback_query:
        await callback_query.message.edit_text(text, reply_markup=keyboard)

# --- Toggle Inline Keyboard برای دسترسی‌ها ---
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
    admin_info = admins_data.get(admin_id)
    if not admin_info:
        await callback_query.answer("❌ ادمین یافت نشد!", show_alert=True)
        return
    
    current_permissions = admin_info.get('permissions', [])
    
    text = (
        f"**تنظیمات دسترسی ادمین**\n\n"
        f"👤 **نام:** {admin_info['name']}\n"
        f"🆔 **آیدی:** `{admin_id}`\n\n"
        "**دسترسی‌ها:**"
    )
    
    # ایجاد دکمه‌های Toggle با ✅/❌
    permission_buttons = []
    for perm_key, perm_name in PERMISSIONS_LIST:
        has_perm = 'all' in current_permissions or perm_key in current_permissions
        icon = "✅" if has_perm else "❌"
        button_text = f"{icon} {perm_name}"
        permission_buttons.append([
            InlineKeyboardButton(button_text, callback_data=f"perm_toggle_{admin_id}_{perm_key}")
        ])
    
    permission_buttons.extend([
        [InlineKeyboardButton("🎯 فعال کردن همه", callback_data=f"perm_all_{admin_id}")],
        [InlineKeyboardButton("🚫 غیرفعال کردن همه", callback_data=f"perm_none_{admin_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_admins")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(permission_buttons))

# --- هندلرهای Callback ---
@FileStream.on_callback_query()
async def callback_handler(bot: Client, update: CallbackQuery):
    if not is_admin(update.from_user.id):
        await update.answer("❌ دسترسی denied", show_alert=True)
        return
        
    data = update.data
    
    try:
        if data == "settings_admins":
            if not has_permission(update.from_user.id, 'manage_admins'):
                await update.answer("❌ دسترسی denied", show_alert=True)
                return
            await show_admins_list(bot, callback_query=update)
        
        elif data == "settings_back":
            await update.message.edit_text(
                "🏠 **صفحه اصلی**\n\nلطفا یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=ADMIN_KEYBOARD
            )
        
        elif data == "add_admin":
            if not has_permission(update.from_user.id, 'manage_admins'):
                await update.answer("❌ دسترسی denied", show_alert=True)
                return
            user_states[update.from_user.id] = "adding_admin"
            await update.message.edit_text(
                "➕ **افزودن ادمین جدید**\n\nیک پیام از کاربر فوروارد کنید یا آیدی/یوزرنیم ارسال کنید."
            )
        
        elif data.startswith("admin_settings_"):
            admin_id = int(data.split("_")[2])
            await show_admin_settings(bot, admin_id, update)
        
        elif data.startswith("perm_toggle_"):
            parts = data.split("_")
            admin_id = int(parts[2])
            permission = parts[3]
            
            if admin_id in admins_data:
                admin_info = admins_data[admin_id]
                permissions = admin_info.get('permissions', [])
                
                if permission in permissions:
                    permissions.remove(permission)
                else:
                    permissions.append(permission)
                
                admin_info['permissions'] = permissions
                save_admins(admins_data)
                await show_admin_settings(bot, admin_id, update)
                await update.answer("✅ وضعیت تغییر کرد!", show_alert=True)
        
        elif data.startswith("perm_all_"):
            admin_id = int(data.split("_")[2])
            if admin_id in admins_data:
                admin_info = admins_data[admin_id]
                admin_info['permissions'] = [perm[0] for perm in PERMISSIONS_LIST]
                save_admins(admins_data)
                await show_admin_settings(bot, admin_id, update)
                await update.answer("✅ همه دسترسی‌ها فعال شد!", show_alert=True)
        
        elif data.startswith("perm_none_"):
            admin_id = int(data.split("_")[2])
            if admin_id in admins_data:
                admin_info = admins_data[admin_id]
                admin_info['permissions'] = []
                save_admins(admins_data)
                await show_admin_settings(bot, admin_id, update)
                await update.answer("✅ همه دسترسی‌ها غیرفعال شد!", show_alert=True)
                
    except Exception as e:
        await update.answer("❌ خطا در پردازش", show_alert=True)

# --- تابع broadcast ---
async def start_broadcast(bot: Client, message: Message, broadcast_msg: Message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    await message.reply_text("🔄 در حال ارسال...")
    
    all_users = await db.get_all_users()
    total_users = await db.total_users_count()
    done, success, failed = 0, 0, 0
    
    async for user in all_users:
        try:
            await broadcast_msg.copy(chat_id=int(user['id']))
            success += 1
        except Exception:
            failed += 1
        done += 1
        
        if done % 10 == 0:
            await message.edit_text(f"📤 ارسال... {done}/{total_users}")
    
    await message.reply_text(
        f"✅ ارسال همگانی تکمیل شد!\n✅ موفق: {success}\n❌ ناموفق: {failed}",
        reply_markup=ADMIN_KEYBOARD
    )

# --- دستورات ---
@FileStream.on_message(filters.command("status") & filters.private)
@require_permission('view_stats')
async def status_handler(c: Client, m: Message):
    total_users = await db.total_users_count()
    total_files = await db.total_files()
    await m.reply_text(f"👥 کاربران: {total_users}\n📁 فایل‌ها: {total_files}")

@FileStream.on_message(filters.command("broadcast") & filters.private & filters.reply)
@require_permission('broadcast')
async def broadcast_cmd_handler(c, m):
    await start_broadcast(c, m, m.reply_to_message)

# --- تابع اصلی برای export ---
def is_bot_active():
    return bot_status