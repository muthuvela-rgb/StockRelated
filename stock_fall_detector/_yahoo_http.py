"""Shared plain-requests session for talking to Yahoo Finance.

Yahoo's quoteSummary API requires a session cookie plus a "crumb" token
tied to it. This is shared by yahoo_source.py (price/shares data) and
yahoo_context_source.py (news/analyst/social context) so the cookie/crumb
dance and browser-like headers live in exactly one place.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    # Yahoo's edge treats requests missing these as bots and skips setting
    # the session cookie the crumb endpoint requires.
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class YahooSession:
    def __init__(self, timeout: float = 10.0) -> None:
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self.timeout = timeout
        self._crumb: Optional[str] = None

    def crumb(self) -> Optional[str]:
        if self._crumb is None:
            self.session.get("https://finance.yahoo.com", timeout=self.timeout)
            resp = self.session.get(
                "https://query1.finance.yahoo.com/v1/test/getcrumb",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            self._crumb = resp.text.strip()
        return self._crumb

    def get_json(self, url: str, params: Optional[dict] = None) -> Optional[Any]:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def get_text(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        return resp.text
