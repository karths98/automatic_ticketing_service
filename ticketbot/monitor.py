"""The polling loop: fetch -> detect -> notify once -> persist."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

from .config import AppConfig, EventConfig
from .detector import Status, detect_status, extract_sale_window
from .fetcher import FetchError, fetch
from .notifier import NotifyError, TelegramNotifier
from .state import AlertState

log = logging.getLogger("ticketbot")

STATUS_LABEL = {
    Status.ON_SALE: "On sale now",
    Status.NOT_YET: "Not on sale yet",
    Status.SOLD_OUT: "Sold out",
    Status.UNKNOWN: "Unknown",
}


class Monitor:
    def __init__(
        self,
        config: AppConfig,
        notifier: TelegramNotifier,
        state: AlertState | None = None,
    ) -> None:
        self._config = config
        self._notifier = notifier
        self._state = state or AlertState(config.state_file)

    def check_event(self, event: EventConfig) -> Status:
        """Check a single event once; alert if its target status is reached."""
        if self._state.already_alerted(event.url, event.watch_for):
            log.info("[%s] already alerted for '%s'; skipping", event.name, event.watch_for)
            return Status.UNKNOWN

        now = datetime.now(timezone.utc)
        html = fetch(event.url, timeout=self._config.request_timeout_seconds)
        status = detect_status(html, event, now=now)
        log.info("[%s] detected status: %s (watching for: %s)",
                 event.name, status.value, event.watch_for)

        if status.value == event.watch_for:
            window = extract_sale_window(html)
            label = window.describe(now) if window else STATUS_LABEL.get(status, status.value)
            self._notifier.notify_status(event.name, event.url, label)
            self._state.mark_alerted(
                event.url, event.watch_for, datetime.now(timezone.utc).isoformat()
            )
            log.info("[%s] ALERT SENT (%s)", event.name, status.value)
        return status

    def check_all(self) -> dict[str, Status]:
        """One pass over every configured event. Per-event errors are isolated."""
        results: dict[str, Status] = {}
        for event in self._config.events:
            try:
                results[event.name] = self.check_event(event)
            except FetchError as exc:
                log.warning("[%s] fetch failed: %s", event.name, exc)
                results[event.name] = Status.UNKNOWN
            except NotifyError as exc:
                log.error("[%s] alert failed to send: %s", event.name, exc)
                results[event.name] = Status.UNKNOWN
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                log.exception("[%s] unexpected error: %s", event.name, exc)
                results[event.name] = Status.UNKNOWN
        return results

    def _all_done(self) -> bool:
        return all(
            self._state.already_alerted(e.url, e.watch_for) for e in self._config.events
        )

    def run_forever(self) -> None:
        """Poll on the configured interval until every event has been alerted."""
        interval = self._config.poll_interval_seconds
        log.info(
            "Monitoring %d event(s) every ~%ds. Ctrl-C to stop.",
            len(self._config.events),
            interval,
        )
        while True:
            self.check_all()
            if self._all_done():
                log.info("All watched events have fired their alert. Done.")
                return
            # Small jitter so we don't poll on a perfectly fixed cadence.
            sleep_for = interval + random.uniform(0, max(1.0, interval * 0.1))
            time.sleep(sleep_for)
