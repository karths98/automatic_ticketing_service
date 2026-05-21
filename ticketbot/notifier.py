"""Send messages to Telegram via the Bot API."""

from __future__ import annotations

import html as html_lib

import requests

from .config import TelegramConfig

API_BASE = "https://api.telegram.org"


class NotifyError(RuntimeError):
    """Raised when a Telegram message could not be delivered."""


class TelegramNotifier:
    def __init__(self, config: TelegramConfig, timeout: int = 15) -> None:
        self._config = config
        self._timeout = timeout

    def send(self, text: str, *, disable_preview: bool = False) -> None:
        """Send an HTML-formatted message to the configured chat."""
        url = f"{API_BASE}/bot{self._config.bot_token}/sendMessage"
        payload = {
            "chat_id": self._config.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            raise NotifyError(f"failed to reach Telegram: {exc}") from exc

        if resp.status_code != 200:
            detail = _describe_error(resp)
            raise NotifyError(f"Telegram API error ({resp.status_code}): {detail}")

    def test_connection(self) -> None:
        """Send a confirmation message; used to verify setup."""
        self.send(
            "✅ <b>Live Nation onsale monitor</b> is connected.\n"
            "You'll get a message here the moment a watched event goes on sale."
        )

    def notify_status(self, event_name: str, url: str, status_label: str) -> None:
        """Send a formatted onsale alert for an event."""
        safe_name = html_lib.escape(event_name)
        safe_url = html_lib.escape(url, quote=True)
        self.send(
            f"\U0001f3ab <b>{safe_name}</b>\n"
            f"Status: <b>{html_lib.escape(status_label)}</b>\n\n"
            f'➡️ <a href="{safe_url}">Open the event page now</a>\n\n'
            "Jump in, clear the queue, and complete payment yourself."
        )


def _describe_error(resp: requests.Response) -> str:
    try:
        body = resp.json()
        return str(body.get("description", body))
    except ValueError:
        return resp.text[:200]
