# Avarr Downloader Platform

This repository hosts a FastAPI backend (`api/`) and a React dashboard (`web/`) for orchestrating yt-dlp downloads controlled via Telegram.

## Quick Start

1. **Backend** (`api/`)
   - Copy `.env.example` to `.env` and set Telegram + storage settings (use an absolute `AVARR_DOWNLOAD_ROOT`).
   - Run `uv sync` then `uv run uvicorn avarr.app:app --reload`.
2. **Frontend** (`web/`)
   - Install dependencies with `pnpm install`.
   - Run `pnpm dev` and point `VITE_API_BASE_URL` to the backend (defaults to `http://localhost:8000`).

Visit `http://localhost:5173` to open the dashboard, submit URLs, and monitor job progress. Telegram messages to your bot will enqueue downloads automatically and receive status updates in return.
