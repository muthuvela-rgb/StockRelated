"""Core logic for detecting large-cap stocks that fell sharply over a lookback window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class StockPriceData:
    """Raw price/market data for a single ticker over a lookback window."""

    ticker: str
    start_price: float
    end_price: float
    shares_outstanding: float
    start_date: str = ""  # YYYY-MM-DD, empty if unknown
    end_date: str = ""  # YYYY-MM-DD; end_price is the close on this date


@dataclass(frozen=True)
class FallResult:
    ticker: str
    start_price: float
    end_price: float
    pct_change: float
    market_cap_before: float
    start_date: str = ""
    end_date: str = ""


class PriceDataSource(Protocol):
    def get_price_data(self, ticker: str, lookback_days: int) -> Optional[StockPriceData]:
        ...


def find_falling_stocks(
    tickers: Sequence[str],
    data_source: PriceDataSource,
    lookback_days: int = 7,
    fall_threshold_pct: float = 10.0,
    min_market_cap: float = 10_000_000_000,
) -> list[FallResult]:
    """Return tickers whose price dropped by at least fall_threshold_pct over
    lookback_days, restricted to stocks whose market cap at the start of the
    window exceeded min_market_cap.
    """
    results: list[FallResult] = []
    for ticker in tickers:
        data = data_source.get_price_data(ticker, lookback_days)
        if data is None or data.start_price <= 0 or data.shares_outstanding <= 0:
            continue

        market_cap_before = data.start_price * data.shares_outstanding
        if market_cap_before <= min_market_cap:
            continue

        pct_change = (data.end_price - data.start_price) / data.start_price * 100
        if pct_change <= -fall_threshold_pct:
            results.append(
                FallResult(
                    ticker=data.ticker,
                    start_price=data.start_price,
                    end_price=data.end_price,
                    pct_change=pct_change,
                    market_cap_before=market_cap_before,
                    start_date=data.start_date,
                    end_date=data.end_date,
                )
            )

    results.sort(key=lambda r: r.pct_change)
    return results
