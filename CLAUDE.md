# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Avarr is a Telegram-driven yt-dlp download orchestrator with a FastAPI backend (`api/`) and React dashboard (`web/`). Downloads are controlled via Telegram bot messages and monitored through a web interface.

## Development Commands

### Backend (from `api/` directory)

- `uv sync` — install/update dependencies after modifying `pyproject.toml` or `uv.lock`
- `uv run python main.py` — launch FastAPI server via console entry point
- `uv run uvicorn avarr.app:app --reload` — start backend with hot-reload for development
- `uv run pytest` — run all tests
- `uv run pytest -k test_name` — run specific test by name
- `uv run pytest --cov=avarr --cov-report=term-missing` — run tests with coverage report (target >=90% on new modules)
- `uv run ruff check . && uv run ruff format .` — lint and format Python code
- `uv lock --upgrade-package <pkg>` — update specific dependency
- `uv run python apply_migration.py` — apply database schema migrations (interactive)
- `uv run python apply_migration.py --yes` — apply migrations non-interactively

### Frontend (from `web/` directory)

- `pnpm install` — install dependencies
- `pnpm dev` — start Vite dev server (default: http://localhost:5173)
- `pnpm build` — build static bundle for production (output: `dist/`)
- `pnpm lint` — lint TypeScript/React code

### Docker

- `docker-compose up --build` — build and run the full stack in containers
- Backend serves on `AVARR_HOST_PORT` (default: 8080), web UI available at `/app`

## High-Level Architecture

### Backend Flow

1. **Entry Point**: `api/avarr/app.py` creates the FastAPI app via `create_app()` factory
2. **State Management**: App stores singleton instances in `app.state`:
   - `manager`: `DownloadManager` (orchestrates download queue)
   - `notifier`: `TelegramNotifier` (sends/edits Telegram messages)
   - `settings`: `Settings` (environment-based configuration)

3. **Download Pipeline**:
   - Jobs created via API (`/api/jobs`) or Telegram webhook (`/api/telegram/webhook`)
   - `DownloadManager` maintains multi-worker asyncio queue to process yt-dlp downloads concurrently
   - Worker count configurable via `AVARR_MAX_CONCURRENT_DOWNLOADS` (default: 1 for backward compatibility)
   - Each job runs yt-dlp in thread via `asyncio.to_thread` to avoid blocking
   - Progress hooks update database and trigger Telegram notifications based on `AVARR_NOTIFIER_MIN_PERCENT_STEP`
   - Completed downloads stored in `AVARR_DOWNLOAD_ROOT/<job_id>/`, then renamed to sanitized title
   - Metadata written to `metadata.json`, description to `description.txt`

4. **Database**: Uses SQLModel with SQLite (or any SQLAlchemy-compatible DB)
   - Single table: `DownloadJob` with status (`pending`/`running`/`completed`/`failed`)
   - Session management via `database.get_session()` context manager
   - **Migrations**: Manual SQL scripts in `api/migrations/` (no Alembic). Run `uv run python apply_migration.py` after schema changes
   - Jobs support `watched` and `starred` boolean flags for organization

5. **Telegram Integration**:
   - Webhook endpoint validates `X-Telegram-Bot-Api-Secret-Token` header against `AVARR_TELEGRAM_WEBHOOK_SECRET`
   - URL messages trigger job creation, bot replies with progress updates
   - Notifier edits same message for progress/completion to reduce chat noise

6. **API Routers** (in `api/avarr/api/`):
   - `jobs.router`: CRUD for download jobs
   - `telegram.router`: webhook handler for Telegram bot

### Frontend Architecture

- React 19 + Vite + TailwindCSS 4
- Single-page dashboard that polls `/api/jobs` for status updates
- shadcn/ui components for UI primitives (cards, buttons, badges, etc.)
- API calls go to `VITE_API_BASE_URL` (defaults to `http://localhost:8000`)

### Configuration

All settings loaded from environment variables prefixed with `AVARR_` (see `api/avarr/settings.py`):

- `AVARR_DOWNLOAD_ROOT`: **Must be absolute path** where downloads are stored
- `AVARR_DATABASE_URL`: SQLAlchemy connection string
- `AVARR_TELEGRAM_BOT_TOKEN`: Required for Telegram notifications
- `AVARR_TELEGRAM_WEBHOOK_SECRET`: Shared secret for webhook validation
- `AVARR_BASE_EXTERNAL_URL`: Public URL included in Telegram messages
- `AVARR_ALLOWED_SOURCE_DOMAINS`: Optional domain whitelist (e.g., `youtube.com,vimeo.com`)
- `AVARR_NOTIFIER_MIN_PERCENT_STEP`: Minimum progress delta (%) before sending Telegram update
- `AVARR_MAX_CONCURRENT_DOWNLOADS`: Maximum number of simultaneous downloads (1-10, default: 1)

### Key Design Decisions

- **Configurable concurrency**: yt-dlp downloads can be processed in parallel (1-10 workers). Default is 1 to avoid rate limits and resource contention, but can be increased for high-bandwidth environments.
- **Thread-based execution**: yt-dlp runs in threads (`asyncio.to_thread`) since it's blocking I/O
- **Directory renaming**: Downloads initially saved to `<job_id>/`, then renamed to sanitized title for user-friendliness
- **Thumbnail deduplication**: `_dedupe_thumbnails()` removes duplicate entries from yt-dlp metadata before writing JSON
- **Telegram message reuse**: Progress updates edit the same message instead of flooding chat
- **Type hints required**: All public functions must have type annotations
- **Small dataclasses preferred**: Use dataclasses (e.g., `JobContext`, `DownloadResult`) instead of passing dictionaries

### Testing

- Tests go in `api/tests/` mirroring package structure (`test_<module>.py`)
- Fixtures in `tests/conftest.py` for shared state
- Naming: `test_<unit>_<behavior>` (e.g., `test_downloader_handles_private_listing`)
- Mock external services (Telegram API, yt-dlp) to avoid network calls

### Code Style

- Python: PEP 8, snake_case functions/variables, UpperCamelCase classes, 4-space indents
- Keep modules under 300 logical lines; extract helpers to `avarr/utils/*.py` as needed
- TypeScript/React: Follow ESLint config (enforced by `pnpm lint`)
- Commit messages: imperative present-tense (e.g., "Add downloader adapter", not "Added" or "Adds")
