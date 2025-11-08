import jdatetime
import time
from pyrogram.errors import UserNotParticipant, FloodWait
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from FileStream.utils.translation import LANG
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.config import Telegram, Server
from FileStream.bot import FileStream
import asyncio
from typing import (
    Union
)


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

async def get_invite_link(bot, chat_id: Union[str, int]):
    try:
        invite_link = await bot.create_chat_invite_link(chat_id=chat_id)
        return invite_link
    except FloodWait as e:
        print(f"Sleep of {e.value}s caused by FloodWait ...")
        await asyncio.sleep(e.value)
        return await get_invite_link(bot, chat_id)

async def is_user_joined(bot, message: Message):
    if Telegram.FORCE_SUB_ID and Telegram.FORCE_SUB_ID.startswith("-100"):
        channel_chat_id = int(Telegram.FORCE_SUB_ID)    # When id startswith with -100
    elif Telegram.FORCE_SUB_ID and (not Telegram.FORCE_SUB_ID.startswith("-100")):
        channel_chat_id = Telegram.FORCE_SUB_ID     # When id not startswith -100
    else:
        return 200
    try:
        user = await bot.get_chat_member(chat_id=channel_chat_id, user_id=message.from_user.id)
        if user.status == "BANNED":
            await message.reply_text(
                text=LANG.BAN_TEXT.format(Telegram.OWNER_ID),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return False
    except UserNotParticipant:
        invite_link = await get_invite_link(bot, chat_id=channel_chat_id)
        if Telegram.VERIFY_PIC:
            ver = await message.reply_photo(
                photo=Telegram.VERIFY_PIC,
                caption="<b>⚠️ <i>عضویت اجباری در کانال</i> ⚠️</b>\n\nبرای استفاده از ربات، لطفاً ابتدا <b><i>عضو کانال</i></b> شوید.\n\nپس از <b><i>عضویت</i></b>، دوباره امتحان کنید.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("LinkBolt channel", url=invite_link.invite_link)
                ]]
                )
            )
        else:
            ver = await message.reply_text(
                text = "<b>⚠️ <i>عضویت اجباری در کانال</i> ⚠️</b>\n\nبرای استفاده از ربات، لطفاً ابتدا <b><i>عضو کانال</i></b> شوید.\n\nپس از <b><i>عضویت</i></b>، دوباره امتحان کنید.",
                reply_markup=InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("LinkBolt channel", url=invite_link.invite_link)
                    ]]
                ),
                parse_mode=ParseMode.HTML
            )
        await asyncio.sleep(30)
        try:
            await ver.delete()
            await message.delete()
        except Exception:
            pass
        return False
    except Exception:
        await message.reply_text(
            text = f"<i>Sᴏᴍᴇᴛʜɪɴɢ ᴡʀᴏɴɢ ᴄᴏɴᴛᴀᴄᴛ ᴍʏ ᴅᴇᴠᴇʟᴏᴘᴇʀ</i> <b><a href='https://t.me/{Telegram.UPDATES_CHANNEL}'>[ ᴄʟɪᴄᴋ ʜᴇʀᴇ ]</a></b>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True)
        return False
    return True

#---------------------[ PRIVATE GEN LINK + CALLBACK ]---------------------#

import jdatetime  # اضافه کردن

async def gen_link(_id):
    file_info = await db.get_file(_id)
    file_name = file_info['file_name']
    file_size = humanbytes(file_info['file_size'])
    mime_type = file_info['mime_type']

    page_link = f"{Server.URL}watch/{_id}"
    stream_link = f"{Server.URL}dl/{_id}"
    file_link = f"https://t.me/{FileStream.username}?start=file_{_id}"

    expires_in = file_info.get('expires_in', 0)
    expire_time = file_info.get('expire_at')

    if expires_in:
        tehran_time = expire_time + 12600
        jalali_date = jdatetime.datetime.fromtimestamp(tehran_time).strftime('%Y/%m/%d - %H:%M:%S')
        remaining = int(expire_time - time.time())
        mins, secs = divmod(remaining, 60)
        countdown = f"{mins} دقیقه و {secs} ثانیه" if remaining > 0 else "منقضی شده!"
        expire_text = f"\n\n<b>انقضا:</b> <code>{jalali_date}</code>\n<b>زمان باقی‌مانده:</b> <code>{countdown}</code>"
    else:
        expire_text = ""

    if "video" in mime_type:
        stream_text = LANG.STREAM_TEXT.format(file_name, file_size, stream_link, page_link, file_link, expire_text)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🖥️ پخش آنلاین", url=page_link), InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📂 دریافت فایل", url=file_link), InlineKeyboardButton("🗑 حذف فایل", callback_data=f"msgdelpvt_{_id}")],
                [InlineKeyboardButton("✖️ بستن", callback_data="close")]
            ]
        )
    else:
        stream_text = LANG.STREAM_TEXT_X.format(file_name, file_size, stream_link, file_link, expire_text)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📂 دریافت فایل", url=file_link), InlineKeyboardButton("🗑 حذف فایل", callback_data=f"msgdelpvt_{_id}")],
                [InlineKeyboardButton("✖️ بستن", callback_data="close")]
            ]
        )
    return reply_markup, stream_text

