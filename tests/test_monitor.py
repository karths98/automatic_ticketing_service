import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ticketbot.config import AppConfig, EventConfig
from ticketbot.detector import Status
from ticketbot.monitor import Monitor
from ticketbot.state import AlertState

FIXTURES = Path(__file__).parent / "fixtures"


class FakeNotifier:
    def __init__(self):
        self.calls = []

    def notify_status(self, name, url, label):
        self.calls.append((name, url, label))


def app_config(state_path: Path, watch_for="on_sale") -> AppConfig:
    return AppConfig(
        events=[
            EventConfig(name="Show", url="https://x.test/e", watch_for=watch_for)
        ],
        poll_interval_seconds=1,
        state_file=str(state_path),
    )


class MonitorTests(unittest.TestCase):
    def test_alerts_once_when_target_reached(self):
        onsale_html = (FIXTURES / "event_onsale.html").read_text()
        with tempfile.TemporaryDirectory() as d:
            state_path = Path(d) / "state.json"
            cfg = app_config(state_path)
            notifier = FakeNotifier()
            monitor = Monitor(cfg, notifier, AlertState(state_path))

            with patch("ticketbot.monitor.fetch", return_value=onsale_html):
                first = monitor.check_all()
                second = monitor.check_all()  # should be deduped

            self.assertEqual(first["Show"], Status.ON_SALE)
            self.assertEqual(len(notifier.calls), 1)
            self.assertEqual(notifier.calls[0][1], "https://x.test/e")

    def test_no_alert_when_not_target(self):
        not_yet_html = (FIXTURES / "event_not_onsale.html").read_text()
        with tempfile.TemporaryDirectory() as d:
            cfg = app_config(Path(d) / "state.json")
            notifier = FakeNotifier()
            monitor = Monitor(cfg, notifier, AlertState(Path(d) / "state.json"))
            with patch("ticketbot.monitor.fetch", return_value=not_yet_html):
                monitor.check_all()
            self.assertEqual(notifier.calls, [])

    def test_fetch_error_is_isolated(self):
        from ticketbot.fetcher import FetchError

        with tempfile.TemporaryDirectory() as d:
            cfg = app_config(Path(d) / "state.json")
            notifier = FakeNotifier()
            monitor = Monitor(cfg, notifier, AlertState(Path(d) / "state.json"))
            with patch("ticketbot.monitor.fetch", side_effect=FetchError("nope")):
                results = monitor.check_all()
            self.assertEqual(results["Show"], Status.UNKNOWN)
            self.assertEqual(notifier.calls, [])


if __name__ == "__main__":
    unittest.main()
