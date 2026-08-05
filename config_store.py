"""
Minimal persisted runtime config (session string, storage chat id) so the
app can survive a restart without re-login, on hosts with a writable disk.

Note: on platforms like Koyeb, the local filesystem may not persist across
redeploys. Once you log in through the panel, copy the printed session
string into a proper Koyeb secret/env var (TG_SESSION_STRING) so a redeploy
doesn't force you to log in again. This file is a convenience for same-boot
restarts, not a substitute for that.
"""
import json
import os

DATA_DIR = os.environ.get("DATA_DIR", "./data")
CONFIG_PATH = os.path.join(DATA_DIR, "runtime_config.json")


def load() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save(partial: dict) -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    data = load()
    data.update(partial)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f)
    return data
