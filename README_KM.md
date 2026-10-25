# Telegram MP3 Bot (Webhook + Worker)

គម្រោងគំរូនេះមាន៖
- Telegram webhook (FastAPI) លើ Vercel: ស្វែងរក YouTube ៥ លទ្ធផល និងបង្ហាញ Inline Buttons។
- Python worker (FastAPI + Uvicorn): ទទួលជម្រើសបទ, ប្រើ yt-dlp និង FFmpeg ដើម្បីបង្កើត MP3 ហើយផ្ញើតាម Telegram។
- Cookie file ជាជម្រើសសម្រាប់ការចូលប្រើដែលអ្នកមានសិទ្ធិ។ កុំប្រើដើម្បីរំលងការការពារ ឬទាញយកមាតិកាដែលគ្មានសិទ្ធិ។

## សំខាន់
Vercel Function មិនសមស្របសម្រាប់ការទាញយក/បម្លែងឯកសារធំៗទេ។ Worker ត្រូវដំណើរការលើម៉ាស៊ីនដែលមាន Python, FFmpeg និង HTTPS endpoint អាចទាក់ទងបាន។ Worker ដែលដំណើរការលើ Termux មិនអាចទទួលសំណើពី Vercel តាមអ៊ីនធឺណិតបានទេ លុះត្រាតែមាន HTTPS tunnel ឬ public server។ សម្រាប់ការដំណើរការ 24/7 ប្រើ server/worker ដែលមានស្ថិរភាព។

## 1. បង្កើត Telegram Bot
1. បើក https://t.me/BotFather
2. ផ្ញើ `/newbot` ហើយយក BOT_TOKEN។
3. កុំផ្ញើ Token ទៅអ្នកដទៃ។

## 2. YouTube Data API v3
1. បើក https://console.cloud.google.com/
2. បង្កើត/ជ្រើស Project និងបើក YouTube Data API v3។
3. បង្កើត API Key ហើយកំណត់ restrictions ឱ្យសមស្រប។
4. Search API បង្ហាញលទ្ធផល និង video ID ប៉ុណ្ណោះ មិនមែនឯកសារ MP3 ទេ។

## 3. Deploy webhook ទៅ Vercel
Upload `api/webhook.py`, `requirements.txt`, `vercel.json` ទៅ GitHub ហើយ Import Repository នៅ https://vercel.com/new។
កំណត់ Environment Variables ក្នុង Vercel:
- `BOT_TOKEN`
- `YOUTUBE_API_KEY`
- `WEBHOOK_SECRET`
- `WORKER_URL` (URL public HTTPS របស់ worker)
- `WORKER_SECRET` (secret ដូចគ្នានឹង worker)

Deploy ហើយចម្លង domain របស់ Vercel។

## 4. ដំឡើង Worker
លើម៉ាស៊ីន worker (ឧ. VPS ឬ Termux សម្រាប់សាកល្បង):
```bash
pkg update
pkg install python ffmpeg
pip install -r requirements.txt
```
លើ Termux ត្រូវ clone/copy គម្រោងមកជាមុន។ កំណត់ environment variables:
```bash
export BOT_TOKEN='YOUR_BOT_TOKEN'
export WORKER_SECRET='SAME_SECRET_AS_VERCEL'
export COOKIE_FILE='cookies.txt'
uvicorn worker:app --host 0.0.0.0 --port 8080
# ឬ: python worker.py
```
Worker ត្រូវមាន public HTTPS URL ដែល Vercel អាចហៅបាន។ កុំបើក endpoint ទៅ public ដោយគ្មាន HTTPS និង secret។

## 5. Webhook setup
បន្ទាប់ពី Vercel deploy:
```bash
export BOT_TOKEN='YOUR_BOT_TOKEN'
export WEBHOOK_SECRET='SAME_SECRET_AS_VERCEL'
curl -sS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://YOUR-VERCEL-DOMAIN/api/webhook" \
  -d "secret_token=${WEBHOOK_SECRET}"
```
ពិនិត្យ webhook:
```bash
curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

## 6. Cookies
- កុំ commit `cookies.txt` ទៅ GitHub។
- កុំដាក់ cookies ក្នុង zip ដែលផ្ញើឱ្យអ្នកដទៃ។
- ប្រើតែ cookie export ពីគណនីរបស់អ្នក និងសម្រាប់មាតិកាដែលអ្នកមានសិទ្ធិចូលប្រើ/ទាញយក។
- កុំប្រើ cookies ដើម្បីរំលង paywall, DRM, ឬការរឹតត្បិតចូលប្រើ។
- Cookies មានសុពលភាពដូច session login; ប្រសិនបើលេចធ្លាយ អ្នកដទៃអាចចូលគណនីបាន។ លុប/បញ្ចប់ session ប្រសិនបើលេចធ្លាយ។

## ដែនកំណត់
- YouTube Data API quota អាចអស់។
- yt-dlp មិនអាចធានាថាគ្រប់ URL ឬគ្រប់ប្រភពនឹងដំណើរការបានទេ។
- Telegram មានដែនកំណត់លើការផ្ញើឯកសារ។
- គំរូនេះត្រូវការការធ្វើតេស្ត និងការកំណត់សុវត្ថិភាពបន្ថែមមុនប្រើ production។
