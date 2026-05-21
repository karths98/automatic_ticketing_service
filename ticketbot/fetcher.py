"""Fetch event page HTML with a plain, polite HTTP GET."""

from __future__ import annotations

import requests

from . import __version__

# A descriptive, honest User-Agent. We are not trying to look like a real
# browser to evade detection -- we identify as a monitor and poll politely.
USER_AGENT = (
    f"livenation-onsale-monitor/{__version__} "
    "(personal onsale alerter; polls infrequently)"
)


class FetchError(RuntimeError):
    """Raised when a page could not be fetched."""


def fetch(url: str, timeout: int = 20) -> str:
    """Return the page HTML for ``url`` or raise FetchError."""
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-MY,en;q=0.9",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"failed to fetch {url}: {exc}") from exc
    return resp.text
