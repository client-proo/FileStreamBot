import time

LAST_SEND = {}
USER_ACCESS = {}
SENT_MSGS = {}

def check_spam(user_id):
    if user_id in LAST_SEND and time.time() - LAST_SEND[user_id] < 120:
        left = 120 - int(time.time() - LAST_SEND[user_id])
        m, s = divmod(left, 60)
        return True, f"صبر کن!\n{m} دقیقه و {s} ثانیه دیگه"
    LAST_SEND[user_id] = time.time()
    return False, ""

def block_reuse(unique_id, user_id):
    if unique_id in USER_ACCESS and user_id in USER_ACCESS[unique_id]:
        if time.time() - USER_ACCESS[unique_id][user_id] < 21600:  # 6 ساعت
            return True
    USER_ACCESS.setdefault(unique_id, {})[user_id] = time.time()
    return False

def track(unique_id, chat_id, msg_id):
    SENT_MSGS.setdefault(unique_id, []).append((chat_id, msg_id))