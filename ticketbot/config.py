"""Configuration loading: event/poll settings from YAML, secrets from env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_WATCH_FOR = {"on_sale", "sold_out", "not_yet"}


@dataclass
class EventConfig:
    name: str
    url: str
    watch_for: str = "on_sale"
    # Optional per-event keyword overrides for the text-scan fallback.
    keywords: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.url:
            raise ValueError("each event needs a 'name' and a 'url'")
        if self.watch_for not in VALID_WATCH_FOR:
            raise ValueError(
                f"event {self.name!r}: watch_for must be one of "
                f"{sorted(VALID_WATCH_FOR)}, got {self.watch_for!r}"
            )


@dataclass
class AppConfig:
    events: list[EventConfig]
    poll_interval_seconds: int = 60
    state_file: str = "state.json"
    request_timeout_seconds: int = 20


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal .env loader (no external dependency).

    Lines like KEY=value are read into os.environ without overriding values
    that are already set in the real environment. Quotes around values are
    stripped. Missing file is a no-op.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_telegram_config() -> TelegramConfig:
    """Read Telegram credentials from the environment.

    Call load_dotenv() first if you want a local .env honoured.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    missing = [
        name
        for name, val in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id))
        if not val
    ]
    if missing:
        raise ValueError(
            "Missing Telegram credentials: "
            + ", ".join(missing)
            + ". Set them in your environment or a .env file (see .env.example)."
        )
    return TelegramConfig(bot_token=token, chat_id=chat_id)


def load_config(path: str | os.PathLike) -> AppConfig:
    """Load and validate the YAML app config."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"config file not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")

    raw_events = data.get("events") or []
    if not raw_events:
        raise ValueError("config has no 'events'; add at least one event to watch")

    events = [
        EventConfig(
            name=e.get("name", ""),
            url=e.get("url", ""),
            watch_for=e.get("watch_for", "on_sale"),
            keywords=e.get("keywords", {}) or {},
        )
        for e in raw_events
    ]

    return AppConfig(
        events=events,
        poll_interval_seconds=int(data.get("poll_interval_seconds", 60)),
        state_file=str(data.get("state_file", "state.json")),
        request_timeout_seconds=int(data.get("request_timeout_seconds", 20)),
    )
