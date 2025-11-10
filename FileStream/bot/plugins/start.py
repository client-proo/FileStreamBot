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
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums.parse_mode import ParseMode
import asyncio

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

# ایمپورت کیبورد ادمین از admin.py
from FileStream.bot.plugins.admin import ADMIN_KEYBOARD

@FileStream.on_message(filters.command('start') & filters.private)
async def start(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return
    usr_cmd = message.text.split("_")[-1]

    # اگر کاربر ادمین اصلی است، کیبورد ادمین نشان داده شود
    if message.from_user.id == Telegram.OWNER_ID:
        if usr_cmd == "/start":
            await message.reply_text(
                text="🛠 **به پنل مدیریت خوش آمدید!**\n\n"
                     "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=ADMIN_KEYBOARD
            )
            return

    if usr_cmd == "/start":
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
    else:
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

@FileStream.on_message(filters.private & filters.command(["about"]))
async def start(bot, message):
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

# ---------------------------------------------------------------------------------------------------

@FileStream.on_message(filters.command('files') & filters.private)
async def my_files(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return
    user_files, total_files = await db.find_files(message.from_user.id, [1, 10])

    file_list = []
    async for x in user_files:
        # محاسبه زمان باقی‌مانده برای هر فایل
        create_time = x['time']
        expire_time = create_time + Telegram.EXPIRE_TIME
        remaining_seconds = int(expire_time - time.time())
        
        if remaining_seconds <= 0:
            remaining_text = "⏰ منقضی شده"
        else:
            remaining_text = f"⏰ {seconds_to_hms(remaining_seconds)}"
        
        # اضافه کردن زمان باقی‌مانده به نام فایل
        file_name = x["file_name"]
        if len(file_name) > 20:
            file_name = file_name[:20] + "..."
        
        button_text = f"{file_name}\n{remaining_text}"
        file_list.append([InlineKeyboardButton(button_text, callback_data=f"myfile_{x['_id']}_{1}")])
    
    if total_files > 10:
        file_list.append(
            [
                InlineKeyboardButton("◄", callback_data="N/A"),
                InlineKeyboardButton(f"1/{math.ceil(total_files / 10)}", callback_data="N/A"),
                InlineKeyboardButton("►", callback_data="userfiles_2")
            ],
        )
    if not file_list:
        file_list.append(
            [InlineKeyboardButton("📭 خالی", callback_data="N/A")],
        )
    file_list.append([InlineKeyboardButton("✖️ بستن", callback_data="close")])
    
    await message.reply_photo(
        photo=Telegram.FILE_PIC,
        caption="🗂 تعداد کل فایل ها: {}\n⏰ زمان‌های نمایش داده شده تا انقضای لینک‌ها می‌باشد".format(total_files),
        reply_markup=InlineKeyboardMarkup(file_list)
    )