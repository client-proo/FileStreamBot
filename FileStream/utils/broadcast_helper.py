import asyncio
import traceback
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid, ChatWriteForbidden

async def send_msg(user_id, message):
    """
    ارسال پیام به کاربر با مدیریت خطاهای مختلف
    """
    try:
        # ارسال پیام با کپی کردن محتوا
        await message.copy(chat_id=user_id)
        return 200, None
        
    except FloodWait as e:
        # مدیریت FloodWait - صبر کردن و تلاش مجدد
        wait_time = e.value
        await asyncio.sleep(wait_time)
        return await send_msg(user_id, message)
        
    except InputUserDeactivated:
        return 400, f"{user_id} : کاربر غیرفعال شده است\n"
        
    except UserIsBlocked:
        return 400, f"{user_id} : کاربر ربات را بلاک کرده است\n"
        
    except PeerIdInvalid:
        return 400, f"{user_id} : آیدی کاربر نامعتبر است\n"
        
    except ChatWriteForbidden:
        return 400, f"{user_id} : امکان ارسال پیام به این چت وجود ندارد\n"
        
    except Exception as e:
        error_msg = f"{user_id} : {str(e)}\n{traceback.format_exc()}\n"
        return 500, error_msg