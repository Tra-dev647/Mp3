# Telegram Audio Bot (Vercel សុទ្ធ)

- `api/webhook.py` (FastAPI) ធ្វើការទាំងអស់លើ Vercel៖ ស្វែងរក YouTube ៥ លទ្ធផល, ទាញយកសំឡេងដោយ yt-dlp, ហើយផ្ញើតាម Telegram។
- គ្មាន Worker ទេ។ គ្មាន FFmpeg លើ Vercel ដូច្នេះផ្ញើជា **M4A** (មិនមែន MP3)។

## ដែនកំណត់ (សំខាន់)
- YouTube តែងរារាំង IP របស់ Vercel ("Sign in to confirm you're not a bot") ដូច្នេះអាចបរាជ័យញឹកញាប់។ Cookies (ប្រើតែគណនី/មាតិកាដែលអ្នកមានសិទ្ធិ) អាចជួយខ្លះ។
- ពេលអតិបរមា 60 វិនាទី; បទវែង ឬធំជាង 45MB នឹងបរាជ័យ។
- Telegram អាចផ្ញើ webhook ម្តងទៀត បើយឺត។

## Environment Variables (Vercel)
- `BOT_TOKEN`, `YOUTUBE_API_KEY`, `WEBHOOK_SECRET`
- `COOKIES_TXT` (ជាជម្រើស៖ ខ្លឹមសារ cookies.txt ទាំងមូល)

## Webhook
```bash
curl -sS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://YOUR-VERCEL-DOMAIN/api/webhook" \
  -d "secret_token=${WEBHOOK_SECRET}"
curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```
