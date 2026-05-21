"""Decide an event's sale status from its page HTML.

Detection strategy, most-to-least reliable (verified against live livenation.my
event pages):

1. **Sale-window timestamps** (primary). Live Nation's Next.js pages embed the
   event's ``waitroomOpenUtc`` (when the queue/waiting room opens) and
   ``validFromUtc`` (when tickets actually go on sale) in the page payload.
   Comparing these to the current time is the ground-truth signal. The "go"
   moment for the user is when the waiting room opens, because you must be in
   the queue *before* onsale -- so that's what flips an event to ON_SALE.
2. **schema.org JSON-LD** (fallback). Some Live Nation properties expose an
   ``Event`` object with ``offers.availability`` / ``validFrom``.
3. **Keyword scan** (last resort). A configurable visible-text scan, for pages
   that carry neither of the above.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .config import EventConfig


class Status(str, Enum):
    ON_SALE = "on_sale"
    NOT_YET = "not_yet"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# 1. Sale-window detection (primary)
# ---------------------------------------------------------------------------

_ISO_TS = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?)"


def _field_times(html: str, field: str) -> list[datetime]:
    """Extract every ISO timestamp associated with ``field`` in the payload.

    The Next.js RSC payload embeds these as escaped JSON, e.g.
    ``validFromUtc\\":\\"2026-05-21T03:00:00Z\\"`` so we allow quotes/colons/
    backslashes/whitespace between the key and the value.
    """
    pattern = re.compile(re.escape(field) + r"""[\\"':\s]{1,6}""" + _ISO_TS)
    out = []
    for raw in pattern.findall(html):
        dt = _parse_iso(raw)
        if dt:
            out.append(dt)
    return out


@dataclass
class SaleWindow:
    onsale: datetime | None = None  # validFromUtc -- tickets purchasable
    waitroom: datetime | None = None  # waitroomOpenUtc -- queue opens

    @property
    def go_time(self) -> datetime | None:
        """The earliest moment the user should act (queue opens, else onsale)."""
        times = [t for t in (self.waitroom, self.onsale) if t]
        return min(times) if times else None

    def status(self, now: datetime) -> Status:
        gt = self.go_time
        if gt is None:
            return Status.UNKNOWN
        return Status.ON_SALE if now >= gt else Status.NOT_YET

    def describe(self, now: datetime) -> str:
        if self.waitroom and self.onsale and self.waitroom <= now < self.onsale:
            return (
                "Waiting room is OPEN — join the queue now. "
                f"Tickets on sale {_fmt(self.onsale)}."
            )
        if self.onsale and now >= self.onsale:
            return "On sale now."
        if self.waitroom and now >= self.waitroom:
            return "Waiting room is open now."
        gt = self.go_time
        return f"Opens {_fmt(gt)}." if gt else ""


def extract_sale_window(html: str) -> SaleWindow | None:
    """Pull the earliest onsale/waiting-room times from the page, if present."""
    onsale = _field_times(html, "validFromUtc")
    waitroom = _field_times(html, "waitroomOpenUtc")
    if not onsale and not waitroom:
        return None
    return SaleWindow(
        onsale=min(onsale) if onsale else None,
        waitroom=min(waitroom) if waitroom else None,
    )


def detect_from_sale_window(html: str, now: datetime | None = None) -> Status:
    window = extract_sale_window(html)
    if window is None:
        return Status.UNKNOWN
    return window.status(now or datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 2. schema.org JSON-LD detection (fallback)
# ---------------------------------------------------------------------------

# schema.org ItemAvailability value (the bit after the last slash, lowercased)
# -> our Status.
_AVAILABILITY_MAP = {
    "instock": Status.ON_SALE,
    "limitedavailability": Status.ON_SALE,
    "onlineonly": Status.ON_SALE,
    "instoreonly": Status.ON_SALE,
    "presale": Status.NOT_YET,
    "preorder": Status.NOT_YET,
    "soldout": Status.SOLD_OUT,
    "outofstock": Status.SOLD_OUT,
    "discontinued": Status.SOLD_OUT,
}

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _iter_jsonld(html: str):
    for match in _JSONLD_RE.finditer(html):
        blob = match.group(1).strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            if isinstance(data.get("@graph"), list):
                yield from data["@graph"]
            else:
                yield data


def _is_event(obj: dict) -> bool:
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and "event" in x.lower() for x in types if x)


def _status_from_offer(offer: dict, now: datetime) -> Status | None:
    if not isinstance(offer, dict):
        return None
    for key in ("validFrom", "availabilityStarts"):
        starts = _parse_iso(offer.get(key))
        if starts and starts > now:
            return Status.NOT_YET
    availability = offer.get("availability")
    if isinstance(availability, str):
        token = availability.rstrip("/").rsplit("/", 1)[-1].lower()
        mapped = _AVAILABILITY_MAP.get(token)
        if mapped:
            return mapped
    return None


def detect_from_jsonld(html: str, now: datetime | None = None) -> Status:
    now = now or datetime.now(timezone.utc)
    statuses: list[Status] = []
    for obj in _iter_jsonld(html):
        if not isinstance(obj, dict) or not _is_event(obj):
            continue
        offers = obj.get("offers")
        offer_list = offers if isinstance(offers, list) else [offers]
        for offer in offer_list:
            s = _status_from_offer(offer, now)
            if s:
                statuses.append(s)
    if not statuses:
        return Status.UNKNOWN
    if Status.ON_SALE in statuses:
        return Status.ON_SALE
    if Status.NOT_YET in statuses:
        return Status.NOT_YET
    return Status.SOLD_OUT


# ---------------------------------------------------------------------------
# 3. Keyword detection (last resort)
# ---------------------------------------------------------------------------

DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "on_sale": ["buy now", "find tickets", "on sale now", "get tickets", "buy tickets"],
    "not_yet": [
        "sale starts",
        "on sale ",
        "coming soon",
        "not yet on sale",
        "presale",
        "pre-sale",
        "register for",
        "tickets available from",
    ],
    "sold_out": ["sold out", "no tickets available", "currently unavailable"],
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _visible_text(html: str) -> str:
    cleaned = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL
    )
    text = _TAG_RE.sub(" ", cleaned)
    return _WS_RE.sub(" ", text).lower()


def detect_from_keywords(html: str, keywords: dict[str, list[str]] | None = None) -> Status:
    kw = {**DEFAULT_KEYWORDS, **(keywords or {})}
    text = _visible_text(html)
    for status in (Status.SOLD_OUT, Status.NOT_YET, Status.ON_SALE):
        for phrase in kw.get(status.value, []):
            if phrase.lower() in text:
                return status
    return Status.UNKNOWN


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def detect_status(
    html: str, event: EventConfig | None = None, now: datetime | None = None
) -> Status:
    """Best-effort sale status: sale-window first, then JSON-LD, then keywords."""
    now = now or datetime.now(timezone.utc)

    status = detect_from_sale_window(html, now=now)
    if status is not Status.UNKNOWN:
        return status

    status = detect_from_jsonld(html, now=now)
    if status is not Status.UNKNOWN:
        return status

    overrides = event.keywords if event else None
    return detect_from_keywords(html, overrides)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(value.strip()[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
