import os
import time
import asyncio
import logging
import datetime
import pytz
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram, Server
from pyrogram import filters, Client
from pyrogram.enums.parse_mode import ParseMode

logger = logging.getLogger(__name__)
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
tehran_tz = pytz.timezone('Asia/Tehran')

# دیکشنری برای ذخیره وضعیت کاربران
user_states = {}

def get_tehran_time():
    return datetime.datetime.now(tehran_tz)

def get_jalali_datetime():
    try:
        import jdatetime
        tehran_time = get_tehran_time()
        jalali_date = jdatetime.datetime.fromgregorian(datetime=tehran_time)
        return jalali_date.strftime('%Y/%m/%d - %H:%M:%S')
    except ImportError:
        return get_tehran_time().strftime('%Y-%m-%d %H:%M:%S')

def get_readable_time(seconds: int) -> str:
    result = ''
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        result += f'{int(days)} روز '
    if hours > 0:
        result += f'{int(hours)} ساعت '
    if minutes > 0:
        result += f'{int(minutes)} دقیقه '
    if seconds > 0 or not result:
        result += f'{int(seconds)} ثانیه'
    
    return result.strip()

# ==================== پنل مدیریت اصلی ====================

@FileStream.on_message(filters.command("admin") & filters.private & filters.user(Telegram.OWNER_ID))
async def admin_panel(c: Client, m: Message):
    total_users = await db.total_users_count()
    total_files = await db.total_files()
    banned_users = await db.total_banned_users_count()

    text = f"""**🛠️ پنل مدیریت ربات**

📊 **آمار کلی:**
├ 👥 کاربران: `{total_users}`
├ 📁 فایل‌ها: `{total_files}`
├ 🚫 مسدود شده: `{banned_users}`
└ 🕒 زمان: `{get_jalali_datetime()}`

**لطفاً یکی از گزینه‌های زیر را انتخاب کنید:**"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار کامل", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("📢 ارسال همگانی", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("🗑️ حذف فایل", callback_data="admin_delete_file")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_refresh")]
    ])

    await m.reply_text(text, reply_markup=keyboard, quote=True)

# ==================== مدیریت کاربران ====================

@FileStream.on_callback_query(filters.regex(r"^admin_users$"))
async def admin_users_menu(query: CallbackQuery):
    text = """**👥 مدیریت کاربران**

