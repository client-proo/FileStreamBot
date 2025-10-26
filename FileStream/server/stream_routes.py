import time
import math
import logging
import mimetypes
import traceback
from datetime import datetime
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from FileStream.bot import multi_clients, work_loads, FileStream
from FileStream.config import Telegram, Server
from FileStream.server.exceptions import FIleNotFound, InvalidHash
from FileStream import utils, StartTime, __version__
from FileStream.utils.render_template import render_page

routes = web.RouteTableDef()


@routes.get("/status", allow_head=True)
async def root_route_handler(_):
    return web.json_response(
        {
            "server_status": "running",
            "uptime": utils.get_readable_time(time.time() - StartTime),
            "telegram_bot": "@" + FileStream.username,
            "connected_bots": len(multi_clients),
            "loads": dict(
                ("bot" + str(c + 1), l)
                for c, (_, l) in enumerate(
                    sorted(work_loads.items(), key=lambda x: x[1], reverse=True)
                )
            ),
            "version": __version__,
        }
    )


@routes.get("/watch/{path}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        return web.Response(text=await render_page(path), content_type='text/html')
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        return web.Response(status=500, text="Internal Server Error")
    except Exception as e:
        logging.error(f"Watch error: {e}")
        return web.Response(status=500, text="Internal Server Error")


@routes.get("/dl/{path}", allow_head=True)
async def download_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        return await media_streamer(request, path)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        return web.Response(status=500, text="Connection error")
    except Exception as e:
        traceback.print_exc()
        logging.critical(e.with_traceback(None))
        logging.debug(traceback.format_exc())
        return web.Response(status=500, text="Server error")


class_cache = {}


async def media_streamer(request: web.Request, db_id: str):
    range_header = request.headers.get("Range", 0)

    # --- چک انقضای لینک ---
    file_doc = await FileStream.db.get_file_by_fileuniqueid(
        user_id=None, file_unique_id=db_id, many=False
    )
    if not file_doc:
        raise web.HTTPNotFound(text="File not found in database")

    if file_doc.get("expire_at") and datetime.utcnow() > file_doc["expire_at"]:
        await FileStream.db.file.delete_one({"file_unique_id": db_id})
        raise web.HTTPGone(text="Link expired! This file is no longer available.")

    # --- ادامه استریم ---
    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if Telegram.MULTI_CLIENT:
        logging.info(f"Client {index} serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
    else:
        tg_connect = utils.ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect

    try:
        file_id = await tg_connect.get_file_properties(db_id, multi_clients)
    except Exception as e:
        logging.error(f"File properties error: {e}")
        raise web.HTTPNotFound(text="File not found on Telegram")

    file_size = file_id.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes >= file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            headers={"Content-Range": f"bytes */{file_size}"},
            text="Range not satisfiable"
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)
    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1
    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)

    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    mime_type = file_id.mime_type or mimetypes.guess_type(utils.get_name(file_id))[0] or "application/octet-stream"
    file_name = utils.get_name(file_id)
    disposition = "attachment"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )