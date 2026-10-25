import os
import re
import threading
import tempfile
import shutil
from pathlib import Path

import requests
import yt_dlp
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
WORKER_SECRET = os.environ["WORKER_SECRET"]
COOKIE_FILE = os.environ.get("COOKIE_FILE", "cookies.txt")
MAX_BYTES = 45 * 1024 * 1024
ALLOWED_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def telegram(method, payload=None, files=None, timeout=120):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    response = requests.post(url, data=payload, files=files, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError("Telegram API returned an error")
    return result


def process_download(video_id, chat_id):
    folder = tempfile.mkdtemp(prefix="mp3bot_")
    try:
        options = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(folder, "%(title).80s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "retries": 1,
            "max_filesize": MAX_BYTES,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }

        # Optional cookies: use only an account/export you are authorized to use.
        # Do not use cookies to bypass access restrictions or download unauthorized content.
        if COOKIE_FILE and os.path.isfile(COOKIE_FILE):
            options["cookiefile"] = COOKIE_FILE

        url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        candidates = list(Path(folder).glob("*.mp3"))
        if not candidates:
            raise RuntimeError("No MP3 output")
        path = max(candidates, key=lambda p: p.stat().st_size)
        if path.stat().st_size > MAX_BYTES:
            raise RuntimeError("File exceeds configured size limit")

        title = str(info.get("title", "audio"))[:64]
        with open(path, "rb") as f:
            telegram(
                "sendAudio",
                payload={"chat_id": str(chat_id), "title": title,
                         "caption": "សូមប្រើតែសំឡេងដែលអ្នកមានសិទ្ធិប្រើប្រាស់។"},
                files={"audio": ("audio.mp3", f, "audio/mpeg")},
                timeout=150,
            )
    except Exception as exc:
        print("Download failed:", repr(exc))
        try:
            telegram("sendMessage", {
                "chat_id": str(chat_id),
                "text": "❌ មិនអាចបង្កើត MP3 បានទេ។ សូមពិនិត្យថាប្រភពអាចចូលប្រើបាន "
                        "និងអ្នកមានសិទ្ធិទាញយក។"
            })
        except Exception as send_exc:
            print("Telegram error:", repr(send_exc))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/download")
def download():
    if request.headers.get("X-Worker-Secret", "") != WORKER_SECRET:
        return jsonify({"ok": False, "message": "Forbidden"}), 403

    body = request.get_json(silent=True) or {}
    video_id = str(body.get("video_id", ""))
    chat_id = body.get("chat_id")

    if not ALLOWED_ID.fullmatch(video_id) or not isinstance(chat_id, (int, str)):
        return jsonify({"ok": False, "message": "Invalid request"}), 400

    threading.Thread(
        target=process_download, args=(video_id, chat_id), daemon=True
    ).start()
    return jsonify({
        "ok": True,
        "message": "⏳ បានទទួលសំណើ។ បើអាចទាញយកបាន Bot នឹងផ្ញើ MP3 មកឆាប់ៗនេះ។"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
