from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from FileStream.config import Telegram

class LANG(object):

    START_TEXT = """
<b>👋 سلام, </b>\n 
<b>🔗 برای دریافت لینک دانلود مستقیم، فایل مورد نظر رو واسه ربات فوروارد کن</b>\n"""

    HELP_TEXT = """
<b>- منو به عنوان ادمین کانال اضافه کن</b>
<b>- فایل مورد نظر خود را بفرست</b>
<b>- لینک دانلود مستقیم و سریع دریافت کن</b>\n
<b>🔞 محتوای +18 (پورن) کاملاً ممنوع است.</b>\n
<i><b> هر مشکلی داشتی به <i><b><a href='https://telegram.me/mahdi79230'>توسعه‌دهنده</a></b></i> گزارش بده!"""

    ABOUT_TEXT = """
<b>⚜ ᴍʏ ɴᴀᴍᴇ : {}</b>\n
<b>✦ ᴠᴇʀsɪᴏɴ : {}</b>
<b>✦ ᴜᴘᴅᴀᴛᴇᴅ ᴏɴ : 06-January-2024</b>
<b>✦ ᴅᴇᴠᴇʟᴏᴘᴇʀ : <a href='https://telegram.me/AvishkarPatil'>Avishkar Patil</a></b>\n
"""

    STREAM_TEXT = """
<i><u><b>لـیـنـک فـایـل شـمـا سـاخـتـه شـد !</b></u></i>\n
<b>🪪 نام فایل :</b> <b>{}</b>\n
<b>📦 حجم فایل :</b> <code>{}</code>\n
<b>📥 لینک دانلود :</b> <code>{}</code>\n
<b>🖥️ پخش آنلاین :</b> <code>{}</code>\n
<b>🔗 اشتراک گذاری :</b> <code>{}</code>\n"""

    STREAM_TEXT_X = """
<i><u><b>لـیـنـک فـایـل شـمـا سـاخـتـه شـد !</b></u></i>\n
<b>🪪 نام فایل :</b> <b>{}</b>\n
<b>📦 حجم فایل :</b> <code>{}</code>\n
<b>📥 لینک دانلود :</b> <code>{}</code>\n
<b>🔗 اشتراک گذاری :</b> <code>{}</code>\n"""


    BAN_TEXT = "دسترسی شما مسدود شده است.\n\n**برای کمک با [توسعه‌دهنده](tg://user?id={}) تماس بگیرید**"


class BUTTON(object):
    START_BUTTONS = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton('ʜᴇʟᴘ', callback_data='help'),
            InlineKeyboardButton('ᴀʙᴏᴜᴛ', callback_data='about'),
            InlineKeyboardButton('✖️ بستن', callback_data='close')
        ],
            [InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url=f'https://t.me/{Telegram.UPDATES_CHANNEL}')]
        ]
    )
    HELP_BUTTONS = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton('ʜᴏᴍᴇ', callback_data='home'),
            InlineKeyboardButton('ᴀʙᴏᴜᴛ', callback_data='about'),
            InlineKeyboardButton('✖️ بستن', callback_data='close'),
        ],
            [InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url=f'https://t.me/{Telegram.UPDATES_CHANNEL}')]
        ]
    )
    ABOUT_BUTTONS = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton('ʜᴏᴍᴇ', callback_data='home'),
            InlineKeyboardButton('ʜᴇʟᴘ', callback_data='help'),
            InlineKeyboardButton('✖️ بستن', callback_data='close'),
        ],
            [InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url=f'https://t.me/{Telegram.UPDATES_CHANNEL}')]
        ]
    )
