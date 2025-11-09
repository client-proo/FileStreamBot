import asyncio
import traceback
from pyrogram.errors import (
    FloodWait, InputUserDeactivated, UserIsBlocked, 
    PeerIdInvalid, ChatWriteForbidden, ChannelPrivate,
    UserNotParticipant, ChatAdminRequired
)

async def send_msg(user_id, message):
    """
    ارسال پیام به کاربر با مدیریت کامل خطاها
    """
    try:
        # بررسی اینکه user_id معتبر است
        if not user_id or not isinstance(user_id, int):
            return 400, f"{user_id} : آیدی کاربر نامعتبر\n"
        
        # ارسال پیام
        await message.copy(chat_id=user_id)
        return 200, None  # موفق
        
    except FloodWait as e:
        # مدیریت FloodWait
        wait_time = e.value
        print(f"FloodWait برای {user_id} - صبر برای {wait_time} ثانیه")
        await asyncio.sleep(wait_time)
        # تلاش مجدد پس از FloodWait
        try:
            await message.copy(chat_id=user_id)
            return 200, None
        except Exception as retry_error:
            return 500, f"{user_id} : خطا پس از FloodWait: {str(retry_error)}\n"
            
    except UserIsBlocked:
        return 400, f"{user_id} : کاربر ربات را بلاک کرده است\n"
        
    except InputUserDeactivated:
        return 400, f"{user_id} : کاربر غیرفعال شده است\n"
        
    except PeerIdInvalid:
        return 400, f"{user_id} : آیدی کاربر نامعتبر است\n"
        
    except ChannelPrivate:
        return 400, f"{user_id} : کانال خصوصی است\n"
        
    except ChatWriteForbidden:
        return 400, f"{user_id} : امکان ارسال پیام وجود ندارد\n"
        
    except UserNotParticipant:
        return 400, f"{user_id} : کاربر در کانال عضو نیست\n"
        
    except ChatAdminRequired:
        return 400, f"{user_id} : نیاز به دسترسی ادمین\n"
        
    except Exception as e:
        error_msg = f"{user_id} : خطای غیرمنتظره: {str(e)}\n"
        print(f"خطا در ارسال به {user_id}: {e}")
        return 500, error_msg