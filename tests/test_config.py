import os
import tempfile
import unittest
from pathlib import Path

from ticketbot.config import (
    load_config,
    load_dotenv,
    load_telegram_config,
)


class ConfigLoadTests(unittest.TestCase):
    def _write(self, text: str) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        tmp.write(text)
        tmp.close()
        self.addCleanup(lambda: os.unlink(tmp.name))
        return tmp.name

    def test_loads_events_and_defaults(self):
        path = self._write(
            """
            events:
              - name: Show One
                url: https://www.livenation.my/event/one
            """
        )
        cfg = load_config(path)
        self.assertEqual(len(cfg.events), 1)
        self.assertEqual(cfg.events[0].name, "Show One")
        self.assertEqual(cfg.events[0].watch_for, "on_sale")
        self.assertEqual(cfg.poll_interval_seconds, 60)

    def test_missing_events_raises(self):
        path = self._write("poll_interval_seconds: 30\n")
        with self.assertRaises(ValueError):
            load_config(path)

    def test_invalid_watch_for_raises(self):
        path = self._write(
            """
            events:
              - name: Bad
                url: https://x.test
                watch_for: whenever
            """
        )
        with self.assertRaises(ValueError):
            load_config(path)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_config("/no/such/config.yaml")


class DotenvAndSecretsTests(unittest.TestCase):
    def setUp(self):
        for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            os.environ.pop(k, None)
            self.addCleanup(lambda key=k: os.environ.pop(key, None))

    def test_dotenv_loads_without_override(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text(
                'TELEGRAM_BOT_TOKEN="abc:123"\n# comment\nTELEGRAM_CHAT_ID=999\n'
            )
            load_dotenv(env)
        self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "abc:123")
        self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "999")

    def test_load_telegram_config_ok(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "t"
        os.environ["TELEGRAM_CHAT_ID"] = "c"
        cfg = load_telegram_config()
        self.assertEqual(cfg.bot_token, "t")
        self.assertEqual(cfg.chat_id, "c")

    def test_load_telegram_config_missing_raises(self):
        with self.assertRaises(ValueError):
            load_telegram_config()


if __name__ == "__main__":
    unittest.main()
