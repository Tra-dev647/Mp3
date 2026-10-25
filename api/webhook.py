import hmac
import os
import re

import httpx
from fastapi import FastAPI, Request, Response

BOT_TOKEN = os.environ["BOT_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
WORKER_URL = os.environ["WORKER_URL"].rstrip("/")
WORKER_SECRET = os.environ["WORKER_SECRET"]

MAX_BODY = 100_000
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
    try:
        r = await client.post(
            WORKER_URL + "/download",
            json={"video_id": video_id, "chat_id": chat_id},
            headers={"X-Worker-Secret": WORKER_SECRET},
        )
        r.raise_for_status()
        await send_text(
            client, chat_id,
            r.json().get("message", "បានបញ្ជូនសំណើទៅ Worker។"),
        )
    except Exception as exc:
        print("Worker request failed:", repr(exc))
        await send_text(
            client,
            chat_id,
            "Worker មិនអាចទទួលសំណើបានទេ។ សូមពិនិត្យ WORKER_URL "
            "និង Worker ថាកំពុងដំណើរការឬអត់។",
        )


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

        async with httpx.AsyncClient(timeout=12) as client:
            if "message" in update:
                await handle_message(client, update["message"])
            elif "callback_query" in update:
                await handle_callback(client, update["callback_query"])
        return Response("ok", media_type="text/plain")
    except Exception as exc:
        print("Webhook error:", repr(exc))
        return Response("handled", media_type="text/plain")
