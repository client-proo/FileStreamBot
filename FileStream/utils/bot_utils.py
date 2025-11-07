from pyrogram.errors import UserNotParticipant, FloodWait
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from FileStream.utils.translation import LANG
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.config import Telegram, Server
from FileStream.bot import FileStream
import asyncio
from typing import Union
import time
import jdatetime
import random
import string

# دیتابیس‌های اضافی برای ویژگی‌های LinkBolt Pro
FILE_DB = {}  # code → (file_id, expire, ftype, chat_id, message_id, [sent_msgs])
USER_ACCESS = {}  # code → {user_id: last_click_time}
SENT_FILES = {}  # user_id → لیست کد فایل‌های فعال
LAST_SEND = {}  # user_id → timestamp آخرین ارسال
ANTI_SPAM_TIME = 120  # ثانیه

# توابع کمکی برای ویژگی‌های LinkBolt Pro
def format_remaining(seconds: float) -> str:
    seconds = int(seconds)
    if seconds <= 0: return "منقضی شده!"
    parts = []
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s: parts.append(f"{s} ثانیه")
    if len(parts) == 1: return parts[0] + " باقی مونده"
    if len(parts) == 2: return f"{parts[0]} و {parts[1]} باقی مونده"
    return f"{parts[0]} و {parts[1]} و {parts[2]} باقی مونده"

def to_shamsi(t):
    return jdatetime.datetime.fromtimestamp(t).strftime("%Y/%m/%d - %H:%M:%S")

def generate_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=20))

# پاکسازی خودکار فایل‌های منقضی شده
async def auto_cleanup(bot):
    while True:
        await asyncio.sleep(10)
        now = time.time()
        expired = [c for c, (_, e, *_) in FILE_DB.items() if now > e]
        for code in expired:
            file_id, _, _, chat_id, msg_id, sent = FILE_DB.pop(code, (None,)*6)
            try: await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except: pass
            for ch, mid in sent:
                try: await bot.delete_message(chat_id=ch, message_id=mid)
                except: pass
            try: await bot.send_message(chat_id=chat_id, text="فایل شما منقضی شد. لطفاً دوباره ارسال کنید.")
            except: pass
            USER_ACCESS.pop(code, None)
            for u, files in SENT_FILES.items():
                if code in files: files.remove(code)
            for u in list(LAST_SEND.keys()):
                if u in SENT_FILES and not SENT_FILES[u]:
                    LAST_SEND.pop(u, None)

# راه‌اندازی پاکسازی خودکار (در استارت ربات فراخوانی کنید)
async def start_cleanup(bot):
    asyncio.create_task(auto_cleanup(bot))

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

async def gen_link(_id):
    file_info = await db.get_file(_id)
    file_name = file_info['file_name']
    file_size = humanbytes(file_info['file_size'])
    mime_type = file_info['mime_type']

    # اضافه کردن ویژگی انقضا به لینک
    code = generate_code()
    expire = time.time() + 60
    FILE_DB[code] = (_id, expire, mime_type, file_info.get('chat_id'), file_info.get('message_id'), [])

    page_link = f"{Server.URL}watch/{code}"
    stream_link = f"{Server.URL}dl/{code}"
    file_link = f"https://t.me/{FileStream.username}?start=file_{code}"

    remaining_text = format_remaining(expire - time.time())
    shamsi_expire = to_shamsi(expire)

    if "video" in mime_type:
        stream_text = LANG.STREAM_TEXT.format(file_name, file_size, stream_link, page_link, file_link) + f"\n\nانقضا: {shamsi_expire}\n{remaining_text}"
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🖥️ پخش آنلاین", url=page_link), InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📂 دریافت فایل", url=file_link), InlineKeyboardButton("🗑 حذف فایل", callback_data=f"msgdelpvt_{code}")],
                [InlineKeyboardButton("✖️ بستن", callback_data="close")]
            ]
        )
    else:
        stream_text = LANG.STREAM_TEXT_X.format(file_name, file_size, stream_link, file_link) + f"\n\nانقضا: {shamsi_expire}\n{remaining_text}"
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📂 دریافت فایل", url=file_link), InlineKeyboardButton("🗑 حذف فایل", callback_data=f"msgdelpvt_{code}")],
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

    # اضافه کردن ویژگی انقضا
    code = generate_code()
    expire = time.time() + 60
    FILE_DB[code] = (_id, expire, mime_type, m.chat.id, m.id, [])

    page_link = f"{Server.URL}watch/{code}"
    stream_link = f"{Server.URL}dl/{code}"
    file_link = f"https://t.me/{FileStream.username}?start=file_{code}"

    remaining_text = format_remaining(expire - time.time())
    shamsi_expire = to_shamsi(expire)

    if "video" in mime_type:
        stream_text= LANG.STREAM_TEXT_X.format(file_name, file_size, stream_link, page_link) + f"\n\nانقضا: {shamsi_expire}\n{remaining_text}"
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🖥️ پخش آنلاین", url=page_link), InlineKeyboardButton("📥 دانلود", url=stream_link)]
            ]
        )
    else:
        stream_text= LANG.STREAM_TEXT_X.format(file_name, file_size, stream_link, file_link) + f"\n\nانقضا: {shamsi_expire}\n{remaining_text}"
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

    # اضافه کردن ضد اسپم به وریفای
    user_id = message.from_user.id
    now = time.time()
    if user_id in LAST_SEND and now - LAST_SEND[user_id] < ANTI_SPAM_TIME:
        remaining = ANTI_SPAM_TIME - (now - LAST_SEND[user_id])
        m = int(remaining) // 60
        s = int(remaining) % 60
        countdown = f"{m} دقیقه و {s} ثانیه" if m else f"{s} ثانیه"
        await message.reply_text(f"از اسپم کردن خودداری کنید!\nزمان باقی‌مانده تا ارسال بعدی: {countdown}")
        return False
    LAST_SEND[user_id] = now

    return True