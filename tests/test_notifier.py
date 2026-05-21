import unittest
from unittest.mock import MagicMock, patch

from ticketbot.config import TelegramConfig
from ticketbot.notifier import NotifyError, TelegramNotifier


def make_notifier() -> TelegramNotifier:
    return TelegramNotifier(TelegramConfig(bot_token="TOKEN", chat_id="42"))


class TelegramNotifierTests(unittest.TestCase):
    @patch("ticketbot.notifier.requests.post")
    def test_send_posts_to_correct_url_and_payload(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        make_notifier().send("hello")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.telegram.org/botTOKEN/sendMessage")
        self.assertEqual(kwargs["json"]["chat_id"], "42")
        self.assertEqual(kwargs["json"]["text"], "hello")
        self.assertEqual(kwargs["json"]["parse_mode"], "HTML")

    @patch("ticketbot.notifier.requests.post")
    def test_non_200_raises(self, mock_post):
        resp = MagicMock(status_code=401)
        resp.json.return_value = {"description": "Unauthorized"}
        mock_post.return_value = resp
        with self.assertRaises(NotifyError) as ctx:
            make_notifier().send("hi")
        self.assertIn("Unauthorized", str(ctx.exception))

    @patch("ticketbot.notifier.requests.post")
    def test_notify_status_includes_link_and_escapes(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        make_notifier().notify_status(
            "A & B <Live>", "https://x.test/e?id=1&y=2", "On sale now"
        )
        text = mock_post.call_args.kwargs["json"]["text"]
        self.assertIn("A &amp; B &lt;Live&gt;", text)
        self.assertIn("https://x.test/e?id=1&amp;y=2", text)
        self.assertIn("On sale now", text)

    @patch("ticketbot.notifier.requests.post")
    def test_network_error_becomes_notify_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError("boom")
        with self.assertRaises(NotifyError):
            make_notifier().send("hi")


if __name__ == "__main__":
    unittest.main()
