import os
import time
import string
import random
import asyncio
import aiofiles
import datetime
import pytz
from jdatetime import datetime as jdatetime

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
    await m.reply_text(
        text=f"""**📊 وضعیت ربات:**

👥 **کل کاربران:** `{await db.total_users_count()}`
👑 **کاربران پرمیوم:** `{total_premium}`
🚫 **کاربران مسدود شده:** `{await db.total_banned_users_count()}`
🔗 **لینک‌های تولید شده:** `{await db.total_files()}`
🔒 **حالت فقط پرمیوم:** `{'فعال ✅' if Telegram.ONLY_PREMIUM else 'غیرفعال ❌'}`""",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )


@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
async def ban_handler(b, m: Message):
    try:
        id = m.text.split("/ban ")[-1]
        if not await db.is_user_banned(int(id)):
            await db.ban_user(int(id))
            await db.delete_user(int(id))
            await m.reply_text(
                text=f"✅ کاربر `{id}` مسدود شد.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            if not str(id).startswith('-100'):
                try:
                    await b.send_message(
                        chat_id=id,
                        text="**حساب کاربری شما مسدود شده است**",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        else:
            await m.reply_text(
                text=f"⚠️ کاربر `{id}` قبلاً مسدود شده است.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
    except Exception as e:
        await m.reply_text(
            text=f"❌ خطا در مسدود کردن کاربر: {str(e)}",
            quote=True
        )


@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
async def unban_handler(b, m: Message):
    try:
        id = m.text.split("/unban ")[-1]
        if await db.is_user_banned(int(id)):
            await db.unban_user(int(id))
            await m.reply_text(
                text=f"✅ مسدودیت کاربر `{id}` برداشته شد.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            if not str(id).startswith('-100'):
                try:
                    await b.send_message(
                        chat_id=id,
                        text="**مسدودیت شما برداشته شد. می‌توانید از ربات استفاده کنید**",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        else:
            await m.reply_text(
                text=f"⚠️ کاربر `{id}` مسدود نشده است.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
    except Exception as e:
        await m.reply_text(
            text=f"❌ خطا در برداشتن مسدودیت: {str(e)}",
            quote=True
        )


@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID) & filters.reply)
async def broadcast_handler(c, m):
    all_users = await db.get_all_users()
    broadcast_msg = m.reply_to_message
    
    while True:
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(3)])
        if not broadcast_ids.get(broadcast_id):
            break
    
    out = await m.reply_text("📢 آغاز ارسال همگانی...")
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
                    await out.edit_text(f"📊 وضعیت ارسال:\n\nارسال شده: {done}\nموفق: {success}\nناموفق: {failed}")
                except:
                    pass
    
    if broadcast_ids.get(broadcast_id):
        broadcast_ids.pop(broadcast_id)
    
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await asyncio.sleep(3)
    await out.delete()
    
    if failed == 0:
        await m.reply_text(
            text=f"✅ ارسال همگانی با موفقیت انجام شد.\n\n⏱️ زمان: `{completed_in}`\n👥 کاربران: `{total_users}`\n✅ موفق: `{success}`\n❌ ناموفق: `{failed}`",
            quote=True
        )
    else:
        await m.reply_document(
            document='broadcast.txt',
            caption=f"✅ ارسال همگانی انجام شد.\n\n⏱️ زمان: `{completed_in}`\n👥 کاربران: `{total_users}`\n✅ موفق: `{success}`\n❌ ناموفق: `{failed}`",
            quote=True
        )
    os.remove('broadcast.txt')


@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def delete_file_handler(c: Client, m: Message):
    try:
        file_id = m.text.split(" ")[-1]
        file_info = await db.get_file(file_id)
        await db.delete_one_file(file_info['_id'])
        await db.count_links(file_info['user_id'], "-")
        await m.reply_text(
            text="✅ فایل با موفقیت حذف شد!",
            quote=True
        )
    except FIleNotFound:
        await m.reply_text(
            text="⚠️ فایل قبلاً حذف شده است.",
            quote=True
        )
    except Exception as e:
        await m.reply_text(
            text=f"❌ خطا در حذف فایل: {str(e)}",
            quote=True
        )


@FileStream.on_message(filters.command("setpremium") & filters.private & filters.user(Telegram.OWNER_ID))
async def set_premium_handler(bot: Client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.reply_text(
                "❌ **فرمت دستور نادرست است.**\n\n"
                "✅ **استفاده صحیح:**\n"
                "`/setpremium [آیدی کاربر] [زمان به ثانیه]`\n\n"
                "📝 **مثال:**\n"
                "`/setpremium 123456789 2592000`\n"
                "(30 روز پرمیوم - 2,592,000 ثانیه)",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        user_id = int(parts[1])
        seconds = int(parts[2])

        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "❌ کاربر در دیتابیس یافت نشد!",
                quote=True
            )
            return

        await db.set_premium_user(user_id, seconds, message.from_user.id)
        
        tz_iran = pytz.timezone('Asia/Tehran')
        expiry_time = datetime.datetime.now(tz_iran) + datetime.timedelta(seconds=seconds)
        expiry_jalali = jdatetime.fromgregorian(datetime=expiry_time)
        
        # فرمت تاریخ شمسی کامل
        expiry_date = expiry_jalali.strftime('%Y/%m/%d - %H:%M:%S')
        year = expiry_jalali.year
        month = expiry_jalali.month
        day = expiry_jalali.day
        hour = expiry_jalali.hour
        minute = expiry_jalali.minute
        second = expiry_jalali.second
        
        # نام ماه شمسی
        month_names = {
            1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 
            4: "تیر", 5: "مرداد", 6: "شهریور",
            7: "مهر", 8: "آبان", 9: "آذر",
            10: "دی", 11: "بهمن", 12: "اسفند"
        }
        month_name = month_names.get(month, "نامشخص")
        
        from FileStream.utils.bot_utils import seconds_to_detailed
        duration_readable = seconds_to_detailed(seconds)
        
        await message.reply_text(
            f"✅ **کاربر با موفقیت پرمیوم شد!**\n\n"
            f"👤 **آیدی کاربر:** `{user_id}`\n"
            f"⏰ **جزئیات تاریخ انقضا:**\n"
            f"   ├ **سال:** `{year}`\n"
            f"   ├ **ماه:** `{month_name}`\n"
            f"   ├ **روز:** `{day}`\n"
            f"   ├ **ساعت:** `{hour:02d}`\n"
            f"   ├ **دقیقه:** `{minute:02d}`\n"
            f"   ├ **ثانیه:** `{second:02d}`\n"
            f"   └ **فرمت کامل:** `{expiry_date}`\n"
            f"⏳ **مدت زمان:** `{duration_readable}`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

        try:
            user_info = await bot.get_users(user_id)
            user_name = f"{user_info.first_name or ''} {user_info.last_name or ''}".strip()
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 **تبریک! شما اکنون کاربر پرمیوم هستید!**\n\n"
                     f"👤 **نام:** {user_name}\n"
                     f"⏰ **پرمیوم شما تا:** `{expiry_date}` فعال خواهد بود.\n"
                     f"📅 **جزئیات:** سال {year}، ماه {month_name}، روز {day}\n"
                     f"🕒 **ساعت:** {hour:02d}:{minute:02d}:{second:02d}\n"
                     f"✨ **از امکانات ویژه ربات لذت ببرید!**",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

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


@FileStream.on_message(filters.command("unpremium") & filters.private & filters.user(Telegram.OWNER_ID))
async def unpremium_handler(bot: Client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.reply_text(
                "❌ **فرمت دستور نادرست است.**\n\n"
                "✅ **استفاده صحیح:**\n"
                "`/unpremium [آیدی کاربر]`\n\n"
                "📝 **مثال:**\n"
                "`/unpremium 123456789`",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        user_id = int(parts[1])

        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "❌ کاربر در دیتابیس یافت نشد!",
                quote=True
            )
            return

        if not await db.is_premium_user(user_id):
            await message.reply_text(
                f"⚠️ کاربر `{user_id}` در حال حاضر پرمیوم نیست.",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        # لغو پرمیوم کاربر - بدون ارسال پیام به کاربر
        await db.remove_premium_user(user_id)

        await message.reply_text(
            f"✅ **پرمیوم کاربر با موفقیت لغو شد!**\n\n"
            f"👤 **آیدی کاربر:** `{user_id}`\n"
            f"📝 **توجه:** به کاربر پیامی ارسال نشد.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

    except ValueError:
        await message.reply_text(
            "❌ آیدی کاربر باید عدد باشد!",
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
                "📭 **هیچ کاربر پرمیومی وجود ندارد.**",
                quote=True
            )
            return

        from FileStream.utils.bot_utils import seconds_to_detailed
        
        text = "👑 **لیست کاربران پرمیوم**\n\n"
        counter = 1
        
        for user_data in premium_users:
            user_id = user_data['id']
            expiry_time = user_data['premium_expiry']
            added_by = user_data.get('premium_added_by', 'نامشخص')
            
            try:
                user_info = await bot.get_users(user_id)
                first_name = user_info.first_name or "بدون نام"
                last_name = user_info.last_name or ""
                username = f"@{user_info.username}" if user_info.username else "بدون یوزرنیم"
                full_name = f"{first_name} {last_name}".strip()
            except Exception:
                full_name = "نامشخص"
                username = "نامشخص"
            
            # تبدیل زمان به تاریخ شمسی ایران با جزئیات کامل
            tz_iran = pytz.timezone('Asia/Tehran')
            expiry_dt = datetime.datetime.fromtimestamp(expiry_time, tz_iran)
            expiry_jalali = jdatetime.fromgregorian(datetime=expiry_dt)
            
            # فرمت تاریخ شمسی کامل
            expiry_date = expiry_jalali.strftime('%Y/%m/%d - %H:%M:%S')
            year = expiry_jalali.year
            month = expiry_jalali.month
            day = expiry_jalali.day
            hour = expiry_jalali.hour
            minute = expiry_jalali.minute
            second = expiry_jalali.second
            
            # نام ماه شمسی
            month_names = {
                1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 
                4: "تیر", 5: "مرداد", 6: "شهریور",
                7: "مهر", 8: "آبان", 9: "آذر",
                10: "دی", 11: "بهمن", 12: "اسفند"
            }
            month_name = month_names.get(month, "نامشخص")
            
            remaining = expiry_time - time.time()
            remaining_readable = seconds_to_detailed(int(remaining))
            
            text += f"**{counter}. 👤 کاربر**\n"
            text += f"   ├ **نام:** {full_name}\n"
            text += f"   ├ **یوزرنیم:** {username}\n"
            text += f"   ├ **آیدی:** `{user_id}`\n"
            text += f"   ├ **تاریخ انقضا:**\n"
            text += f"   │   ├ **سال:** `{year}`\n"
            text += f"   │   ├ **ماه:** `{month_name}`\n"
            text += f"   │   ├ **روز:** `{day}`\n"
            text += f"   │   ├ **ساعت:** `{hour:02d}`\n"
            text += f"   │   ├ **دقیقه:** `{minute:02d}`\n"
            text += f"   │   └ **ثانیه:** `{second:02d}`\n"
            text += f"   ├ **فرمت کامل:** `{expiry_date}`\n"
            text += f"   ├ **باقی‌مانده:** `{remaining_readable}`\n"
            text += f"   └ **اضافه شده توسط:** `{added_by}`\n\n"
            
            counter += 1

        text += f"📊 **جمع کل:** {len(premium_users)} کاربر پرمیوم"
        
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
                "❌ **فرمت دستور نادرست است.**\n\n"
                "✅ **استفاده صحیح:**\n"
                "`/onlypremium on` - فعال کردن حالت فقط پرمیوم\n"
                "`/onlypremium off` - غیرفعال کردن حالت فقط پرمیوم",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        mode = parts[1].lower()
        if mode in ['on', 'true', '1', 'فعال']:
            Telegram.ONLY_PREMIUM = True
            status = "فعال ✅"
            status_emoji = "🔒"
        elif mode in ['off', 'false', '0', 'غیرفعال']:
            Telegram.ONLY_PREMIUM = False
            status = "غیرفعال ❌"
            status_emoji = "🔓"
        else:
            await message.reply_text(
                "❌ حالت نامعتبر! از 'on' یا 'off' استفاده کنید.",
                quote=True
            )
            return

        premium_count = len(await db.get_premium_users())
        
        await message.reply_text(
            f"{status_emoji} **حالت 'فقط پرمیوم' {status} شد.**\n\n"
            f"📊 **کاربران پرمیوم فعال:** `{premium_count}` نفر\n"
            f"👥 **کل کاربران:** `{await db.total_users_count()}` نفر",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

    except Exception as e:
        await message.reply_text(
            f"❌ خطا در تغییر حالت: {str(e)}",
            quote=True
        )


@FileStream.on_message(filters.command("setlimit") & filters.private & filters.user(Telegram.OWNER_ID))
async def set_limit_handler(bot: Client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.reply_text(
                "❌ **فرمت دستور نادرست است.**\n\n"
                "✅ **استفاده صحیح:**\n"
                "`/setlimit [نوع کاربر] [حداکثر حجم به مگابایت]`\n\n"
                "📝 **مثال‌ها:**\n"
                "`/setlimit free 100` - محدودیت 100 مگابایت برای کاربران رایگان\n"
                "`/setlimit premium 1024` - محدودیت 1 گیگابایت برای کاربران پرمیوم\n"
                "`/setlimit free 0` - حذف محدودیت برای کاربران رایگان",
                parse_mode=ParseMode.MARKDOWN,
                quote=True
            )
            return

        user_type = parts[1].lower()
        max_size_mb = int(parts[2])
        max_size_bytes = max_size_mb * 1024 * 1024  # تبدیل به بایت

        if user_type == "free":
            Telegram.FREE_USER_MAX_SIZE = max_size_bytes
            type_name = "کاربران رایگان"
        elif user_type == "premium":
            Telegram.PREMIUM_USER_MAX_SIZE = max_size_bytes
            type_name = "کاربران پرمیوم"
        else:
            await message.reply_text(
                "❌ نوع کاربر نامعتبر! از 'free' یا 'premium' استفاده کنید.",
                quote=True
            )
            return

        from FileStream.utils.human_readable import humanbytes
        max_size_readable = humanbytes(max_size_bytes)

        status = "نامحدود" if max_size_bytes == 0 else max_size_readable

        await message.reply_text(
            f"✅ **محدودیت حجمی تنظیم شد!**\n\n"
            f"👤 **نوع کاربر:** {type_name}\n"
            f"📦 **حداکثر حجم مجاز:** {status}",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

    except ValueError:
        await message.reply_text(
            "❌ حجم باید عدد باشد!",
            quote=True
        )
    except Exception as e:
        await message.reply_text(
            f"❌ خطا در اجرای دستور: {str(e)}",
            quote=True
        )


@FileStream.on_message(filters.command("limits") & filters.private & filters.user(Telegram.OWNER_ID))
async def show_limits_handler(bot: Client, message: Message):
    try:
        from FileStream.utils.human_readable import humanbytes
        
        free_limit = humanbytes(Telegram.FREE_USER_MAX_SIZE) if Telegram.FREE_USER_MAX_SIZE > 0 else "نامحدود"
        premium_limit = humanbytes(Telegram.PREMIUM_USER_MAX_SIZE) if Telegram.PREMIUM_USER_MAX_SIZE > 0 else "نامحدود"

        await message.reply_text(
            f"📊 **محدودیت‌های حجمی فعلی:**\n\n"
            f"👤 **کاربران رایگان:** {free_limit}\n"
            f"👑 **کاربران پرمیوم:** {premium_limit}\n\n"
            f"🔒 **حالت فقط پرمیوم:** `{'فعال ✅' if Telegram.ONLY_PREMIUM else 'غیرفعال ❌'}`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

    except Exception as e:
        await message.reply_text(
            f"❌ خطا در دریافت محدودیت‌ها: {str(e)}",
            quote=True
        )