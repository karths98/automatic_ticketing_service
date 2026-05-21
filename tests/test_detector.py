import unittest
from datetime import datetime, timezone
from pathlib import Path

from ticketbot.detector import (
    Status,
    detect_from_jsonld,
    detect_from_keywords,
    detect_from_sale_window,
    detect_status,
    extract_sale_window,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class JsonLdDetectionTests(unittest.TestCase):
    def test_onsale_instock(self):
        self.assertEqual(detect_from_jsonld(load("event_onsale.html")), Status.ON_SALE)

    def test_not_yet_preorder_future_validfrom(self):
        self.assertEqual(detect_from_jsonld(load("event_not_onsale.html")), Status.NOT_YET)

    def test_sold_out(self):
        self.assertEqual(detect_from_jsonld(load("event_soldout.html")), Status.SOLD_OUT)

    def test_future_validfrom_overrides_instock(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Event","offers":{"availability":"https://schema.org/InStock",
        "validFrom":"2999-01-01T00:00:00+00:00"}}
        </script>
        """
        self.assertEqual(detect_from_jsonld(html), Status.NOT_YET)

    def test_past_validfrom_instock_is_on_sale(self):
        now = datetime(2026, 5, 21, tzinfo=timezone.utc)
        html = """
        <script type="application/ld+json">
        {"@type":"Event","offers":{"availability":"https://schema.org/InStock",
        "validFrom":"2026-01-01T00:00:00+00:00"}}
        </script>
        """
        self.assertEqual(detect_from_jsonld(html, now=now), Status.ON_SALE)

    def test_offers_as_list_prefers_on_sale(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Event","offers":[
          {"availability":"https://schema.org/SoldOut"},
          {"availability":"https://schema.org/InStock"}
        ]}
        </script>
        """
        self.assertEqual(detect_from_jsonld(html), Status.ON_SALE)

    def test_no_jsonld_is_unknown(self):
        self.assertEqual(detect_from_jsonld("<html><body>hi</body></html>"), Status.UNKNOWN)

    def test_malformed_jsonld_is_ignored(self):
        html = '<script type="application/ld+json">{not valid json}</script>'
        self.assertEqual(detect_from_jsonld(html), Status.UNKNOWN)


class SaleWindowDetectionTests(unittest.TestCase):
    """Primary detection: Live Nation's embedded onsale / waiting-room timestamps."""

    def setUp(self):
        self.html = load("event_ln_waitroom.html")  # waitroom 02:00Z, onsale 03:00Z

    def test_before_waitroom_is_not_yet(self):
        now = datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(detect_from_sale_window(self.html, now), Status.NOT_YET)

    def test_during_waitroom_is_on_sale_actionable(self):
        # Waiting room is open (02:00) but tickets not technically on sale (03:00).
        # The actionable "go" moment is the waiting room, so this is ON_SALE.
        now = datetime(2026, 5, 21, 2, 30, tzinfo=timezone.utc)
        self.assertEqual(detect_from_sale_window(self.html, now), Status.ON_SALE)

    def test_after_onsale_is_on_sale(self):
        now = datetime(2026, 5, 21, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(detect_from_sale_window(self.html, now), Status.ON_SALE)

    def test_extract_window_values(self):
        w = extract_sale_window(self.html)
        self.assertEqual(w.waitroom, datetime(2026, 5, 21, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(w.onsale, datetime(2026, 5, 21, 3, 0, tzinfo=timezone.utc))
        self.assertEqual(w.go_time, w.waitroom)

    def test_describe_waiting_room_message(self):
        w = extract_sale_window(self.html)
        msg = w.describe(datetime(2026, 5, 21, 2, 30, tzinfo=timezone.utc))
        self.assertIn("Waiting room is OPEN", msg)
        self.assertIn("2026-05-21 03:00 UTC", msg)

    def test_onsale_only_no_waitroom(self):
        html = 'x validFromUtc\\":\\"2026-04-02T03:00:00Z\\" y'
        before = datetime(2026, 4, 1, tzinfo=timezone.utc)
        after = datetime(2026, 4, 3, tzinfo=timezone.utc)
        self.assertEqual(detect_from_sale_window(html, before), Status.NOT_YET)
        self.assertEqual(detect_from_sale_window(html, after), Status.ON_SALE)

    def test_no_window_is_unknown(self):
        self.assertEqual(detect_from_sale_window("<html></html>"), Status.UNKNOWN)
        self.assertIsNone(extract_sale_window("<html></html>"))

    def test_sale_window_takes_priority_in_detect_status(self):
        now = datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc)  # before waitroom
        # Page also literally contains "Join waiting room" text, but the
        # timestamp signal must win and report NOT_YET.
        self.assertEqual(detect_status(self.html, now=now), Status.NOT_YET)


class KeywordDetectionTests(unittest.TestCase):
    def test_buy_now_is_on_sale(self):
        self.assertEqual(detect_from_keywords("<a>Buy Now</a>"), Status.ON_SALE)

    def test_sold_out_wins_over_on_sale_phrase(self):
        # "on sale" substring is present but sold out should take precedence.
        html = "<p>This show is Sold Out. Was on sale now.</p>"
        self.assertEqual(detect_from_keywords(html), Status.SOLD_OUT)

    def test_custom_keywords(self):
        html = "<p>Tiket dijual sekarang</p>"
        kw = {"on_sale": ["dijual sekarang"]}
        self.assertEqual(detect_from_keywords(html, kw), Status.ON_SALE)

    def test_script_contents_ignored(self):
        html = '<script>var x = "buy now";</script><body>nothing here</body>'
        self.assertEqual(detect_from_keywords(html), Status.UNKNOWN)


class DetectStatusFallbackTests(unittest.TestCase):
    def test_falls_back_to_keywords_when_no_jsonld(self):
        html = "<html><body><button>Find Tickets</button></body></html>"
        self.assertEqual(detect_status(html), Status.ON_SALE)

    def test_jsonld_takes_priority(self):
        self.assertEqual(detect_status(load("event_onsale.html")), Status.ON_SALE)


if __name__ == "__main__":
    unittest.main()
