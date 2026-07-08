"""Telegram Bot API client (SRS doc 23 — Notification Engine, Telegram channel).

Uses BLACK LION's OWN bot token + chat id (BL_TELEGRAM_*), completely separate
from the old `analyze` bot's TELEGRAM_* — nothing here touches the old bot.

If no token is configured the client logs instead of sending, so the runtime is
safe to boot in any environment (dry-run, CI) without Telegram set up.
"""
from __future__ import annotations

import html

import requests

from ..core import config
from ..core.logging import get_logger

log = get_logger("telegram.client")

_API = "https://api.telegram.org/bot{token}/{method}"


def esc(text: object) -> str:
    """Escape &,<,> so model/AI text can't break Telegram HTML parse mode."""
    return html.escape(str(text), quote=False)


class TelegramClient:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token if token is not None else config.env("BL_TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else config.env("BL_TELEGRAM_CHAT_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _call(self, method: str, payload: dict, timeout: int = 15) -> dict | None:
        if not self.token:
            log.info("TelegramNotConfigured", method=method,
                     preview=str(payload.get("text", ""))[:120])
            return None
        try:
            r = requests.post(_API.format(token=self.token, method=method),
                              json=payload, timeout=timeout)
            body = r.json() if r.content else {}
            if not r.ok:
                log.warning("TelegramError", method=method, status=r.status_code,
                            desc=str(body.get("description", ""))[:150])
            return body
        except requests.RequestException as exc:
            log.warning("TelegramNetworkError", method=method, error=str(exc))
            return None

    def send(self, text: str, chat_id: str | None = None,
             reply_markup: dict | None = None) -> int | None:
        payload = {"chat_id": chat_id or self.chat_id, "text": text,
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = self._call("sendMessage", payload)
        # bad HTML → resend as plain text so delivery never fails on formatting
        if res and not res.get("ok") and "parse" in str(res.get("description", "")).lower():
            payload.pop("parse_mode", None)
            res = self._call("sendMessage", payload)
        return res["result"]["message_id"] if res and res.get("ok") else None

    def send_photo(self, image: bytes, caption: str = "",
                   chat_id: str | None = None) -> int | None:
        """Send a PNG with an HTML caption. Telegram caps captions at 1024 chars,
        so a longer message is sent as a follow-up text instead of being cut."""
        if not self.token:
            log.info("TelegramNotConfigured", method="sendPhoto",
                     preview=str(caption)[:120])
            return None
        cap, overflow = (caption, "") if len(caption) <= 1024 else ("", caption)
        try:
            r = requests.post(
                _API.format(token=self.token, method="sendPhoto"),
                data={"chat_id": chat_id or self.chat_id, "caption": cap,
                      "parse_mode": "HTML"},
                files={"photo": ("signal.png", image, "image/png")}, timeout=30)
            body = r.json() if r.content else {}
            if not r.ok:
                log.warning("TelegramError", method="sendPhoto", status=r.status_code,
                            desc=str(body.get("description", ""))[:150])
        except requests.RequestException as exc:
            log.warning("TelegramNetworkError", method="sendPhoto", error=str(exc))
            return None
        if overflow:
            self.send(overflow, chat_id=chat_id)
        return body["result"]["message_id"] if body.get("ok") else None

    def get_updates(self, offset: int, timeout: int = 20) -> list[dict]:
        res = self._call("getUpdates",
                         {"offset": offset, "timeout": timeout,
                          "allowed_updates": ["message"]}, timeout=timeout + 10)
        return res["result"] if res and res.get("ok") else []
