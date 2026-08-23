"""Command-line interface for the stock fall detector."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from .context import ContextSource, StockContext
from .detector import FallResult, find_falling_stocks
from .yahoo_context_source import YahooStockTwitsContextSource
from .yahoo_source import YahooHttpPriceDataSource


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
    parser.add_argument(
        "--no-context", action="store_true", dest="no_context",
        help="Skip fetching news/analyst/social context for qualifying stocks (faster)",
    )
    return parser.parse_args(argv)


def format_summary_table(results: list[FallResult]) -> str:
    lines = [f"{'Ticker':<8}{'Start':>12}{'End':>12}{'Change %':>12}{'Mkt Cap ($B)':>16}"]
    for r in results:
        lines.append(
            f"{r.ticker:<8}{r.start_price:>12.2f}{r.end_price:>12.2f}"
            f"{r.pct_change:>12.2f}{r.market_cap_before / 1e9:>16.2f}"
        )
    return "\n".join(lines)


def format_context_report(context: StockContext) -> str:
    lines = [f"\n{context.ticker}:"]

    lines.append("  Recent headlines (why it may have fallen):")
    if context.headlines:
        for h in context.headlines:
            lines.append(f"    - [{h.published_at}] {h.title} ({h.publisher})")
            lines.append(f"      {h.link}")
    else:
        lines.append("    (no recent ticker-tagged headlines found)")

    lines.append("  Analyst view:")
    a = context.analyst
    if a is not None and (a.recommendation or a.mean_target_price):
        rec = (a.recommendation or "n/a").upper()
        n = a.num_analysts if a.num_analysts is not None else "?"
        target = f"${a.mean_target_price:.2f}" if a.mean_target_price else "n/a"
        upside = f" ({a.upside_pct:+.1f}% vs current price)" if a.upside_pct is not None else ""
        lines.append(f"    {rec} ({n} analysts) — mean target {target}{upside}")
        if a.recent_actions:
            lines.append("    Recent actions:")
            for act in a.recent_actions:
                pt = f", PT ${act.price_target:.2f}" if act.price_target else ""
                lines.append(f"      [{act.date}] {act.firm}: {act.from_grade} -> {act.to_grade}{pt}")
    else:
        lines.append("    (analyst data unavailable)")

    lines.append("  Social sentiment:")
    s = context.social
    if s is not None:
        lines.append(
            f"    {s.source}: {s.bullish_pct:.0f}% bullish / {s.bearish_pct:.0f}% bearish "
            f"(of {s.sample_size} recent sentiment-tagged posts)"
        )
    else:
        lines.append("    (social sentiment unavailable)")

    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    source = YahooHttpPriceDataSource()
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

    print(format_summary_table(results))

    if args.no_context:
        return

    context_source: ContextSource = YahooStockTwitsContextSource()
    for r in results:
        context = context_source.get_context(r.ticker, current_price=r.end_price)
        print(format_context_report(context))


if __name__ == "__main__":
    main()
