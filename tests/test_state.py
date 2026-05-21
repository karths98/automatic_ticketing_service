import tempfile
import unittest
from pathlib import Path

from ticketbot.state import AlertState


class AlertStateTests(unittest.TestCase):
    def test_mark_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            state = AlertState(Path(d) / "state.json")
            url = "https://x.test/e"
            self.assertFalse(state.already_alerted(url, "on_sale"))
            state.mark_alerted(url, "on_sale", "2026-05-21T00:00:00+00:00")
            self.assertTrue(state.already_alerted(url, "on_sale"))
            # Different watch_for is a distinct key.
            self.assertFalse(state.already_alerted(url, "sold_out"))

    def test_persists_across_instances(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            AlertState(path).mark_alerted("u", "on_sale", "t")
            self.assertTrue(AlertState(path).already_alerted("u", "on_sale"))

    def test_corrupt_file_starts_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text("not json{")
            state = AlertState(path)
            self.assertFalse(state.already_alerted("u", "on_sale"))


if __name__ == "__main__":
    unittest.main()