لطفاً یکی از عملیات‌ها را انتخاب کنید:"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 لیست کاربران", callback_data="users_list_1")],
        [InlineKeyboardButton("🚫 مسدود کردن کاربر", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ رفع مسدودیت", callback_data="admin_unban_user")],
        [InlineKeyboardButton("🔍 اطلاعات کاربر", callback_data="admin_user_info")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

@FileStream.on_callback_query(filters.regex(r"^admin_ban_user$"))
async def admin_ban_user_start(query: CallbackQuery):
    user_id = query.from_user.id
    user_states[user_id] = {"action": "ban_user", "step": 1}
    
    text = """**🚫 مسدود کردن کاربر**

لطفاً آیدی عددی کاربر را ارسال کنید:"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

@FileStream.on_callback_query(filters.regex(r"^admin_unban_user$"))
async def admin_unban_user_start(query: CallbackQuery):
    user_id = query.from_user.id
    user_states[user_id] = {"action": "unban_user", "step": 1}
    
    text = """**✅ رفع مسدودیت کاربر**

لطفاً آیدی عددی کاربر را ارسال کنید:"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

@FileStream.on_callback_query(filters.regex(r"^admin_user_info$"))
async def admin_user_info_start(query: CallbackQuery):
    user_id = query.from_user.id
    user_states[user_id] = {"action": "user_info", "step": 1}
    
    text = """**🔍 اطلاعات کاربر**

لطفاً آیدی عددی کاربر را ارسال کنید:"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

# ==================== ارسال همگانی ====================

@FileStream.on_callback_query(filters.regex(r"^admin_broadcast_start$"))
async def admin_broadcast_start(query: CallbackQuery):
    user_id = query.from_user.id
    user_states[user_id] = {"action": "broadcast", "step": 1}
    
    text = """**📢 ارسال پیام همگانی**

لطفاً پیامی که می‌خواهید برای همه کاربران ارسال شود را بنویسید و ارسال کنید:"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

# ==================== حذف فایل ====================

@FileStream.on_callback_query(filters.regex(r"^admin_delete_file$"))
async def admin_delete_file_start(query: CallbackQuery):
    user_id = query.from_user.id
    user_states[user_id] = {"action": "delete_file", "step": 1}
    
    text = """**🗑️ حذف فایل**

لطفاً آیدی فایل را ارسال کنید:"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

# ==================== پردازش پیام‌های متنی ====================

@FileStream.on_message(filters.private & filters.user(Telegram.OWNER_ID) & filters.text)
async def handle_admin_messages(c: Client, m: Message):
    user_id = m.from_user.id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    action = state["action"]
    
    if action == "ban_user":
        await process_ban_user(m, state)
    
    elif action == "unban_user":
        await process_unban_user(m, state)
    
    elif action == "user_info":
        await process_user_info(m, state)
    
    elif action == "broadcast":
        await process_broadcast(m, state)
    
    elif action == "delete_file":
        await process_delete_file(m, state)

async def process_ban_user(m: Message, state):
    try:
        user_id_to_ban = int(m.text)
        
        if await db.is_user_banned(user_id_to_ban):
            await m.reply_text(f"✅ کاربر `{user_id_to_ban}` قبلاً مسدود شده است.", quote=True)
        else:
            await db.ban_user(user_id_to_ban)
            await m.reply_text(f"✅ کاربر `{user_id_to_ban}` با موفقیت مسدود شد.", quote=True)
        
        # حذف وضعیت
        if m.from_user.id in user_states:
            del user_states[m.from_user.id]
            
        # بازگشت به منوی کاربران
        await admin_users_menu(await create_callback_query(m))
        
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد. لطفاً دوباره تلاش کنید:", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}", quote=True)

async def process_unban_user(m: Message, state):
    try:
        user_id_to_unban = int(m.text)
        
        if not await db.is_user_banned(user_id_to_unban):
            await m.reply_text(f"✅ کاربر `{user_id_to_unban}` مسدود نیست.", quote=True)
        else:
            await db.unban_user(user_id_to_unban)
            await m.reply_text(f"✅ مسدودیت کاربر `{user_id_to_unban}` برداشته شد.", quote=True)
        
        # حذف وضعیت
        if m.from_user.id in user_states:
            del user_states[m.from_user.id]
            
        # بازگشت به منوی کاربران
        await admin_users_menu(await create_callback_query(m))
        
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد. لطفاً دوباره تلاش کنید:", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}", quote=True)

async def process_user_info(m: Message, state):
    try:
        user_id_to_check = int(m.text)
        user = await db.get_user(user_id_to_check)
        
        if not user:
            await m.reply_text(f"❌ کاربر با آیدی `{user_id_to_check}` پیدا نشد.", quote=True)
        else:
            username = user.get('username', 'ندارد')
            first_name = user.get('first_name', '')
            last_name = user.get('last_name', '')
            join_date = user.get('join_date', 0)
            links_count = user.get('Links', 0)
            is_banned = await db.is_user_banned(user_id_to_check)
            
            full_name = f"{first_name} {last_name}".strip()
            if not full_name:
                full_name = "نامشخص"
            
            join_date_str = datetime.datetime.fromtimestamp(join_date).strftime('%Y-%m-%d %H:%M:%S') if join_date else "نامشخص"
            status = "🚫 مسدود" if is_banned else "✅ فعال"
            
            text = f"""**👤 اطلاعات کاربر:**

🆔 آیدی: `{user_id_to_check}`
👤 نام: `{full_name}`
📧 یوزرنیم: `{username}`
📊 تعداد فایل‌ها: `{links_count}`
📅 تاریخ عضویت: `{join_date_str}`
🎯 وضعیت: {status}"""

            await m.reply_text(text, quote=True)
        
        # حذف وضعیت
        if m.from_user.id in user_states:
            del user_states[m.from_user.id]
            
    except ValueError:
        await m.reply_text("❌ آیدی کاربر باید عددی باشد. لطفاً دوباره تلاش کنید:", quote=True)
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}", quote=True)

async def process_broadcast(m: Message, state):
    broadcast_msg = m
    all_users = await db.get_all_users()
    total_users = await db.total_users_count()

    if total_users == 0:
        await m.reply_text("❌ هیچ کاربری در دیتابیس وجود ندارد.", quote=True)
        return

    progress_msg = await m.reply_text("🔄 شروع ارسال همگانی...", quote=True)

    start_time = time.time()
    done = 0
    failed = 0
    success = 0

    async for user in all_users:
        try:
            user_id = int(user['id'])
            await asyncio.sleep(0.1)
            status, error_msg = await send_msg(user_id=user_id, message=broadcast_msg)

            if status == 200:
                success += 1
            else:
                failed += 1
                if status == 400:
                    await db.delete_user(user_id)

            done += 1

            if done % 10 == 0:
                await progress_msg.edit_text(f"📤 ارسال شده: {done}/{total_users}\n✅ موفق: {success}\n❌ ناموفق: {failed}")

        except Exception as e:
            failed += 1
            continue

    total_time = get_readable_time(int(time.time() - start_time))
    await progress_msg.delete()

    final_report = f"""✅ **ارسال همگانی تکمیل شد!**

👥 کاربران کل: {total_users}
📤 ارسال شده: {done}
✅ موفق: {success}
❌ ناموفق: {failed}
⏱️ زمان کل: {total_time}
🗓️ تاریخ: {get_jalali_datetime()}"""

    await m.reply_text(final_report, quote=True)
    
    # حذف وضعیت
    if m.from_user.id in user_states:
        del user_states[m.from_user.id]

async def process_delete_file(m: Message, state):
    file_id = m.text
    
    try:
        file_info = await db.get_file(file_id)
    except FIleNotFound:
        await m.reply_text("❌ فایل پیدا نشد یا قبلاً حذف شده است.", quote=True)
        # حذف وضعیت
        if m.from_user.id in user_states:
            del user_states[m.from_user.id]
        return
    
    try:
        await db.delete_one_file(file_info['_id'])
        await db.count_links(file_info['user_id'], "-")
        await m.reply_text("✅ فایل با موفقیت حذف شد.", quote=True)
        
        # حذف وضعیت
        if m.from_user.id in user_states:
            del user_states[m.from_user.id]
            
    except Exception as e:
        await m.reply_text(f"❌ خطا در حذف فایل: {e}", quote=True)

# ==================== لیست کاربران ====================

@FileStream.on_callback_query(filters.regex(r"^users_list_"))
async def users_list_handler(query: CallbackQuery):
    try:
        page = int(query.data.split("_")[2])
        await show_users_page(query, page)
    except:
        await show_users_page(query, 1)

async def show_users_page(query: CallbackQuery, page: int):
    all_users = await db.get_all_users()
    users_list = []
    async for user in all_users:
        users_list.append(user)

    users_list.sort(key=lambda x: x.get('join_date', 0), reverse=True)
    total_users = len(users_list)
    
    users_per_page = 8
    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users_list[start_idx:end_idx]

    total_pages = (total_users + users_per_page - 1) // users_per_page

    text = f"**👥 لیست کاربران**\n\n"
    text += f"📊 **صفحه:** `{page}/{total_pages}`\n"
    text += f"👤 **کل کاربران:** `{total_users}`\n\n"

    for i, user in enumerate(page_users, start=start_idx + 1):
        user_id = user['id']
        username = user.get('username', 'ندارد')
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')
        links_count = user.get('Links', 0)
        is_banned = await db.is_user_banned(user_id)

        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = "نامشخص"

        status = "🚫" if is_banned else "✅"
        
        text += f"**{i}. {full_name}**\n"
        text += f"├ 🆔: `{user_id}`\n"
        text += f"├ 📧: {username}\n"
        text += f"├ 🔗: `{links_count}` فایل\n"
        text += f"└ 🎯: {status}\n\n"

    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"users_list_{page-1}"))
    
    buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="users_current"))
    
    if page < total_pages:
        buttons.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"users_list_{page+1}"))

    keyboard = []
    if buttons:
        keyboard.append(buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup)
    await query.answer()

# ==================== آمار کامل ====================

@FileStream.on_callback_query(filters.regex(r"^admin_stats$"))
async def show_complete_stats(query: CallbackQuery):
    total_users = await db.total_users_count()
    total_files = await db.total_files()
    banned_users = await db.total_banned_users_count()
    active_users = total_users - banned_users
    
    all_users = await db.get_all_users()
    today = time.time() - 86400
    today_users = 0
    total_links = 0
    
    async for user in all_users:
        if user.get('join_date', 0) > today:
            today_users += 1
        total_links += user.get('Links', 0)

    text = f"""**📊 آمار کامل ربات**

👥 **کاربران:**
├ کل کاربران: `{total_users}`
├ کاربران فعال: `{active_users}`
├ کاربران امروز: `{today_users}`
└ کاربران مسدود: `{banned_users}`

📁 **فایل‌ها:**
├ کل فایل‌ها: `{total_files}`
└ کل لینک‌ها: `{total_links}`

🕒 **زمان:** `{get_jalali_datetime()}`"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()

# ==================== سایر هندلرها ====================

@FileStream.on_callback_query(filters.regex(r"^admin_back$"))
async def admin_back_handler(query: CallbackQuery):
    await admin_panel(FileStream, query.message)
    await query.answer()

@FileStream.on_callback_query(filters.regex(r"^admin_refresh$"))
async def admin_refresh_handler(query: CallbackQuery):
    await admin_panel(FileStream, query.message)
    await query.answer("✅ پنل بروزرسانی شد")

# تابع کمکی برای ایجاد شبه کال‌بک
async def create_callback_query(m: Message):
    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = m.from_user
            
        async def answer(self, *args, **kwargs):
            pass
            
    return MockCallbackQuery(m)