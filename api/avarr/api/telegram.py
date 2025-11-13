"""Telegram webhook endpoint."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from ..database import session_dependency
from ..download_manager import DownloadManager, is_url_allowed
from ..models import DownloadJob
from ..settings import get_settings


router = APIRouter(prefix="/telegram", tags=["telegram"])
settings = get_settings()


def _get_manager(request: Request) -> DownloadManager:
    return request.app.state.manager


def _extract_url(update: Dict[str, Any]) -> tuple[str | None, int | None]:
    message = update.get("message") or update.get("channel_post")
    if not message:
        return None, None
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not text:
        return None, chat_id
    return text.split()[0], chat_id


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    update: Dict[str, Any],
    request: Request,
    session: Session = Depends(session_dependency),
) -> Dict[str, Any]:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if settings.telegram_webhook_secret and secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    url, chat_id = _extract_url(update)
    if not url or not chat_id:
        return {"ok": True}

    if not is_url_allowed(url):
        notifier = request.app.state.notifier
        if notifier.bot_token:
            await notifier.send_message(chat_id, "URL blocked by server policy")
        return {"ok": True}

    job = DownloadJob(source_url=url, telegram_chat_id=chat_id)
    session.add(job)
    session.commit()
    session.refresh(job)

    notifier = request.app.state.notifier
    if notifier.bot_token:
        await notifier.send_message(chat_id, f"Queued download request {job.id}")

    manager = _get_manager(request)
    await manager.enqueue_job(job.id)

    return {"ok": True, "job_id": job.id}
