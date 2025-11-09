import pymongo
import time
import motor.motor_asyncio
from bson.objectid import ObjectId
from bson.errors import InvalidId
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.black = self.db.blacklist
        self.file = self.db.file

#---------------------[ NEW USER ]---------------------#
    def new_user(self, id):
        return dict(
            id=id,
            join_date=time.time(),
            Links=0,
            last_send_time=0
        )

# ---------------------[ ADD USER ]---------------------#
    async def add_user(self, id):
        user = self.new_user(id)
        await self.col.insert_one(user)

# ---------------------[ GET USER ]---------------------#
    async def get_user(self, id):
        user = await self.col.find_one({'id': int(id)})
        return user

# ---------------------[ CHECK USER ]---------------------#
    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users

# ---------------------[ REMOVE USER ]---------------------#
    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

# ---------------------[ BAN, UNBAN USER ]---------------------#
    def black_user(self, id):
        return dict(
            id=id,
            ban_date=time.time()
        )

    async def ban_user(self, id):
        user = self.black_user(id)
        await self.black.insert_one(user)

    async def unban_user(self, id):
        await self.black.delete_one({'id': int(id)})

    async def is_user_banned(self, id):
        user = await self.black.find_one({'id': int(id)})
        return True if user else False

    async def total_banned_users_count(self):
        count = await self.black.count_documents({})
        return count

# ---------------------[ ADD FILE TO DB ]---------------------#
    async def add_file(self, file_info):
        file_info["time"] = time.time()
        
        # فقط فایل‌های فعال (غیر منقضی) رو چک کن
        expire_threshold = time.time() - Telegram.EXPIRE_TIME
        fetch_old = await self.file.find_one({
            "user_id": file_info["user_id"],
            "file_unique_id": file_info["file_unique_id"],
            "time": {"$gt": expire_threshold}
        })
        
        if fetch_old:
            return fetch_old["_id"]  # فایل فعال → برگردون همون
        else:
            await self.count_links(file_info["user_id"], "+")
            return (await self.file.insert_one(file_info)).inserted_id

# ---------------------[ FIND FILE IN DB ]---------------------#
    async def find_files(self, user_id, range):
        user_files = self.file.find({"user_id": user_id})
        user_files.skip(range[0] - 1)
        user_files.limit(range[1] - range[0] + 1)
        user_files.sort('_id', pymongo.DESCENDING)
        total_files = await self.file.count_documents({"user_id": user_id})
        return user_files, total_files

    async def get_file(self, _id):
        try:
            file_info = await self.file.find_one({"_id": ObjectId(_id)})
            if not file_info:
                raise FIleNotFound
            return file_info
        except InvalidId:
            raise FIleNotFound

    async def get_file_by_fileuniqueid(self, id, file_unique_id, many=False):
        expire_threshold = time.time() - Telegram.EXPIRE_TIME
        query = {
            "user_id": id,
            "file_unique_id": file_unique_id,
            "time": {"$gt": expire_threshold}
        }
        if many:
            return self.file.find(query)
        else:
            return await self.file.find_one(query)

# ---------------------[ TOTAL FILES ]---------------------#
    async def total_files(self, id=None):
        if id:
            return await self.file.count_documents({"user_id": id})
        return await self.file.count_documents({})

# ---------------------[ DELETE FILES ]---------------------#
    async def delete_one_file(self, _id):
        await self.file.delete_one({'_id': ObjectId(_id)})

# ---------------------[ UPDATE FILES ]---------------------#
    async def update_file_ids(self, _id, file_ids: dict):
        await self.file.update_one({"_id": ObjectId(_id)}, {"$set": {"file_ids": file_ids}})

# ---------------------[ PAID SYS ]---------------------#
    async def count_links(self, id, operation: str):
        if operation == "-":
            await self.col.update_one({"id": id}, {"$inc": {"Links": -1}})
        elif operation == "+":
            await self.col.update_one({"id": id}, {"$inc": {"Links": 1}})

# ---------------------[ CHECK REPEAT (تا انقضای لینک) ]---------------------#
    async def check_repeat(self, user_id, file_unique_id):
        expire_threshold = time.time() - Telegram.EXPIRE_TIME
        
        last_file = await self.file.find_one(
            {
                "user_id": user_id,
                "file_unique_id": file_unique_id,
                "time": {"$gt": expire_threshold}
            },
            sort=[("time", -1)]
        )
        
        if last_file:
            last_time = last_file['time']
            remaining = int(Telegram.EXPIRE_TIME - (time.time() - last_time))
            return True, remaining  # فایل هنوز فعال است
        return False, 0  # فایل منقضی شده → اجازه آپلود

# ---------------------[ CHECK SPAM ]---------------------#
    async def check_spam(self, user_id):
        user = await self.get_user(user_id)
        if not user:
            return 0, False
        last_send = user.get('last_send_time', 0)
        remaining = Telegram.ANTI_SPAM_TIME - (time.time() - last_send)
        if remaining > 0:
            return remaining, True
        await self.col.update_one({'id': user_id}, {'$set': {'last_send_time': time.time()}})
        return 0, False