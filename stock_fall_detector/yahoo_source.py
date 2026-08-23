"""PriceDataSource implementation that talks to Yahoo Finance directly over
plain HTTP (via `requests`), rather than through the yfinance package.

yfinance's default HTTP backend (curl_cffi) impersonates a specific browser
TLS fingerprint, which some TLS-terminating proxies reset. This module hits
the same public Yahoo endpoints yfinance uses, but with a plain requests
session, which works through standard HTTP(S) proxies.
"""

from __future__ import annotations

import datetime
from typing import Optional

from ._yahoo_http import YahooSession
from .detector import StockPriceData


class YahooHttpPriceDataSource:
    def __init__(self, timeout: float = 10.0) -> None:
        self._yahoo = YahooSession(timeout=timeout)

    def get_price_data(self, ticker: str, lookback_days: int) -> Optional[StockPriceData]:
        chart = self._yahoo.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"range": "3mo", "interval": "1d"},
        )
        if chart is None:
            return None

        results = chart.get("chart", {}).get("result")
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
        start_date = datetime.datetime.utcfromtimestamp(window[0][0]).strftime("%Y-%m-%d")
        end_date = datetime.datetime.utcfromtimestamp(window[-1][0]).strftime("%Y-%m-%d")

        crumb = self._yahoo.crumb()
        if crumb is None:
            return None

        stats = self._yahoo.get_json(
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
            params={"modules": "defaultKeyStatistics", "crumb": crumb},
        )
        if stats is None:
            return None

        stats_results = stats.get("quoteSummary", {}).get("result")
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
            start_date=start_date,
            end_date=end_date,
        )
