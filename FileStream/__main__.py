import sys
import asyncio
import logging
import traceback
from FileStream.config import Telegram, Server
from aiohttp import web
from pyrogram import idle
from FileStream.bot import FileStream
from FileStream.server import web_server

# تنظیم لاگ‌گیری دقیق
logging.basicConfig(
    level=logging.DEBUG,  # تغییر به DEBUG برای جزئیات بیشتر
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

async def start_services():
    logger.info("🚀 Starting FileStream Bot...")
    
    try:
        # شروع ربات
        logger.info("📞 Connecting to Telegram...")
        await FileStream.start()
        bot_info = await FileStream.get_me()
        
        logger.info(f"✅ Bot Started: {bot_info.first_name} (@{bot_info.username})")
        logger.info(f"🆔 Bot ID: {bot_info.id}")
        
        # شروع سرور وب
        logger.info("🌐 Starting Web Server...")
        server = await web_server()
        await server.start()
        logger.info(f"✅ Web Server Started on port {Server.PORT}")
        
        logger.info("🤖 Bot is ready and running!")
        await idle()
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        traceback.print_exc()

async def cleanup():
    try:
        await FileStream.stop()
        logger.info("🛑 Bot stopped successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        logger.info("⏹️ Received interrupt signal")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        traceback.print_exc()
    finally:
        loop.run_until_complete(cleanup())
        loop.close()
        logger.info("👋 Service stopped")