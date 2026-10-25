import asyncio
import hmac
import os
import re
import shutil
import tempfile
from pathlib import Path

import httpx
import yt_dlp
from fastapi import FastAPI, Request, Response

BOT_TOKEN = os.environ["BOT_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
COOKIES_TXT = os.environ.get("COOKIES_TXT", "")

MAX_BODY = 100_000
MAX_BYTES = 45 * 1024 * 1024
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")

# Docs/OpenAPI disabled: this endpoint is only meant for Telegram.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


async def telegram(client, method, payload):
    r = await client.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload
    )
    return r.json()


async def send_text(client, chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    await telegram(client, "sendMessage", payload)


async def search_songs(client, query):
    r = await client.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "type": "video",
            "maxResults": 5,
            "q": query,
            "key": YOUTUBE_API_KEY,
            "safeSearch": "moderate",
        },
    )
    r.raise_for_status()

    songs = []
    for item in r.json().get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        songs.append({
            "id": video_id,
            "title": snippet.get("title", "Untitled")[:150],
            "channel": snippet.get("channelTitle", "")[:80],
        })
    return songs


async def handle_message(client, message):
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    if text == "/start":
        await send_text(
            client,
            chat_id,
            "🎵 សូមវាយឈ្មោះបទចម្រៀង ដើម្បីបង្ហាញ ៥ លទ្ធផល។\n"
            "ចុចប៊ូតុងក្រោមបទដែលចង់បាន ដើម្បីស្នើសុំ MP3។\n"
            "ប្រើតែសំឡេងដែលអ្នកមានសិទ្ធិទាញយក។",
        )
        return

    if not text or text.startswith("/"):
        return

    if len(text) > 150:
        await send_text(client, chat_id, "សូមបញ្ចូលឈ្មោះបទខ្លីជាងនេះ។")
        return

    songs = await search_songs(client, text)
    if not songs:
        await send_text(client, chat_id, "រកមិនឃើញបទចម្រៀងទេ។")
        return

    lines, keyboard = ["🎵 លទ្ធផល ៥ បទ៖\n"], []
    for i, song in enumerate(songs, 1):
        lines.append(f"{i}. {song['title']}\n👤 {song['channel']}\n")
        keyboard.append([{
            "text": f"🎧 ជ្រើសបទទី {i}",
            "callback_data": "song:" + song["id"],
        }])
    await send_text(client, chat_id, "\n".join(lines)[:3900], keyboard)


def download_audio(video_id):
    """Blocking: download audio without FFmpeg (m4a preferred). Returns (path, title, folder)."""
    folder = tempfile.mkdtemp(prefix="mp3bot_", dir="/tmp")
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio",
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 1,
        "max_filesize": MAX_BYTES,
        "cachedir": False,  # Vercel filesystem is read-only except /tmp
    }

    # Optional cookies: use only an account/export you are authorized to use.
    if COOKIES_TXT.strip():
        cookie_path = os.path.join(folder, "cookies.txt")
        Path(cookie_path).write_text(COOKIES_TXT, encoding="utf-8")
        options["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=True
            )
        files = [p for p in Path(folder).iterdir() if p.name != "cookies.txt"]
        if not files:
            raise RuntimeError("No audio output")
        path = max(files, key=lambda p: p.stat().st_size)
        if path.stat().st_size > MAX_BYTES:
            raise RuntimeError("File exceeds size limit")
        return path, str(info.get("title", "audio"))[:64], folder
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


async def handle_callback(client, cb):
    await telegram(client, "answerCallbackQuery", {
        "callback_query_id": cb["id"],
        "text": "កំពុងដាក់សំណើ...",
    })

    data = cb.get("data", "")
    if not data.startswith("song:"):
        return

    video_id = data[5:]
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid video ID")

    chat_id = cb["message"]["chat"]["id"]
    await send_text(client, chat_id, "⏳ កំពុងទាញយក សូមរង់ចាំ...")

    folder = None
    try:
        path, title, folder = await asyncio.to_thread(download_audio, video_id)
        is_m4a = path.suffix.lower() in (".m4a", ".mp4")
        method, field = ("sendAudio", "audio") if is_m4a else ("sendDocument", "document")
        with open(path, "rb") as f:
            r = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                data={"chat_id": str(chat_id), "title": title,
                      "caption": "សូមប្រើតែសំឡេងដែលអ្នកមានសិទ្ធិប្រើប្រាស់។"},
                files={field: (f"{title[:40] or 'audio'}{path.suffix}", f)},
                timeout=40,
            )
        r.raise_for_status()
    except Exception as exc:
        print("Download failed:", repr(exc))
        await send_text(
            client,
            chat_id,
            "❌ មិនអាចទាញយកបានទេ។ ប្រហែលជាប្រភពត្រូវបានរារាំង ឬឯកសារធំពេក ឬអស់ពេល។",
        )
    finally:
        if folder:
            shutil.rmtree(folder, ignore_errors=True)


@app.post("/api/webhook")
async def webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        return Response(status_code=403)

    # Always answer 200 after auth so Telegram does not retry endlessly.
    try:
        body = await request.body()
        if not body or len(body) > MAX_BODY:
            raise ValueError("Invalid request size")
        update = await request.json()

        async with httpx.AsyncClient(timeout=15) as client:
            if "message" in update:
                await handle_message(client, update["message"])
            elif "callback_query" in update:
                await handle_callback(client, update["callback_query"])
        return Response("ok", media_type="text/plain")
    except Exception as exc:
        print("Webhook error:", repr(exc))
        return Response("handled", media_type="text/plain")
