"""
Manages the single shared MTProto (Telethon) client used by the whole app.

Unlike the terminal-based setup, this client can start out *unauthenticated*
(no valid session yet) and get hot-swapped for a freshly logged-in client
once someone completes the login panel flow in the browser -- no restart
required.
"""
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

from app import config_store

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

_client: TelegramClient | None = None
_storage_chat_id: int | None = None


def _initial_session_string() -> str:
    # Prefer a session saved locally from a previous panel login; fall back
    # to whatever was set via the TG_SESSION_STRING env var (e.g. generated
    # once via generate_session.py and pasted into your host's secrets).
    cfg = config_store.load()
    return cfg.get("session_string") or os.environ.get("TG_SESSION_STRING", "")


def _initial_storage_chat_id():
    cfg = config_store.load()
    val = cfg.get("storage_chat_id") or os.environ.get("TG_STORAGE_CHAT_ID")
    return int(val) if val else None


async def startup():
    global _client, _storage_chat_id
    _storage_chat_id = _initial_storage_chat_id()
    session_str = _initial_session_string()
    _client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await _client.connect()
    # Intentionally does NOT raise if unauthorized -- the app just starts in
    # a "needs login" state and the frontend shows the login panel.


async def shutdown():
    if _client and _client.is_connected():
        await _client.disconnect()


def get_client() -> TelegramClient:
    if _client is None:
        raise RuntimeError("Telegram client not initialized yet")
    return _client


async def is_ready() -> bool:
    if _client is None:
        return False
    try:
        return await _client.is_user_authorized()
    except Exception:
        return False


def get_storage_chat_id():
    return _storage_chat_id


def set_storage_chat_id(chat_id: int):
    global _storage_chat_id
    _storage_chat_id = chat_id
    config_store.save({"storage_chat_id": chat_id})


async def replace_with_logged_in_client(new_client: TelegramClient):
    """Swap the shared client for one that just finished the login flow,
    and persist its session string so a same-machine restart stays logged in."""
    global _client
    old = _client
    _client = new_client
    session_str = new_client.session.save()
    config_store.save({"session_string": session_str})
    if old is not None and old is not new_client and old.is_connected():
        await old.disconnect()
