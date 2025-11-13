import logging
import math
import time
from FileStream import __version__
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.utils.bot_utils import gen_linkx, verify_user, seconds_to_hms
from FileStream.config import Telegram
from FileStream.utils.database import Database
from FileStream.utils.translation import LANG, BUTTON
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.enums.parse_mode import ParseMode
import asyncio

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

# ایمپورت تابع is_bot_active از admin
try:
    from FileStream.bot.plugins.admin import is_bot_active
except ImportError:
    # اگر ایمپورت نشد، تابع ساده‌ای تعریف کن
    def is_bot_active():
        return True

@FileStream.on_message(filters.command('start') & filters.private)
async def start(bot: Client, message: Message):
    print(f"🚀 دستور start دریافت شده از کاربر: {message.from_user.id}")
    
    # اگر ربات خاموش است و کاربر عادی است
    if not is_bot_active() and message.from_user.id != Telegram.OWNER_ID:
        print("❌ ربات غیرفعال است و کاربر عادی است")
        await message.reply_text("❌ ربات در حال حاضر غیرفعال است. لطفاً بعداً تلاش کنید.")
        return

    # اگر کاربر ادمین نیست، باید verify_user را چک کنیم
    if message.from_user.id != Telegram.OWNER_ID:
        print("🔍 چک verify_user برای کاربر عادی")
        if not await verify_user(bot, message):
            print("❌ کاربر verify نشد")
            return
        print("✅ کاربر verify شد")

    usr_cmd = message.text.split("_")[-1]
    print(f"🔍 پارامتر start: {usr_cmd}")

    # اگر کاربر ادمین اصلی است، به پنل مدیریت هدایت شود
    if message.from_user.id == Telegram.OWNER_ID:
        print("👑 کاربر ادمین اصلی است")
        if usr_cmd == "/start":
            # استفاده از کیبورد ادمین
            from FileStream.bot.plugins.admin import ADMIN_KEYBOARD
            await message.reply_text(
                text="🏠 **پنل مدیریت**\n\nبه پنل مدیریت خوش آمدید! لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=ADMIN_KEYBOARD
            )
            return

    # پردازش لینک‌های stream_ و file_ برای همه کاربران مجاز
    if usr_cmd != "/start":
        print(f"🔗 پردازش لینک: {usr_cmd}")
        if "stream_" in message.text:
            try:
                file_check = await db.get_file(usr_cmd)
                file_id = str(file_check['_id'])
                if file_id == usr_cmd:
                    reply_markup, stream_text = await gen_linkx(m=message, _id=file_id,
                                                                name=[FileStream.username, FileStream.fname])
                    await message.reply_text(
                        text=stream_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                        quote=True
                    )

            except FIleNotFound as e:
                await message.reply_text("❌ فایل پیدا نشد یا منقضی شده است")
            except Exception as e:
                await message.reply_text("❌ خطایی رخ داد")
                logging.error(e)

        elif "file_" in message.text:
            try:
                # استفاده از تابع get_file که خودش چک انقضا می‌کند
                file_check = await db.get_file(usr_cmd)
                file_id = file_check['file_id']
                file_name = file_check['file_name']

                filex = await message.reply_cached_media(file_id=file_id, caption=f'**{file_name}**')
                await asyncio.sleep(3600)
                try:
                    await filex.delete()
                    await message.delete()
                except Exception:
                    pass

            except FIleNotFound as e:
                await message.reply_text("❌ این لینک منقضی شده است یا وجود ندارد!")
            except Exception as e:
                await message.reply_text("❌ خطایی رخ داد")
                logging.error(e)
        else:
            await message.reply_text(f"**دستور نامعتبر**")
        return

    # پیام start برای کاربران عادی
    print("📝 ارسال پیام start به کاربر عادی")
    if Telegram.START_PIC:
        await message.reply_photo(
            photo=Telegram.START_PIC,
            caption=LANG.START_TEXT.format(message.from_user.mention, FileStream.username),
            parse_mode=ParseMode.HTML,
            reply_markup=BUTTON.START_BUTTONS
        )
    else:
        await message.reply_text(
            text=LANG.START_TEXT.format(message.from_user.mention, FileStream.username),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=BUTTON.START_BUTTONS
        )