#---------------------[ GEN STREAM LINKS FOR CHANNEL ]---------------------#

async def gen_linkx(m:Message , _id, name: list):
    file_info = await db.get_file(_id)
    file_name = file_info['file_name']
    mime_type = file_info['mime_type']
    file_size = humanbytes(file_info['file_size'])

    page_link = f"{Server.URL}watch/{_id}"
    stream_link = f"{Server.URL}dl/{_id}"
    file_link = f"https://t.me/{FileStream.username}?start=file_{_id}"

    if "video" in mime_type:
        stream_text= LANG.STREAM_TEXT_X.format(file_name, file_size, stream_link, page_link)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🖥️ پخش آنلاین", url=page_link), InlineKeyboardButton("📥 دانلود", url=stream_link)]
            ]
        )
    else:
        stream_text= LANG.STREAM_TEXT_X.format(file_name, file_size, stream_link, file_link)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📥 دانلود", url=stream_link)]
            ]
        )
    return reply_markup, stream_text

#---------------------[ USER BANNED ]---------------------#

async def is_user_banned(message):
    if await db.is_user_banned(message.from_user.id):
        await message.reply_text(
            text=LANG.BAN_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return True
    return False

#---------------------[ CHANNEL BANNED ]---------------------#

async def is_channel_banned(bot, message):
    if await db.is_user_banned(message.chat.id):
        await bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.id,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"ᴄʜᴀɴɴᴇʟ ɪs ʙᴀɴɴᴇᴅ", callback_data="N/A")]])
        )
        return True
    return False

#---------------------[ USER AUTH ]---------------------#

async def is_user_authorized(message):
    if hasattr(Telegram, 'AUTH_USERS') and Telegram.AUTH_USERS:
        user_id = message.from_user.id

        if user_id == Telegram.OWNER_ID:
            return True

        if not (user_id in Telegram.AUTH_USERS):
            await message.reply_text(
                text="شما مجاز به استفاده از این ربات نیستید.",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return False

    return True

#---------------------[ USER EXIST ]---------------------#

async def is_user_exist(bot, message):
    if not bool(await db.get_user(message.from_user.id)):
        await db.add_user(message.from_user.id)
        await bot.send_message(
            Telegram.ULOG_CHANNEL,
            f"**✨ کاربر جدید اضافه شد! ✨**\n**👤 نام کاربر :** [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n**🆔 آیدی کاربر :** `{message.from_user.id}`"
        )

async def is_channel_exist(bot, message):
    if not bool(await db.get_user(message.chat.id)):
        await db.add_user(message.chat.id)
        members = await bot.get_chat_members_count(message.chat.id)
        await bot.send_message(
            Telegram.ULOG_CHANNEL,
            f"**✨ کانال جدید اضافه شد! ✨** \n💬 نام چت:** `{message.chat.title}`\n**🆔 آیدی چت :** `{message.chat.id}`\n**⬩ 👥 کل کاربران :** `{members}`"
        )

async def verify_user(bot, message):
    if not await is_user_authorized(message):
        return False

    if await is_user_banned(message):
        return False

    await is_user_exist(bot, message)

    if Telegram.FORCE_SUB:
        if not await is_user_joined(bot, message):
            return False

    return True