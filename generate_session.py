"""
Run this ONCE, locally, interactively:

    python generate_session.py

It logs you into Telegram with your phone number (like the normal app) and
prints a session string. Paste that string into TG_SESSION_STRING in your
.env file, then never run this script on a public/shared machine again --
the printed string is equivalent to your login, treat it like a password.

After logging in, it also lists your recent dialogs (chats/channels) with
their numeric IDs, so you can pick the private channel to use as storage
and set TG_STORAGE_CHAT_ID in .env.
"""
import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n=== SESSION STRING (put this in TG_SESSION_STRING) ===")
    print(client.session.save())

    print("\n=== YOUR CHATS/CHANNELS (pick one for TG_STORAGE_CHAT_ID) ===")
    for dialog in client.iter_dialogs(limit=30):
        print(f"{dialog.id:>15}   {dialog.name}")

    print(
        "\nTip: create a new *private channel* just for this demo "
        "(e.g. 'My Video Storage'), then re-run this script or check the "
        "Telegram app to find its id in the list above."
    )
