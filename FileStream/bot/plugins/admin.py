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

# وضعیت ربات (در حافظه)
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
    bot_status = not bot_status
    
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
            "لطفا پیام مورد نظر خود را به عنوان ریپلای ارسال کنید...\n\n"
            "❕ برای لغو عملیات از دستور /cancel استفاده کنید.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 بازگشت")]], resize_keyboard=True)
        )
    
    elif message.text == "⚙️ تنظیمات":
        settings_text = (
            "⚙️ **تنظیمات ربات**\n\n"
            f"⏰ زمان انقضای لینک‌ها: `{Telegram.EXPIRE_TIME} ثانیه`\n"
            f"🚫 زمان ضد اسپم: `{Telegram.ANTI_SPAM_TIME} ثانیه`\n"
            f"👥 کاربران مجاز: `{len(Telegram.AUTH_USERS) if Telegram.AUTH_USERS else 'همه'}`\n"
            f"📢 عضویت اجباری: `{'فعال' if Telegram.FORCE_SUB else 'غیرفعال'}`\n"
            f"🔌 وضعیت ربات: `{'🟢 روشن' if bot_status else '🔴 خاموش'}`"
        )
        
        await message.reply_text(settings_text, reply_markup=ADMIN_KEYBOARD)
    
    elif message.text == "🔴 خاموش/روشن کردن ربات":
        global bot_status
        bot_status = not bot_status
        
        if bot_status:
            status_text = "🟢 **ربات روشن شد**\n\nکاربران اکنون می‌توانند فایل‌ها را دریافت کنند."
        else:
            status_text = "🔴 **ربات خاموش شد**\n\nکاربران دیگر نمی‌توانند فایل‌ها را دریافت کنند."
        
        await message.reply_text(status_text, reply_markup=ADMIN_KEYBOARD)
    
    elif message.text == "🔙 بازگشت":
        await message.reply_text(
            "🔙 **بازگشت به صفحه اصلی**",
            reply_markup=ADMIN_KEYBOARD
        )

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
async def broadcast_(c, m):
    all_users = await db.get_all_users()
    broadcast_msg = m.reply_to_message
    while True:
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(3)])
        if not broadcast_ids.get(broadcast_id):
            break
    out = await m.reply_text(
        text=f"Broadcast initiated! You will be notified with log file when all the users are notified."
    )
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
    async with aiofiles.open('broadcast.txt', 'w') as broadcast_log_file:
        async for user in all_users:
            sts, msg = await send_msg(
                user_id=int(user['id']),
                message=broadcast_msg
            )
            if msg is not None:
                await broadcast_log_file.write(msg)
            if sts == 200:
                success += 1
            else:
                failed += 1
            if sts == 400:
                await db.delete_user(user['id'])
            done += 1
            if broadcast_ids.get(broadcast_id) is None:
                break
            else:
                broadcast_ids[broadcast_id].update(
                    dict(
                        current=done,
                        failed=failed,
                        success=success
                    )
                )
                try:
                    await out.edit_text(f"Broadcast Status\n\ncurrent: {done}\nfailed:{failed}\nsuccess: {success}")
                except:
                    pass
    if broadcast_ids.get(broadcast_id):
        broadcast_ids.pop(broadcast_id)
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await asyncio.sleep(3)
    await out.delete()
    if failed == 0:
        await m.reply_text(
            text=f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed.",
            quote=True
        )
    else:
        await m.reply_document(
            document='broadcast.txt',
            caption=f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed.",
            quote=True
        )
    os.remove('broadcast.txt')


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

# تابع برای چک کردن وضعیت ربات (برای استفاده در سایر فایل‌ها)
def is_bot_active():
    return bot_status