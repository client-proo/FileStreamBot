import time

async def add_file(db, **data):
    expire_at = int(time.time()) + 60
    await db.cur.execute(
        """INSERT INTO files 
           (file_id, unique_id, user_id, file_name, file_size, mime_type, expire_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data['file_id'], data['unique_id'], data['user_id'], 
         data['file_name'], data['file_size'], data['mime_type'], expire_at)
    )
    await db.con.commit()
    return expire_at

async def is_expired(db, unique_id):
    await db.cur.execute("SELECT expire_at FROM files WHERE unique_id = ?", (unique_id,))
    row = await db.cur.fetchone()
    return not row or time.time() > row[0]

async def get_expire(db, unique_id):
    await db.cur.execute("SELECT expire_at FROM files WHERE unique_id = ?", (unique_id,))
    row = await db.cur.fetchone()
    return row[0] if row else 0