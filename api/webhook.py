import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ["BOT_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
WORKER_URL = os.environ["WORKER_URL"].rstrip("/")
WORKER_SECRET = os.environ["WORKER_SECRET"]


def post_json(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def telegram(method, payload):
    return post_json(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", payload
    )


def search_songs(query):
    params = urllib.parse.urlencode({
        "part": "snippet",
        "type": "video",
        "maxResults": 5,
        "q": query,
        "key": YOUTUBE_API_KEY,
        "safeSearch": "moderate",
    })
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/search?" + params
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        result = json.loads(response.read().decode("utf-8"))

    songs = []
    for item in result.get("items", []):
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


def send_text(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    telegram("sendMessage", payload)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != WEBHOOK_SECRET:
            self.send_response(403)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100_000:
                raise ValueError("Invalid request size")
            update = json.loads(self.rfile.read(length))

            if "message" in update:
                message = update["message"]
                chat_id = message["chat"]["id"]
                text = (message.get("text") or "").strip()

                if text == "/start":
                    send_text(
                        chat_id,
                        "🎵 សូមវាយឈ្មោះបទចម្រៀង ដើម្បីបង្ហាញ ៥ លទ្ធផល។\n"
                        "ចុចប៊ូតុងក្រោមបទដែលចង់បាន ដើម្បីស្នើសុំ MP3។\n"
                        "ប្រើតែសំឡេងដែលអ្នកមានសិទ្ធិទាញយក។"
                    )
                elif text and not text.startswith("/"):
                    if len(text) > 150:
                        send_text(chat_id, "សូមបញ្ចូលឈ្មោះបទខ្លីជាងនេះ។")
                    else:
                        songs = search_songs(text)
                        if not songs:
                            send_text(chat_id, "រកមិនឃើញបទចម្រៀងទេ។")
                        else:
                            lines, keyboard = ["🎵 លទ្ធផល ៥ បទ៖\n"], []
                            for i, song in enumerate(songs, 1):
                                lines.append(
                                    f"{i}. {song['title']}\n👤 {song['channel']}\n"
                                )
                                keyboard.append([{
                                    "text": f"🎧 ជ្រើសបទទី {i}",
                                    "callback_data": "song:" + song["id"],
                                }])
                            send_text(chat_id, "\n".join(lines)[:3900], keyboard)

            elif "callback_query" in update:
                cb = update["callback_query"]
                telegram("answerCallbackQuery", {
                    "callback_query_id": cb["id"],
                    "text": "កំពុងដាក់សំណើ..."
                })
                data = cb.get("data", "")
                if data.startswith("song:"):
                    video_id = data[5:]
                    if not video_id.replace("-", "").replace("_", "").isalnum():
                        raise ValueError("Invalid video ID")
                    chat_id = cb["message"]["chat"]["id"]
                    try:
                        result = post_json(
                            WORKER_URL + "/download",
                            {"video_id": video_id, "chat_id": chat_id},
                            {"X-Worker-Secret": WORKER_SECRET},
                        )
                        send_text(chat_id, result.get(
                            "message", "បានបញ្ជូនសំណើទៅ Worker។"
                        ))
                    except Exception as exc:
                        print("Worker request failed:", repr(exc))
                        send_text(
                            chat_id,
                            "Worker មិនអាចទទួលសំណើបានទេ។ សូមពិនិត្យ WORKER_URL "
                            "និង Worker ថាកំពុងដំណើរការឬអត់។"
                        )

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as exc:
            print("Webhook error:", repr(exc))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"handled")
