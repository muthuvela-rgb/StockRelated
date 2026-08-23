"""TechnicalsSource implementation backed by Yahoo Finance: daily price
history for RSI/Bollinger Bands and 52-week high/low, full monthly history
for all-time high, and the options chain for implied volatility.

Each piece is fetched independently and best-effort: a failure anywhere
comes back as None on that field rather than failing the whole report.
"""

from __future__ import annotations

import time
from typing import Optional

from ._yahoo_http import YahooSession
from .technicals import Technicals, compute_bollinger, compute_rsi

_TARGET_IV_DAYS_OUT = 30


class YahooTechnicalsSource:
    def __init__(self, timeout: float = 10.0) -> None:
        self._yahoo = YahooSession(timeout=timeout)

    def get_technicals(self, ticker: str) -> Technicals:
        current_price, closes, fifty_two_week_high, fifty_two_week_low = self._get_daily_history(
            ticker
        )
        return Technicals(
            ticker=ticker,
            current_price=current_price,
            rsi_14=compute_rsi(closes) if closes else None,
            implied_volatility_pct=self._get_implied_volatility(ticker),
            bollinger=compute_bollinger(closes) if closes else None,
            fifty_two_week_high=fifty_two_week_high,
            fifty_two_week_low=fifty_two_week_low,
            all_time_high=self._get_all_time_high(ticker),
        )

    def _get_daily_history(
        self, ticker: str
    ) -> tuple[Optional[float], list[float], Optional[float], Optional[float]]:
        data = self._yahoo.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"range": "6mo", "interval": "1d"},
        )
        if not data:
            return None, [], None, None

        results = data.get("chart", {}).get("result")
        if not results:
            return None, [], None, None

        result = results[0]
        closes = [
            c for c in result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if c is not None
        ]
        meta = result.get("meta", {})
        current_price = meta.get("regularMarketPrice")
        fifty_two_week_high = meta.get("fiftyTwoWeekHigh")
        fifty_two_week_low = meta.get("fiftyTwoWeekLow")
        return current_price, closes, fifty_two_week_high, fifty_two_week_low

    def _get_all_time_high(self, ticker: str) -> Optional[float]:
        data = self._yahoo.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"period1": 0, "period2": int(time.time()), "interval": "1mo"},
        )
        if not data:
            return None

        results = data.get("chart", {}).get("result")
        if not results:
            return None

        highs = [
            h for h in results[0].get("indicators", {}).get("quote", [{}])[0].get("high", [])
            if h is not None
        ]
        return max(highs) if highs else None

    def _get_implied_volatility(self, ticker: str) -> Optional[float]:
        crumb = self._yahoo.crumb()
        if crumb is None:
            return None

        base = self._yahoo.get_json(
            f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}",
            params={"crumb": crumb},
        )
        if not base:
            return None

        base_results = base.get("optionChain", {}).get("result")
        if not base_results:
            return None

        expiration_dates = base_results[0].get("expirationDates", [])
        if not expiration_dates:
            return None

        target = time.time() + _TARGET_IV_DAYS_OUT * 86400
        chosen_expiry = min(expiration_dates, key=lambda e: abs(e - target))

        data = self._yahoo.get_json(
            f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}",
            params={"crumb": crumb, "date": chosen_expiry},
        )
        if not data:
            return None

        results = data.get("optionChain", {}).get("result")
        if not results:
            return None

        result = results[0]
        price = result.get("quote", {}).get("regularMarketPrice")
        options = result.get("options")
        if price is None or not options:
            return None

        calls = options[0].get("calls", [])
        puts = options[0].get("puts", [])
        if not calls or not puts:
            return None

        atm_call = min(calls, key=lambda c: abs(c["strike"] - price))
        atm_put = min(puts, key=lambda c: abs(c["strike"] - price))
        call_iv = atm_call.get("impliedVolatility")
        put_iv = atm_put.get("impliedVolatility")
        if call_iv is None or put_iv is None:
            return None

        return (call_iv + put_iv) / 2 * 100
