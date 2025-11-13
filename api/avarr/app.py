"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .database import init_db
from .download_manager import DownloadManager
from .notifier import TelegramNotifier
from .settings import get_settings
from . import get_version


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()

    notifier = TelegramNotifier(settings.telegram_bot_token)
    manager = DownloadManager(notifier)

    app = FastAPI(title="Avarr Downloader", version=get_version())

    app.state.manager = manager
    app.state.notifier = notifier
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - framework hook
        await manager.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover - framework hook
        await manager.stop()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # pragma: no cover - trivial endpoint
        return {"status": "ok"}

    app.include_router(api_router)

    downloads_dir = settings.download_root.resolve()
    if downloads_dir.exists():
        app.mount("/downloads", StaticFiles(directory=downloads_dir), name="downloads")

    webui_dir = Path("webui/dist")
    if webui_dir.exists():
        app.mount("/", StaticFiles(directory=webui_dir, html=True), name="webui")

    return app


app = create_app()


__all__ = ["app", "create_app"]
