"""
Telegram-backed video CDN -- demo system, with a web-based login panel.

Endpoints:
  GET  /api/auth/status          -> is a session logged in? is a storage chat set?
  POST /api/auth/send-code       -> step 1: phone number -> sends Telegram login code
  POST /api/auth/verify-code     -> step 2: code -> logs in, or asks for 2FA password
  POST /api/auth/verify-password -> step 2b: 2FA password -> logs in
  GET  /api/auth/dialogs         -> list chats/channels to pick as storage
  POST /api/auth/storage-chat    -> save the chosen storage chat id

  GET  /api/videos               -> catalog (reads local SQLite, not Telegram)
  POST /api/upload                -> uploads a file to the Telegram storage chat
  GET  /video/{video_id}          -> streams the video with HTTP range support
  GET  /                          -> demo frontend (static/index.html)

Run:
  uvicorn app.main:app --reload --port 8000
"""
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db, auth_flow, telegram_client as tg

ADMIN_SECRET = os.environ.get("UPLOAD_SECRET", "change-me")

app = FastAPI(title="Telegram Video CDN Demo")


def require_admin(secret: str):
    if secret != ADMIN_SECRET:
        raise HTTPException(401, "Invalid secret")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    db.init_db()
    await tg.startup()


@app.on_event("shutdown")
async def shutdown():
    await tg.shutdown()


# ---------------------------------------------------------------------------
# Auth / login panel
# ---------------------------------------------------------------------------
class SendCodeBody(BaseModel):
    secret: str
    phone: str


class VerifyCodeBody(BaseModel):
    secret: str
    login_id: str
    code: str


class VerifyPasswordBody(BaseModel):
    secret: str
    login_id: str
    password: str


class StorageChatBody(BaseModel):
    secret: str
    chat_id: int


@app.get("/api/auth/status")
async def auth_status():
    logged_in = await tg.is_ready()
    return {
        "logged_in": logged_in,
        "storage_chat_id": tg.get_storage_chat_id(),
    }


@app.post("/api/auth/send-code")
async def auth_send_code(body: SendCodeBody):
    require_admin(body.secret)
    try:
        login_id = await auth_flow.start_login(body.phone)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"login_id": login_id}


@app.post("/api/auth/verify-code")
async def auth_verify_code(body: VerifyCodeBody):
    require_admin(body.secret)
    try:
        result = await auth_flow.submit_code(body.login_id, body.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@app.post("/api/auth/verify-password")
async def auth_verify_password(body: VerifyPasswordBody):
    require_admin(body.secret)
    try:
        result = await auth_flow.submit_password(body.login_id, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@app.get("/api/auth/dialogs")
async def auth_dialogs(secret: str):
    require_admin(secret)
    if not await tg.is_ready():
        raise HTTPException(409, "Not logged in yet")
    client = tg.get_client()
    dialogs = []
    async for d in client.iter_dialogs(limit=30):
        dialogs.append({"id": d.id, "name": d.name})
    return dialogs


@app.post("/api/auth/storage-chat")
async def auth_storage_chat(body: StorageChatBody):
    require_admin(body.secret)
    tg.set_storage_chat_id(body.chat_id)
    return {"storage_chat_id": body.chat_id}


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
@app.get("/api/videos")
async def api_list_videos():
    return db.list_videos()


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def api_upload(
    title: str = Form(...),
    secret: str = Form(...),
    file: UploadFile = File(...),
):
    require_admin(secret)

    if not await tg.is_ready():
        raise HTTPException(409, "Not logged in to Telegram yet -- complete the login panel first")

    storage_chat_id = tg.get_storage_chat_id()
    if not storage_chat_id:
        raise HTTPException(409, "No storage channel selected yet -- pick one in the panel first")

    client = tg.get_client()

    suffix = os.path.splitext(file.filename or "")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)

    try:
        message = await client.send_file(
            storage_chat_id,
            tmp_path,
            caption=title,
            force_document=False,
        )
    finally:
        os.remove(tmp_path)

    tg_file = message.file
    video_id = db.insert_video(
        title=title,
        tg_chat_id=storage_chat_id,
        tg_message_id=message.id,
        file_size=tg_file.size,
        mime_type=tg_file.mime_type or "video/mp4",
    )

    return {"id": video_id, "title": title, "file_size": tg_file.size}


# ---------------------------------------------------------------------------
# Streaming with HTTP Range support
# ---------------------------------------------------------------------------
@app.get("/video/{video_id}")
async def stream_video(video_id: str, request: Request, range: str | None = Header(default=None)):
    if not await tg.is_ready():
        raise HTTPException(409, "Not logged in to Telegram")

    record = db.get_video(video_id)
    if not record:
        raise HTTPException(404, "Video not found")

    client = tg.get_client()
    message = await client.get_messages(record["tg_chat_id"], ids=record["tg_message_id"])
    if not message or not message.media:
        raise HTTPException(404, "Source file no longer available on Telegram")

    file_size = record["file_size"]
    mime_type = record["mime_type"]

    if range:
        start_str, _, end_str = range.replace("bytes=", "").partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    else:
        start = 0
        end = file_size - 1

    end = min(end, file_size - 1)
    chunk_size = (end - start) + 1

    async def file_iterator():
        async for chunk in client.iter_download(message.media, offset=start, limit=chunk_size):
            yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": mime_type,
        "Cache-Control": "public, max-age=3600",
    }

    status_code = 206 if range else 200
    return StreamingResponse(
        file_iterator(),
        status_code=status_code,
        headers=headers,
        media_type=mime_type,
    )


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
