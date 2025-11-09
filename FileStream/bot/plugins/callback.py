import datetime
import math
import time
from FileStream import __version__
from FileStream.bot import FileStream
from FileStream.config import Telegram, Server
from FileStream.utils.translation import LANG, BUTTON
from FileStream.utils.bot_utils import gen_link, seconds_to_hms
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.server.exceptions import FIleNotFound
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.file_id import FileId, FileType, PHOTO_TYPES
from pyrogram.enums.parse_mode import ParseMode
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

#---------------------[ START CMD ]---------------------#
@FileStream.on_callback_query()
async def cb_data(bot, update: CallbackQuery):
    usr_cmd = update.data.split("_")
    if usr_cmd[0] == "home":
        await update.message.edit_text(
            text=LANG.START_TEXT.format(update.from_user.mention, FileStream.username),
            disable_web_page_preview=True,
            reply_markup=BUTTON.START_BUTTONS
        )
    elif usr_cmd[0] == "help":
        await update.message.edit_text(
            text=LANG.HELP_TEXT.format(Telegram.OWNER_ID),
            disable_web_page_preview=True,
            reply_markup=BUTTON.HELP_BUTTONS
        )
    elif usr_cmd[0] == "about":
        await update.message.edit_text(
            text=LANG.ABOUT_TEXT.format(FileStream.fname, __version__),
            disable_web_page_preview=True,
            reply_markup=BUTTON.ABOUT_BUTTONS
        )

    #---------------------[ MY FILES CMD ]---------------------#

    elif usr_cmd[0] == "N/A":
        await update.answer("N/A", True)
    elif usr_cmd[0] == "close":
        await update.message.delete()
    elif usr_cmd[0] == "msgdelete":
        await update.message.edit_caption(
        caption= "**آیا می‌خواهید فایل را حذف کنید؟**\n\n",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بله", callback_data=f"msgdelyes_{usr_cmd[1]}_{usr_cmd[2]}"), InlineKeyboardButton("خیر", callback_data=f"myfile_{usr_cmd[1]}_{usr_cmd[2]}")]])
    )
    elif usr_cmd[0] == "msgdelyes":
        await delete_user_file(usr_cmd[1], int(usr_cmd[2]), update)
        return
    elif usr_cmd[0] == "msgdelpvt":
        await update.message.edit_caption(
        caption= "**آیا می‌خواهید فایل را حذف کنید؟**\n\n",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بله", callback_data=f"msgdelpvtyes_{usr_cmd[1]}"), InlineKeyboardButton("خیر", callback_data=f"mainstream_{usr_cmd[1]}")]])
    )
    elif usr_cmd[0] == "msgdelpvtyes":
        await delete_user_filex(usr_cmd[1], update)
        return

    elif usr_cmd[0] == "mainstream":
        _id = usr_cmd[1]
        reply_markup, stream_text = await gen_link(_id=_id)
        await update.message.edit_text(
            text=stream_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )

    elif usr_cmd[0] == "userfiles":
        file_list, total_files = await gen_file_list_button(int(usr_cmd[1]), update.from_user.id)
        await update.message.edit_caption(
            caption="🗂 تعداد کل فایل ها: {}".format(total_files),
            reply_markup=InlineKeyboardMarkup(file_list)
            )
    elif usr_cmd[0] == "myfile":
        await gen_file_menu(usr_cmd[1], usr_cmd[2], update)
        return
    elif usr_cmd[0] == "sendfile":
        myfile = await db.get_file(usr_cmd[1])
        file_name = myfile['file_name']
        await update.answer(f"Sending File {file_name}")
        await update.message.reply_cached_media(myfile['file_id'], caption=f'**{file_name}**')
    else:
        await update.message.delete()



    #---------------------[ MY FILES FUNC ]---------------------#

async def gen_file_list_button(file_list_no: int, user_id: int):

    file_range=[file_list_no*10-10+1, file_list_no*10]
    user_files, total_files=await db.find_files(user_id, file_range)

    file_list=[]
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
        file_list.append([InlineKeyboardButton(button_text, callback_data=f"myfile_{x['_id']}_{file_list_no}")])
    
    if total_files > 10:
        file_list.append(
                [InlineKeyboardButton("◄", callback_data="{}".format("userfiles_"+str(file_list_no-1) if file_list_no > 1 else 'N/A')),
                 InlineKeyboardButton(f"{file_list_no}/{math.ceil(total_files/10)}", callback_data="N/A"),
                 InlineKeyboardButton("►", callback_data="{}".format("userfiles_"+str(file_list_no+1) if total_files > file_list_no*10 else 'N/A'))]
        )
    if not file_list:
        file_list.append(
                [InlineKeyboardButton("📭 خالی", callback_data="N/A")])
    file_list.append([InlineKeyboardButton("✖️ بستن", callback_data="close")])
    return file_list, total_files

async def gen_file_menu(_id, file_list_no, update: CallbackQuery):
    try:
        myfile_info=await db.get_file(_id)
    except FIleNotFound:
        await update.answer("فایل پیدا نشد")
        return

    file_id=FileId.decode(myfile_info['file_id'])

    if file_id.file_type in PHOTO_TYPES:
        file_type = "Image"
    elif file_id.file_type == FileType.VOICE:
        file_type = "Voice"
    elif file_id.file_type in (FileType.VIDEO, FileType.ANIMATION, FileType.VIDEO_NOTE):
        file_type = "Video"
    elif file_id.file_type == FileType.DOCUMENT:
        file_type = "Document"
    elif file_id.file_type == FileType.STICKER:
        file_type = "Sticker"
    elif file_id.file_type == FileType.AUDIO:
        file_type = "Audio"
    else:
        file_type = "Unknown"

    # محاسبه زمان باقی‌مانده
    create_time = myfile_info['time']
    expire_time = create_time + Telegram.EXPIRE_TIME
    remaining_seconds = int(expire_time - time.time())
    
    if remaining_seconds <= 0:
        remaining_readable = "❌ منقضی شده"
        expire_status = "❌ منقضی شده"
    else:
        remaining_readable = seconds_to_hms(remaining_seconds)
        expire_status = f"⏰ {remaining_readable}"

    page_link = f"{Server.URL}watch/{myfile_info['_id']}"
    stream_link = f"{Server.URL}dl/{myfile_info['_id']}"
    if "video" in file_type.lower():
        MYFILES_BUTTONS = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🖥️ پخش آنلاین", url=page_link), InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📂 دریافت فایل", callback_data=f"sendfile_{myfile_info['_id']}"),
                 InlineKeyboardButton("🗑 حذف فایل", callback_data=f"msgdelete_{myfile_info['_id']}_{file_list_no}")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="userfiles_{}".format(file_list_no))]
            ]
        )
    else:
        MYFILES_BUTTONS = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📥 دانلود", url=stream_link)],
                [InlineKeyboardButton("📂 دریافت فایل", callback_data=f"sendfile_{myfile_info['_id']}"),
                 InlineKeyboardButton("🗑 حذف فایل", callback_data=f"msgdelete_{myfile_info['_id']}_{file_list_no}")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="userfiles_{}".format(file_list_no))]
            ]
        )

    TiMe = myfile_info['time']
    if type(TiMe) == float:
        date = datetime.datetime.fromtimestamp(TiMe)
    
    await update.edit_message_caption(
        caption="**🪪 نام فایل :** `{}`\n**📦 حجم فایل :** `{}`\n**🗂 نوع فایل :** `{}`\n**⏰ وضعیت انقضا :** `{}`\n**📅 تاریخ ایجاد :** `{}`".format(
            myfile_info['file_name'],
            humanbytes(int(myfile_info['file_size'])),
            file_type,
            expire_status,
            TiMe if isinstance(TiMe,str) else date.date()
        ),
        reply_markup=MYFILES_BUTTONS 
    )


async def delete_user_file(_id, file_list_no: int, update:CallbackQuery):

    try:
        myfile_info=await db.get_file(_id)
    except FIleNotFound:
        await update.answer("فایل قبلاً حذف شده است")
        return

    await db.delete_one_file(myfile_info['_id'])
    await db.count_links(update.from_user.id, "-")
    await update.message.edit_caption(
            caption= "**فایل با موفقیت حذف شد !**" + update.message.caption.replace("آیا می‌خواهید فایل را حذف کنید؟", ""),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data=f"userfiles_1")]])
        )

async def delete_user_filex(_id, update:CallbackQuery):

    try:
        myfile_info=await db.get_file(_id)
    except FIleNotFound:
        await update.answer("فایل قبلاً حذف شده است")
        return

    await db.delete_one_file(myfile_info['_id'])
    await db.count_links(update.from_user.id, "-")
    await update.message.edit_caption(
            caption= "**فایل با موفقیت حذف شد !**\n\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ بستن", callback_data=f"close")]])
        )