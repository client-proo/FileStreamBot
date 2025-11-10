import os
import time
import string
import random
import asyncio
import aiofiles
import datetime

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram, Server
from pyrogram import filters, Client
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums.parse_mode import ParseMode

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# وضعیت ربات
bot_status = True

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
        "🛠 **پنل مدیریت ادمین**\n\n"
        "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=ADMIN_KEYBOARD
    )

@FileStream.on_message(filters.private & filters.text & filters.user(Telegram.OWNER_ID))
async def admin_buttons_handler(bot: Client, message: Message):
    global bot_status

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
        await message.reply_text(
            "📨 **ارسال پیام همگانی**\n\n"
            "پیام مد نظرت را ریپلای کن.\n"
            "❕ برای لغو: /cancel",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 بازگشت")]], resize_keyboard=True)
        )

    elif message.text == "⚙️ تنظیمات":
        settings_text = (
            "⚙️ **تنظیمات ربات**\n\n"
            f"⏰ زمان انقضای لینک‌ها: `{Telegram.EXPIRE_TIME} ثانیه`\n"
            f"🚫 ضد اسپم: `{Telegram.ANTI_SPAM_TIME} ثانیه`\n"
            f"📢 عضویت اجباری: `{'فعال' if Telegram.FORCE_SUB else 'غیرفعال'}`\n"
            f"🔌 وضعیت ربات: `{'🟢 روشن' if bot_status else '🔴 خاموش'}`"
        )

        await message.reply_text(settings_text, reply_markup=ADMIN_KEYBOARD)

    elif message.text == "🔴 خاموش/روشن کردن ربات":

        bot_status = not bot_status

        if bot_status:
            status_text = "🟢 **ربات روشن شد**\n\nکاربران اکنون می‌توانند از ربات استفاده کنند."
        else:
            status_text = "🔴 **ربات خاموش شد**\n\nکاربران دیگر نمی‌توانند فایل‌ها را دریافت کنند."

        await message.reply_text(status_text, reply_markup=ADMIN_KEYBOARD)

    elif message.text == "🔙 بازگشت":
        await message.reply_text("🔙 برگشتیم ✅", reply_markup=ADMIN_KEYBOARD)

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    await m.reply_text(f"""**👥 کاربران:** `{await db.total_users_count()}`
**🚫 مسدودی‌ها:** `{await db.total_banned_users_count()}`
**📁 تعداد فایل‌ها:** `{await db.total_files()}`""")

@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(b, m: Message):
    id = m.text.split("/ban ")[-1]
    if not await db.is_user_banned(int(id)):
        try:
            await db.ban_user(int(id))
            await db.delete_user(int(id))
            await m.reply_text(f"`{id}` مسدود شد ✅")
            if not str(id).startswith('-100'):
                await b.send_message(id, "حساب شما مسدود شد.")
        except Exception as e:
            await m.reply_text(f"خطا: {e}")
    else:
        await m.reply_text(f"`{id}` قبلا مسدود شده است ✅")

@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(b, m: Message):
    id = m.text.split("/unban ")[-1]
    if await db.is_user_banned(int(id)):
        try:
            await db.unban_user(int(id))
            await m.reply_text(f"`{id}` رفع مسدودی شد ✅")
        except Exception as e:
            await m.reply_text(f"خطا: {e}")
    else:
        await m.reply_text(f"`{id}` مسدود نبود ❗")

def is_bot_active():
    return bot_status