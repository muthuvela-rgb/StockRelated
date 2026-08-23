"""Command-line interface for the stock fall detector."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from .context import ContextSource, StockContext
from .detector import FallResult, find_falling_stocks
from .qqq_components import QQQ_COMPONENTS
from .technicals import Technicals, TechnicalsSource
from .yahoo_context_source import YahooStockTwitsContextSource
from .yahoo_source import YahooHttpPriceDataSource
from .yahoo_technicals_source import YahooTechnicalsSource


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find large-cap stocks that fell sharply over a recent window. "
            "A stock qualifies if its market cap at the start of the window "
            "exceeded --min-market-cap and it then dropped at least --fall-pct. "
            "If no tickers are given, defaults to QQQ's holdings (Nasdaq-100)."
        )
    )
    parser.add_argument(
        "tickers", nargs="*",
        help="Stock ticker symbols, e.g. AAPL MSFT TSLA (default: QQQ's holdings)",
    )
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
    parser.add_argument(
        "--no-technicals", action="store_true", dest="no_technicals",
        help="Skip fetching RSI/volatility/Bollinger/high-low data for qualifying stocks (faster)",
    )
    return parser.parse_args(argv)


def resolve_tickers(tickers: Sequence[str]) -> list[str]:
    return list(tickers) if tickers else list(QQQ_COMPONENTS)


def format_summary_table(
    results: list[FallResult], technicals_by_ticker: Optional[dict[str, Technicals]] = None
) -> str:
    start_dates = [r.start_date for r in results if r.start_date]
    end_dates = [r.end_date for r in results if r.end_date]
    if start_dates and end_dates:
        title = f"Fall report: {min(start_dates)} to {max(end_dates)} (Current = last close)"
    else:
        title = "Fall report"

    if not technicals_by_ticker:
        lines = [title, f"{'Ticker':<8}{'Start':>12}{'Current':>12}{'Change %':>12}{'Mkt Cap ($B)':>16}"]
        for r in results:
            lines.append(
                f"{r.ticker:<8}{r.start_price:>12.2f}{r.end_price:>12.2f}"
                f"{r.pct_change:>12.2f}{r.market_cap_before / 1e9:>16.2f}"
            )
        return "\n".join(lines)

    header = (
        f"{'Ticker':<7}{'Start':>9}{'Current':>9}{'Chg %':>8}{'MktCap($B)':>12}"
        f"{'RSI':>7}{'IV%':>7}{'BB %B':>8}{'vs52wkHi%':>11}{'vsATH%':>9}"
    )
    lines = [title, header]
    for r in results:
        t = technicals_by_ticker.get(r.ticker)
        rsi = f"{t.rsi_14:.1f}" if t and t.rsi_14 is not None else "n/a"
        iv = f"{t.implied_volatility_pct:.1f}" if t and t.implied_volatility_pct is not None else "n/a"
        bb = f"{t.bollinger.percent_b:.2f}" if t and t.bollinger is not None else "n/a"
        vs_52wk_high = (
            f"{(r.end_price - t.fifty_two_week_high) / t.fifty_two_week_high * 100:+.1f}"
            if t and t.fifty_two_week_high
            else "n/a"
        )
        vs_ath = (
            f"{(r.end_price - t.all_time_high) / t.all_time_high * 100:+.1f}"
            if t and t.all_time_high
            else "n/a"
        )
        lines.append(
            f"{r.ticker:<7}{r.start_price:>9.2f}{r.end_price:>9.2f}{r.pct_change:>8.2f}"
            f"{r.market_cap_before / 1e9:>12.2f}{rsi:>7}{iv:>7}{bb:>8}{vs_52wk_high:>11}{vs_ath:>9}"
        )
    return "\n".join(lines)


def format_context_report(context: StockContext) -> str:
    lines = ["  Recent headlines (why it may have fallen):"]
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


def format_technicals_report(t: Technicals) -> str:
    lines = ["  Technicals:"]

    if t.rsi_14 is not None:
        if t.rsi_14 < 30:
            label = "oversold"
        elif t.rsi_14 > 70:
            label = "overbought"
        else:
            label = "neutral"
        lines.append(f"    RSI(14): {t.rsi_14:.1f} ({label})")
    else:
        lines.append("    RSI(14): unavailable")

    if t.implied_volatility_pct is not None:
        lines.append(f"    Implied volatility (~30d ATM): {t.implied_volatility_pct:.1f}%")
    else:
        lines.append("    Implied volatility: unavailable")

    b = t.bollinger
    if b is not None:
        lines.append(
            f"    Bollinger Bands(20,2): SMA ${b.sma:.2f}, "
            f"bands [${b.lower_band:.2f}, ${b.upper_band:.2f}] — {b.zone} (%B {b.percent_b:.2f})"
        )
    else:
        lines.append("    Bollinger Bands: unavailable")

    if t.fifty_two_week_high is not None and t.fifty_two_week_low is not None:
        lines.append(f"    52-week range: ${t.fifty_two_week_low:.2f} - ${t.fifty_two_week_high:.2f}")
    else:
        lines.append("    52-week range: unavailable")

    if t.all_time_high is not None:
        off_ath = ""
        if t.current_price:
            off_ath = f" (current price is {(t.current_price - t.all_time_high) / t.all_time_high * 100:+.1f}% vs ATH)"
        lines.append(f"    All-time high: ${t.all_time_high:.2f}{off_ath}")
    else:
        lines.append("    All-time high: unavailable")

    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    tickers = resolve_tickers(args.tickers)
    source = YahooHttpPriceDataSource()
    results = find_falling_stocks(
        tickers=tickers,
        data_source=source,
        lookback_days=args.days,
        fall_threshold_pct=args.fall_pct,
        min_market_cap=args.min_market_cap,
    )

    if not results:
        print("No qualifying stocks found.")
        return

    technicals_by_ticker: dict[str, Technicals] = {}
    if not args.no_technicals:
        technicals_source: TechnicalsSource = YahooTechnicalsSource()
        for r in results:
            technicals_by_ticker[r.ticker] = technicals_source.get_technicals(r.ticker)

    print(format_summary_table(results, technicals_by_ticker))

    if args.no_context and args.no_technicals:
        return

    context_source: ContextSource = YahooStockTwitsContextSource()
    for r in results:
        print(f"\n{r.ticker}:")
        if not args.no_context:
            context = context_source.get_context(r.ticker, current_price=r.end_price)
            print(format_context_report(context))
        if r.ticker in technicals_by_ticker:
            print(format_technicals_report(technicals_by_ticker[r.ticker]))


if __name__ == "__main__":
    main()
