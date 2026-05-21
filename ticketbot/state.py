"""Persist which events have already been alerted, so we notify only once."""

from __future__ import annotations

import json
from pathlib import Path


class AlertState:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._alerted: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._alerted = {str(k): str(v) for k, v in data.get("alerted", {}).items()}
        except (ValueError, OSError):
            # A corrupt/unreadable state file shouldn't stop monitoring; start fresh.
            self._alerted = {}

    @staticmethod
    def key(url: str, watch_for: str) -> str:
        return f"{watch_for}:{url}"

    def already_alerted(self, url: str, watch_for: str) -> bool:
        return self.key(url, watch_for) in self._alerted

    def mark_alerted(self, url: str, watch_for: str, when_iso: str) -> None:
        self._alerted[self.key(url, watch_for)] = when_iso
        self._save()

    def _save(self) -> None:
        self._path.write_text(
            json.dumps({"alerted": self._alerted}, indent=2), encoding="utf-8"
        )
