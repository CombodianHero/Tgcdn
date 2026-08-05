"""
Web-based Telegram login flow: phone number -> code -> (2FA password if
enabled) -> session string, hot-swapped into the running app's shared client.

Pending logins are held in memory, keyed by a random login_id, so the
frontend can complete a multi-step form without re-sending the phone number
each time.
"""
import uuid

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
)

from app.telegram_client import API_ID, API_HASH, replace_with_logged_in_client

_pending: dict[str, dict] = {}


async def start_login(phone: str) -> str:
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        await client.disconnect()
        raise ValueError("That phone number looks invalid (use international format, e.g. +14155551234)")

    login_id = str(uuid.uuid4())
    _pending[login_id] = {
        "client": client,
        "phone": phone,
        "phone_code_hash": sent.phone_code_hash,
    }
    return login_id


async def submit_code(login_id: str, code: str) -> dict:
    entry = _pending.get(login_id)
    if not entry:
        raise ValueError("Login session expired or invalid -- start again")

    client = entry["client"]
    try:
        await client.sign_in(
            phone=entry["phone"], code=code, phone_code_hash=entry["phone_code_hash"]
        )
    except SessionPasswordNeededError:
        return {"status": "password_required"}
    except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
        raise ValueError(str(e))

    await replace_with_logged_in_client(client)
    del _pending[login_id]
    return {"status": "logged_in"}


async def submit_password(login_id: str, password: str) -> dict:
    entry = _pending.get(login_id)
    if not entry:
        raise ValueError("Login session expired or invalid -- start again")

    client = entry["client"]
    await client.sign_in(password=password)
    await replace_with_logged_in_client(client)
    del _pending[login_id]
    return {"status": "logged_in"}
