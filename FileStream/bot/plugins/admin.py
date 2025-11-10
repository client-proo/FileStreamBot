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

# وضعیت ربات
bot_status = load_bot_status()

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

@FileStream.on_message(filters.command("panel") & filters.private & filters.user(Telegram.OWNER_ID))
async def admin_panel_handler(bot: Client, message: Message):
    await message.reply_text(
        "🏠 **صفحه اصلی**\n\n"
        "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=ADMIN_KEYBOARD
    )

@FileStream.on_message(filters.private & filters.user(Telegram.OWNER_ID))
async def admin_message_handler(bot: Client, message: Message):
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
        
        # ارسال مستقیم پیام (بدون نیاز به ریپلای)
        await start_broadcast(bot, message, message)
        return

    # پردازش دکمه‌های کیبورد
    if message.text == "📊 مشاهده فایل ها و آمار":
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

# هندلر برای callback_query های تنظیمات
@FileStream.on_callback_query(filters.regex("^settings_"))
async def settings_callback_handler(bot: Client, update: CallbackQuery):
    data = update.data
    
    if data == "settings_force_sub":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_admins":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_users_list":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_banned_list":
        await update.answer("🔄 این قابلیت به زودی اضافه خواهد شد", show_alert=True)
    
    elif data == "settings_back":
        await update.message.edit_text(
            "🏠 **صفحه اصلی**\n\n"
            "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=ADMIN_KEYBOARD
        )

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

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    await m.reply_text(text=f"""**👥 کل کاربران:** `{await db.total_users_count()}`
**🚫 کاربران مسدود شده:** `{await db.total_banned_users_count()}`
**🔗 لینک‌های تولید شده: ** `{await db.total_files()}`"""
                       , parse_mode=ParseMode.MARKDOWN, quote=True)

@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
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

@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
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

@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID) & filters.reply)
async def broadcast_command_handler(c, m):
    """هندلر برای دستور /broadcast با ریپلای"""
    await start_broadcast(c, m, m.reply_to_message)

@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
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