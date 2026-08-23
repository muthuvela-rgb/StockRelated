"""PriceDataSource implementation backed by Yahoo Finance via yfinance."""

from __future__ import annotations

from typing import Optional

from .detector import StockPriceData


class YFinancePriceDataSource:
    """Fetches historical close prices and shares outstanding from Yahoo Finance.

    Requests a small buffer of extra calendar days beyond lookback_days to
    absorb weekends/holidays, then uses the earliest and latest trading days
    actually returned within the window.
    """

    def __init__(self, buffer_days: int = 5) -> None:
        self._buffer_days = buffer_days

    def get_price_data(self, ticker: str, lookback_days: int) -> Optional[StockPriceData]:
        import yfinance as yf

        yf_ticker = yf.Ticker(ticker)
        history = yf_ticker.history(period=f"{lookback_days + self._buffer_days}d")
        if history.empty:
            return None

        window = history.tail(lookback_days + 1)
        if len(window) < 2:
            return None

        start_price = float(window["Close"].iloc[0])
        end_price = float(window["Close"].iloc[-1])

        shares_outstanding = yf_ticker.info.get("sharesOutstanding")
        if not shares_outstanding:
            return None

        return StockPriceData(
            ticker=ticker,
            start_price=start_price,
            end_price=end_price,
            shares_outstanding=float(shares_outstanding),
        )
