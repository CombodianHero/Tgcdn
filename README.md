# TG-CDN — Telegram-backed Video Streaming Demo

A working demo that uses a private Telegram channel as video storage and
streams playback to a website with proper HTTP range support (seeking works).
Login happens through an in-app web panel — no terminal or interactive
phone-code prompt needed, which matters on headless hosts like Koyeb.

```
Browser <--range requests--> FastAPI <--MTProto (Telethon)--> Telegram
                                 |
                              SQLite (catalog metadata)
```

## What's included

- `app/main.py` — FastAPI server: login panel API, catalog API, upload
  endpoint, range-based video streaming endpoint
- `app/telegram_client.py` — the shared MTProto client manager (supports
  hot-swapping to a freshly logged-in client without restarting the app)
- `app/auth_flow.py` — the phone → code → 2FA login state machine
- `app/config_store.py` — tiny JSON file that remembers your session string
  and chosen storage channel across restarts (same machine only)
- `app/db.py` — SQLite metadata store (titles, file sizes, Telegram pointers)
- `generate_session.py` — optional terminal-based login script, if you'd
  rather not use the web panel
- `static/index.html` — the demo frontend: login panel, storage-channel
  picker, upload form, catalog, player

## Setup

### 1. Get API credentials

Go to https://my.telegram.org → **API Development Tools** → create an app.
You'll get an `api_id` and `api_hash`. These identify your *application*,
not your Telegram account — they don't change between logins.

### 2. Install dependencies

```bash
cd telegram-video-cdn
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in `TG_API_ID`, `TG_API_HASH`, and pick a private value for
`UPLOAD_SECRET`. Leave `TG_SESSION_STRING` and `TG_STORAGE_CHAT_ID` blank —
you'll set those through the web panel in the next step.

### 4. Run it

```bash
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000**.

### 5. Log in through the panel

1. Enter your **admin secret** (the `UPLOAD_SECRET` value) and your phone
   number in international format (e.g. `+14155551234`) → **Send login code**
2. Telegram sends a code to your Telegram app (or SMS) → enter it →
   **Verify code**
3. If your account has two-factor auth enabled, you'll be asked for that
   password too → **Verify password**
4. Once logged in, pick which chat/channel to use as video storage from the
   dropdown → **Use this channel** (create a dedicated private channel for
   this beforehand if you don't already have one)
5. The main upload/catalog UI appears — you're ready to upload and play videos

At this point the server holds a live, authenticated Telegram session in
memory — no further login steps are needed while the process keeps running.

## Deploying to a host like Koyeb

1. Push this project to a Git repo, connect it to Koyeb, set the build/run
   command to `uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. Set `TG_API_ID`, `TG_API_HASH`, and `UPLOAD_SECRET` as Koyeb environment
   variables/secrets (Koyeb dashboard → Secrets, then reference them as env
   vars — see Koyeb's docs on Secrets)
3. Deploy. Leave `TG_SESSION_STRING` unset.
4. Open your Koyeb app's public URL and complete the login panel (step 5
   above) — this logs the *running* server in, live, no redeploy needed.
5. **Important on ephemeral hosts:** `app/config_store.py` saves your
   session to local disk so it survives in-place restarts, but many
   platforms (Koyeb included, depending on plan/config) wipe local disk on
   redeploy. After logging in through the panel, you can fetch the current
   session string by checking `data/runtime_config.json` (if you have shell
   access) or by re-running `generate_session.py` locally once and setting
   `TG_SESSION_STRING` as a permanent Koyeb secret — that way a redeploy
   doesn't force you back through the login panel every time.

## How it works

1. **Login (panel)** — `POST /api/auth/send-code` creates a temporary
   Telethon client and asks Telegram to text/send a code. `POST
   /api/auth/verify-code` completes the sign-in (or reports that 2FA is
   needed). Once fully signed in, `replace_with_logged_in_client()` swaps
   this new authenticated client in as the app's shared client — the one
   used for every upload and stream from then on.
2. **Storage channel** — `GET /api/auth/dialogs` lists your chats via
   `iter_dialogs()`; picking one calls `POST /api/auth/storage-chat`, which
   is remembered for all future uploads.
3. **Upload** — the frontend posts a file + title + secret to
   `/api/upload`. The server saves it to a temp file, then calls
   `client.send_file(...)` to send it into your chosen storage channel.
   Telegram returns a `message.id`; that plus the chat id, file size, and
   mime type get saved as one row in SQLite as your internal `video_id`.
4. **Catalog** — `/api/videos` reads only from SQLite — Telegram is never
   touched just to list videos, so the catalog loads instantly.
5. **Playback** — `/video/{id}` looks up the Telegram pointer, resolves the
   message, and uses `client.iter_download(offset=..., limit=...)` to pull
   exactly the byte range the browser's `Range` header asked for, streaming
   it straight back. This is what makes seeking work smoothly.

## Known limitations (this is a demo, not production)

- **No caching layer.** Every playback re-fetches from Telegram. Add a CDN
  or local disk cache in front of `/video/{id}` for real traffic.
- **Single MTProto session.** Heavy concurrent streaming can trigger
  Telegram's flood-wait limits.
- **`UPLOAD_SECRET` gates everything** (login panel + uploads) as a single
  shared string — fine for a demo/personal project, not real multi-user auth.
- **No thumbnails**, no resumable uploads — see the original demo notes for
  extension ideas (ffmpeg thumbnails, S3-backed catalog images, etc).
- **Login panel is exposed to anyone with your URL and admin secret.**
  Keep `UPLOAD_SECRET` private — anyone with it can trigger login attempts
  against the phone number they enter, and can re-point your storage
  channel.

## Extending this

- Add a `local_cache` table + disk cache for repeat playback.
- Add real per-user auth in front of the admin/login panel.
- Put the streaming endpoint behind a CDN with range-request caching enabled.
- Swap SQLite for Postgres once you have concurrent writers.
