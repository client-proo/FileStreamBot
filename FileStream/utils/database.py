import pymongo
import time
import motor.motor_asyncio
from bson.objectid import ObjectId
from bson.errors import InvalidId
from FileStream.server.exceptions import FileNotFound  # درست شد!
from FileStream.config import Telegram
import jdatetime

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.black = self.db.blacklist
        self.file = self.db.file

    # --------------------- [ NEW USER ] --------------------- #
    def new_user(self, id):
        return dict(
            id=id,
            join_date=time.time(),
            Links=0,
            Plan="Free"
        )

    # --------------------- [ ADD USER ] --------------------- #
    async def add_user(self, id):
        user = self.new_user(id)
        await self.col.insert_one(user)

    # --------------------- [ GET USER ] --------------------- #
    async def get_user(self, id):
        return await self.col.find_one({'id': int(id)})

    # --------------------- [ COUNTS ] --------------------- #
    async def total_users_count(self):
        return await self.col.count_documents({})

    async def get_all_users(self):
        return self.col.find({})

    # --------------------- [ DELETE USER ] --------------------- #
    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    # --------------------- [ BAN SYSTEM ] --------------------- #
    def black_user(self, id):
        return dict(id=id, ban_date=time.time())

    async def ban_user(self, id):
        await self.black.insert_one(self.black_user(id))

    async def unban_user(self, id):
        await self.black.delete_one({'id': int(id)})

    async def is_user_banned(self, id):
        return bool(await self.black.find_one({'id': int(id)}))

    async def total_banned_users_count(self):
        return await self.black.count_documents({})

    # --------------------- [ ADD FILE ] --------------------- #
    async def add_file(self, file_info, expire_seconds=None):
        file_info["time"] = time.time()
        file_info["expire_at"] = None
        file_info["expires_in"] = 0

        if expire_seconds:
            file_info["expire_at"] = time.time() + expire_seconds
            file_info["expires_in"] = expire_seconds

        old = await self.get_file_by_fileuniqueid(file_info["user_id"], file_info["file_unique_id"])
        if old:
            return old["_id"]

        await self.count_links(file_info["user_id"], "+")
        return (await self.file.insert_one(file_info)).inserted_id

    # --------------------- [ FIND FILES ] --------------------- #
    async def find_files(self, user_id, range):
        query = {"user_id": user_id}
        cursor = self.file.find(query)
        cursor.skip(range[0] - 1).limit(range[1] - range[0] + 1).sort('_id', pymongo.DESCENDING)
        total = await self.file.count_documents(query)
        return cursor, total

    async def get_file(self, _id):
        try:
            file_info = await self.file.find_one({"_id": ObjectId(_id)})
            if not file_info:
                raise FileNotFound
            return file_info
        except InvalidId:
            raise FileNotFound

    async def get_file_by_fileuniqueid(self, user_id, file_unique_id, many=False):
        if many:
            return self.file.find({"file_unique_id": file_unique_id})
        return await self.file.find_one({"user_id": user_id, "file_unique_id": file_unique_id})

    # --------------------- [ TOTAL FILES ] --------------------- #
    async def total_files(self, id=None):
        if id:
            return await self.file.count_documents({"user_id": id})
        return await self.file.count_documents({})

    # --------------------- [ DELETE ] --------------------- #
    async def delete_one_file(self, _id):
        await self.file.delete_one({'_id': ObjectId(_id)})

    async def delete_expired_file(self, _id):
        await self.file.delete_one({"_id": ObjectId(_id)})

    # --------------------- [ UPDATE ] --------------------- #
    async def update_file_ids(self, _id, file_ids: dict):
        await self.file.update_one({"_id": ObjectId(_id)}, {"$set": {"file_ids": file_ids}})

    # --------------------- [ EXPIRED FILES — بدون async ] --------------------- #
    def get_expired_files(self):  # بدون async → cursor برمی‌گردونه
        return self.file.find({
            "expire_at": {"$lt": time.time(), "$ne": None}
        })

    # --------------------- [ COOLDOWN ] --------------------- #
    async def get_user_last_link_time(self, user_id):
        last = await self.file.find_one(
            {"user_id": user_id, "expire_at": {"$ne": None}},
            sort=[("time", pymongo.DESCENDING)]
        )
        return last["time"] if last else 0

    async def is_user_on_cooldown(self, user_id):
        if not Telegram.SPAM_PROTECTION:
            return False
        last_time = await self.get_user_last_link_time(user_id)
        return (time.time() - last_time) < Telegram.USER_COOLDOWN_SECONDS

    # --------------------- [ PAID SYSTEM ] --------------------- #
    async def link_available(self, user_id):
        user = await self.get_user(user_id)
        if not user:
            return False
        if user.get("Plan") == "Plus":
            return "Plus"
        files = await self.total_files(user_id)
        return files < 11

    async def count_links(self, user_id, operation: str):
        if operation == "-":
            await self.col.update_one({"id": user_id}, {"$inc": {"Links": -1}})
        elif operation == "+":
            await self.col.update_one({"id": user_id}, {"$inc": {"Links": 1}})