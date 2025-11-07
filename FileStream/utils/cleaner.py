import asyncio

async def cleaner(app, db):
    while True:
        await asyncio.sleep(10)
        await db.cur.execute("SELECT unique_id, user_id FROM files WHERE expire_at < ?", (int(time.time()),))
        expired = await db.cur.fetchall()
        
        for uid, owner in expired:
            for chat_id, msg_id in SENT_MSGS.get(uid, []):
                try: await app.bot.delete_message(chat_id, msg_id)
                except: pass
            try: await app.bot.send_message(owner, "فایل شما منقضی شد.")
            except: pass
            
            SENT_MSGS.pop(uid, None)
            USER_ACCESS.pop(uid, None)
        
        await db.cur.execute("DELETE FROM files WHERE expire_at < ?", (int(time.time()),))
        await db.con.commit()