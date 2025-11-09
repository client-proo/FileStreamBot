import asyncio
import time
from typing import Dict, Any

class BroadcastManager:
    """
    مدیریت پیشرفته ارسال همگانی
    """
    
    def __init__(self):
        self.active_broadcasts: Dict[str, Dict[str, Any]] = {}
        self.broadcast_stats: Dict[str, Dict[str, int]] = {}
    
    async def send_broadcast(self, user_id: int, message, delay: float = 0.1):
        """
        ارسال پیام به کاربر با مدیریت خطا
        """
        try:
            await asyncio.sleep(delay)  # تاخیر برای جلوگیری از FloodWait
            
            # ارسال پیام
            await message.copy(chat_id=user_id)
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def start_broadcast(self, broadcast_id: str, total_users: int):
        """شروع یک broadcast جدید"""
        self.active_broadcasts[broadcast_id] = {
            'start_time': time.time(),
            'total_users': total_users,
            'processed': 0,
            'success': 0,
            'failed': 0
        }
    
    def update_broadcast(self, broadcast_id: str, success: bool):
        """بروزرسانی آمار broadcast"""
        if broadcast_id in self.active_broadcasts:
            self.active_broadcasts[broadcast_id]['processed'] += 1
            if success:
                self.active_broadcasts[broadcast_id]['success'] += 1
            else:
                self.active_broadcasts[broadcast_id]['failed'] += 1
    
    def get_broadcast_progress(self, broadcast_id: str):
        """دریافت پیشرفت broadcast"""
        if broadcast_id in self.active_broadcasts:
            stats = self.active_broadcasts[broadcast_id]
            progress = (stats['processed'] / stats['total_users']) * 100
            elapsed = time.time() - stats['start_time']
            
            return {
                'progress': progress,
                'processed': stats['processed'],
                'total': stats['total_users'],
                'success': stats['success'],
                'failed': stats['failed'],
                'elapsed': elapsed
            }
        return None
    
    def cancel_broadcast(self, broadcast_id: str):
        """لغو broadcast"""
        if broadcast_id in self.active_broadcasts:
            del self.active_broadcasts[broadcast_id]
            return True
        return False


# ایجاد نمونه جهانی
broadcast_manager = BroadcastManager()