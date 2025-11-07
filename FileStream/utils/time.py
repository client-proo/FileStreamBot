import jdatetime
import time

def to_shamsi(ts=None):
    if ts is None: ts = time.time()
    return jdatetime.datetime.fromtimestamp(ts).strftime("%Y/%m/%d - %H:%M")

def remaining(seconds):
    s = int(seconds)
    if s <= 0: return "منقضی شده!"
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    p = []
    if h: p.append(f"{h} ساعت")
    if m: p.append(f"{m} دقیقه")
    if s: p.append(f"{s} ثانیه")
    return " و ".join(p) + " باقی مونده"