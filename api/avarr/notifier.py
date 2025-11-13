"""Telegram notifier helper."""

from __future__ import annotations

from typing import Optional

import httpx


class TelegramNotifier:
    """Send messages to Telegram chats if a bot token is configured."""

    def __init__(self, bot_token: Optional[str]) -> None:
        self.bot_token = bot_token
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        if self.bot_token and not self._client:
            self._client = httpx.AsyncClient(timeout=30)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: Optional[int] = None,
    ) -> Optional[int]:
        if not self.bot_token or not self._client:
            return None

        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        response = await self._client.post(self._api_url("sendMessage"), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {}).get("message_id")

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        if not self.bot_token or not self._client:
            return
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
        response = await self._client.post(self._api_url("editMessageText"), json=payload)
        if response.status_code == 400:
            # Ignore cases where the message was already edited or cannot be edited
            return
        response.raise_for_status()

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"


__all__ = ["TelegramNotifier"]
