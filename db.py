"""
Lightweight SQLite metadata store.

We never query Telegram to build the catalog page -- only when someone
actually plays a video. This table is the source of truth for the site.
"""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", "./data")
DB_PATH = os.path.join(DATA_DIR, "videos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tg_chat_id INTEGER NOT NULL,
    tg_message_id INTEGER NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL
);
"""


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_conn() as conn:
        conn.execute(SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def insert_video(title, tg_chat_id, tg_message_id, file_size, mime_type):
    video_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO videos
               (id, title, tg_chat_id, tg_message_id, file_size, mime_type, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'ready', ?)""",
            (
                video_id,
                title,
                tg_chat_id,
                tg_message_id,
                file_size,
                mime_type,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    return video_id


def list_videos():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, file_size, mime_type, created_at FROM videos ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_video(video_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None
