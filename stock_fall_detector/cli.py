"""Command-line interface for the stock fall detector."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from .detector import find_falling_stocks
from .yfinance_source import YFinancePriceDataSource


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find large-cap stocks that fell sharply over a recent window. "
            "A stock qualifies if its market cap at the start of the window "
            "exceeded --min-market-cap and it then dropped at least --fall-pct."
        )
    )
    parser.add_argument("tickers", nargs="+", help="Stock ticker symbols, e.g. AAPL MSFT TSLA")
    parser.add_argument(
        "--days", type=int, default=7, dest="days",
        help="Lookback window in calendar days (default: 7, i.e. one week)",
    )
    parser.add_argument(
        "--fall-pct", type=float, default=10.0, dest="fall_pct",
        help="Minimum percentage fall to flag a stock (default: 10)",
    )
    parser.add_argument(
        "--min-market-cap", type=float, default=10_000_000_000, dest="min_market_cap",
        help="Minimum market cap in USD at the start of the window (default: 10000000000, i.e. $10B)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    source = YFinancePriceDataSource()
    results = find_falling_stocks(
        tickers=args.tickers,
        data_source=source,
        lookback_days=args.days,
        fall_threshold_pct=args.fall_pct,
        min_market_cap=args.min_market_cap,
    )

    if not results:
        print("No qualifying stocks found.")
        return

    print(f"{'Ticker':<8}{'Start':>12}{'End':>12}{'Change %':>12}{'Mkt Cap ($B)':>16}")
    for r in results:
        print(
            f"{r.ticker:<8}{r.start_price:>12.2f}{r.end_price:>12.2f}"
            f"{r.pct_change:>12.2f}{r.market_cap_before / 1e9:>16.2f}"
        )


if __name__ == "__main__":
    main()
