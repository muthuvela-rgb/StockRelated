"""PriceDataSource implementation that talks to Yahoo Finance directly over
plain HTTP (via `requests`), rather than through the yfinance package.

yfinance's default HTTP backend (curl_cffi) impersonates a specific browser
TLS fingerprint, which some TLS-terminating proxies reset. This module hits
the same public Yahoo endpoints yfinance uses, but with a plain requests
session, which works through standard HTTP(S) proxies.
"""

from __future__ import annotations

from typing import Optional

import requests

from .detector import StockPriceData

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


class YahooHttpPriceDataSource:
    def __init__(self, timeout: float = 10.0) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._timeout = timeout
        self._crumb: Optional[str] = None

    def _ensure_crumb(self) -> str:
        if self._crumb is None:
            self._session.get("https://finance.yahoo.com", timeout=self._timeout)
            resp = self._session.get(
                "https://query1.finance.yahoo.com/v1/test/getcrumb",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            self._crumb = resp.text.strip()
        return self._crumb

    def get_price_data(self, ticker: str, lookback_days: int) -> Optional[StockPriceData]:
        chart_resp = self._session.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"range": "3mo", "interval": "1d"},
            timeout=self._timeout,
        )
        if chart_resp.status_code != 200:
            return None

        results = chart_resp.json().get("chart", {}).get("result")
        if not results:
            return None

        result = results[0]
        timestamps = result.get("timestamp") or []
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
        pairs = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        if len(pairs) < 2:
            return None

        cutoff = pairs[-1][0] - lookback_days * 86400
        window = [p for p in pairs if p[0] >= cutoff]
        if len(window) < 2:
            window = pairs[-2:]

        start_price = float(window[0][1])
        end_price = float(window[-1][1])

        crumb = self._ensure_crumb()
        stats_resp = self._session.get(
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
            params={"modules": "defaultKeyStatistics", "crumb": crumb},
            timeout=self._timeout,
        )
        if stats_resp.status_code != 200:
            return None

        stats_results = stats_resp.json().get("quoteSummary", {}).get("result")
        if not stats_results:
            return None

        shares = (
            stats_results[0]
            .get("defaultKeyStatistics", {})
            .get("sharesOutstanding", {})
            .get("raw")
        )
        if not shares:
            return None

        return StockPriceData(
            ticker=ticker,
            start_price=start_price,
            end_price=end_price,
            shares_outstanding=float(shares),
        )
