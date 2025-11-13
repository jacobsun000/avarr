## Avarr API

FastAPI server that accepts job requests via REST or Telegram webhook and orchestrates yt-dlp downloads with plugin support.

### Prerequisites
- Python 3.12+
- uv (https://docs.astral.sh/uv/) for dependency management
- Optional: pnpm for the React UI located in `../web`
- ffmpeg CLI available on the system `PATH` (used for automatic MP4 transcodes)

### Environment Variables
Create an `.env` file inside `api/` with at least:

```
AVARR_TELEGRAM_BOT_TOKEN=<bot_token>
AVARR_TELEGRAM_WEBHOOK_SECRET=<random_string>
AVARR_ALLOWED_SOURCE_DOMAINS=example.com,another.example
AVARR_DOWNLOAD_ROOT=downloads
# Optional: parallel ffmpeg workers (default 1)
AVARR_TRANSCODE_WORKERS=2
```

### Install & Run

```
uv sync
uv run uvicorn avarr.app:app --reload
```

Expose `/telegram/webhook` over HTTPS and set it via `BotFather` with the same secret using `setwebhook`. The server automatically enqueues downloads and publishes progress events back to Telegram.
