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
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}


@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    total_premium = len(await db.get_premium_users())
    await m.reply_text(text=f"""**👥 کل کاربران:** `{await db.total_users_count()}`
**👑 کاربران پرمیوم:** `{total_premium}`
**🚫 کاربران مسدود شده:** `{await db.total_banned_users_count()}`
**🔗 لینک‌های تولید شده: ** `{await db.total_files()}`
**🔒 حالت فقط پرمیوم:** `{'فعال ✅' if Telegram.ONLY_PREMIUM else 'غیرفعال ❌'}`"""
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

# ==================== PREMIUM MANAGEMENT ====================

@FileStream.on_message(filters.command("setpremium") & filters.private & filters.user(Telegram.OWNER_ID))
async def set_premium_handler(bot: Client, message: Message):
    try:
        # فرمت دستور: /setpremium user_id seconds
        parts = message.text.split()
        if len(parts) != 3:
            await message.reply_text(
                "❌ فرمت دستور نادرست است.\n\n"
                "✅ استفاده صحیح:\n"
                "`/setpremium user_id seconds`\n\n"
                "📝 مثال:\n"
                "`/setpremium 123456789 2592000`\n"
                "(30 روز پرمیوم)",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        user_id = int(parts[1])
        seconds = int(parts[2])

        # بررسی وجود کاربر
        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "❌ کاربر در دیتابیس یافت نشد!",
                quote=True
            )
            return

        # تنظیم کاربر به عنوان پرمیوم
        await db.set_premium_user(user_id, seconds, message.from_user.id)
        
        # محاسبه زمان انقضا
        expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        expiry_str = expiry_time.strftime("%Y/%m/%d - %H:%M:%S")
        
        await message.reply_text(
            f"✅ کاربر `{user_id}` با موفقیت پرمیوم شد!\n\n"
            f"⏰ زمان انقضا: `{expiry_str}`\n"
            f"⏳ مدت زمان: `{seconds}` ثانیه",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

        # اطلاع به کاربر (اگر امکان داشته باشد)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 **تبریک! شما اکنون کاربر پرمیوم هستید!**\n\n"
                     f"⏰ پرمیوم شما تا `{expiry_str}` فعال خواهد بود.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass  # اگر نتوانستیم به کاربر پیام بدهیم، مشکلی نیست

    except ValueError:
        await message.reply_text(
            "❌ آیدی کاربر یا زمان باید عدد باشد!",
            quote=True
        )
    except Exception as e:
        await message.reply_text(
            f"❌ خطا در اجرای دستور: {str(e)}",
            quote=True
        )

@FileStream.on_message(filters.command("premiumusers") & filters.private & filters.user(Telegram.OWNER_ID))
async def premium_users_handler(bot: Client, message: Message):
    try:
        premium_users = await db.get_premium_users()
        
        if not premium_users:
            await message.reply_text(
                "📭 هیچ کاربر پرمیومی وجود ندارد.",
                quote=True
            )
            return

        from FileStream.utils.bot_utils import seconds_to_hms
        
        text = "👑 **لیست کاربران پرمیوم:**\n\n"
        
        for user in premium_users:
            user_id = user['id']
            expiry_time = user['premium_expiry']
            added_by = user.get('premium_added_by', 'نامشخص')
            
            # تبدیل زمان به فرمت خوانا
            expiry_date = datetime.datetime.fromtimestamp(expiry_time).strftime("%Y/%m/%d - %H:%M:%S")
            
            # محاسبه زمان باقی‌مانده
            remaining = expiry_time - time.time()
            remaining_readable = seconds_to_hms(int(remaining))
            
            text += f"🆔 کاربر: `{user_id}`\n"
            text += f"⏰ انقضا: `{expiry_date}`\n"
            text += f"⏳ باقی‌مانده: `{remaining_readable}`\n"
            text += f"👤 اضافه شده توسط: `{added_by}`\n"
            text += "─" * 30 + "\n"

        await message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

    except Exception as e:
        await message.reply_text(
            f"❌ خطا در دریافت لیست کاربران پرمیوم: {str(e)}",
            quote=True
        )

@FileStream.on_message(filters.command("onlypremium") & filters.private & filters.user(Telegram.OWNER_ID))
async def only_premium_handler(bot: Client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.reply_text(
                "❌ فرمت دستور نادرست است.\n\n"
                "✅ استفاده صحیح:\n"
                "`/onlypremium on` - فعال کردن حالت فقط پرمیوم\n"
                "`/onlypremium off` - غیرفعال کردن حالت فقط پرمیوم",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        mode = parts[1].lower()
        if mode in ['on', 'true', '1']:
            Telegram.ONLY_PREMIUM = True
            status = "فعال ✅"
        elif mode in ['off', 'false', '0']:
            Telegram.ONLY_PREMIUM = False
            status = "غیرفعال ❌"
        else:
            await message.reply_text(
                "❌ حالت نامعتبر! از 'on' یا 'off' استفاده کنید.",
                quote=True
            )
            return

        await message.reply_text(
            f"✅ حالت 'فقط پرمیوم' {status} شد.\n\n"
            f"📊 کاربران پرمیوم فعال: `{len(await db.get_premium_users())}` نفر",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

    except Exception as e:
        await message.reply_text(
            f"❌ خطا در تغییر حالت: {str(e)}",
            quote=True
        )