@FileStream.on_message(filters.private & filters.command(["about"]))
async def about_handler(bot, message):
    if not is_bot_active() and message.from_user.id != Telegram.OWNER_ID:
        await message.reply_text("❌ ربات در حال حاضر غیرفعال است.")
        return

    if message.from_user.id != Telegram.OWNER_ID:
        if not await verify_user(bot, message):
            return

    if Telegram.START_PIC:
        await message.reply_photo(
            photo=Telegram.START_PIC,
            caption=LANG.ABOUT_TEXT.format(FileStream.fname, __version__),
            parse_mode=ParseMode.HTML,
            reply_markup=BUTTON.ABOUT_BUTTONS
        )
    else:
        await message.reply_text(
            text=LANG.ABOUT_TEXT.format(FileStream.fname, __version__),
            disable_web_page_preview=True,
            reply_markup=BUTTON.ABOUT_BUTTONS
        )

@FileStream.on_message((filters.command('help')) & filters.private)
async def help_handler(bot, message):
    if not is_bot_active() and message.from_user.id != Telegram.OWNER_ID:
        await message.reply_text("❌ ربات در حال حاضر غیرفعال است.")
        return

    if message.from_user.id != Telegram.OWNER_ID:
        if not await verify_user(bot, message):
            return

    if Telegram.START_PIC:
        await message.reply_photo(
            photo=Telegram.START_PIC,
            caption=LANG.HELP_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.HTML,
            reply_markup=BUTTON.HELP_BUTTONS
        )
    else:
        await message.reply_text(
            text=LANG.HELP_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=BUTTON.HELP_BUTTONS
        )

@FileStream.on_message(filters.command('files') & filters.private)
async def my_files(bot: Client, message: Message):
    print(f"📁 دستور files دریافت شده از کاربر: {message.from_user.id}")
    
    if not is_bot_active() and message.from_user.id != Telegram.OWNER_ID:
        await message.reply_text("❌ ربات در حال حاضر غیرفعال است.")
        return

    if message.from_user.id != Telegram.OWNER_ID:
        if not await verify_user(bot, message):
            return

    try:
        print("🔍 درحال دریافت فایل‌ها از دیتابیس...")
        user_files, total_files = await db.find_files(message.from_user.id, [1, 10])
        print(f"✅ {total_files} فایل پیدا شد")

        file_list = []
        file_count = 0
        
        async for x in user_files:
            file_count += 1
            print(f"📁 پردازش فایل {file_count}: {x['file_name']}")
            
            create_time = x['time']
            expire_time = create_time + Telegram.EXPIRE_TIME
            remaining_seconds = int(expire_time - time.time())

            if remaining_seconds <= 0:
                remaining_text = "⏰ منقضی شده"
            else:
                remaining_text = f"⏰ {seconds_to_hms(remaining_seconds)}"

            file_name = x["file_name"]
            if len(file_name) > 20:
                file_name = file_name[:20] + "..."

            button_text = f"{file_name}\n{remaining_text}"
            file_list.append([InlineKeyboardButton(button_text, callback_data=f"myfile_{x['_id']}_{1}")])

        print(f"📋 {len(file_list)} فایل برای نمایش آماده شد")

        if total_files > 10:
            file_list.append(
                [
                    InlineKeyboardButton("◄", callback_data="{}".format("userfiles_"+str(1-1) if 1 > 1 else 'N/A')),
                    InlineKeyboardButton(f"1/{math.ceil(total_files / 10)}", callback_data="N/A"),
                    InlineKeyboardButton("►", callback_data="{}".format("userfiles_"+str(1+1) if total_files > 1*10 else 'N/A'))
                ],
            )
        
        if not file_list:
            file_list.append([InlineKeyboardButton("📭 خالی", callback_data="N/A")])
            print("📭 هیچ فایلی برای نمایش وجود ندارد")
        
        file_list.append([InlineKeyboardButton("✖️ بستن", callback_data="close")])

        # چک کردن وجود FILE_PIC
        if hasattr(Telegram, 'FILE_PIC') and Telegram.FILE_PIC:
            print("🖼️ ارسال با عکس")
            await message.reply_photo(
                photo=Telegram.FILE_PIC,
                caption=f"🗂 تعداد کل فایل ها: {total_files}\n⏰ زمان‌های نمایش داده شده تا انقضای لینک‌ها می‌باشد",
                reply_markup=InlineKeyboardMarkup(file_list)
            )
        else:
            print("📝 ارسال بدون عکس")
            await message.reply_text(
                text=f"🗂 تعداد کل فایل ها: {total_files}\n⏰ زمان‌های نمایش داده شده تا انقضای لینک‌ها می‌باشد",
                reply_markup=InlineKeyboardMarkup(file_list)
            )
            
        print("✅ دستور files با موفقیت اجرا شد")

    except Exception as e:
        print(f"❌ خطا در اجرای دستور files: {e}")
        await message.reply_text("❌ خطایی در دریافت فایل‌ها رخ داد. لطفاً بعداً تلاش کنید.")