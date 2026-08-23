from stock_fall_detector.cli import (
    format_context_report,
    format_summary_table,
    format_technicals_report,
    resolve_tickers,
)
from stock_fall_detector.context import AnalystAction, AnalystSummary, NewsHeadline, SocialSentiment, StockContext
from stock_fall_detector.detector import FallResult
from stock_fall_detector.qqq_components import QQQ_COMPONENTS
from stock_fall_detector.technicals import BollingerPosition, Technicals


def test_resolve_tickers_returns_explicit_list_when_given():
    assert resolve_tickers(["AAPL", "MSFT"]) == ["AAPL", "MSFT"]


def test_resolve_tickers_defaults_to_qqq_components_when_empty():
    assert resolve_tickers([]) == QQQ_COMPONENTS


def test_format_summary_table_title_shows_comparison_window():
    results = [
        FallResult(
            ticker="A", start_price=100.0, end_price=88.0, pct_change=-12.0, market_cap_before=20e9,
            start_date="2026-08-14", end_date="2026-08-21",
        ),
        FallResult(
            ticker="B", start_price=50.0, end_price=44.0, pct_change=-12.0, market_cap_before=15e9,
            start_date="2026-08-15", end_date="2026-08-22",
        ),
    ]
    table = format_summary_table(results)
    assert "2026-08-14 to 2026-08-22" in table
    assert "Current" in table


def test_format_summary_table_falls_back_without_dates():
    results = [
        FallResult(ticker="A", start_price=100.0, end_price=88.0, pct_change=-12.0, market_cap_before=20e9),
    ]
    table = format_summary_table(results)
    assert "Fall report" in table


def test_format_summary_table_includes_all_results():
    results = [
        FallResult(ticker="A", start_price=100.0, end_price=88.0, pct_change=-12.0, market_cap_before=20e9),
        FallResult(ticker="B", start_price=50.0, end_price=44.0, pct_change=-12.0, market_cap_before=15e9),
    ]
    table = format_summary_table(results)
    assert "A" in table
    assert "B" in table
    assert "-12.00" in table


def test_format_summary_table_includes_technicals_columns_when_provided():
    results = [
        FallResult(
            ticker="INTC", start_price=102.50, end_price=90.07, pct_change=-12.13,
            market_cap_before=541.83e9, start_date="2026-08-14", end_date="2026-08-21",
        ),
    ]
    technicals_by_ticker = {
        "INTC": Technicals(
            ticker="INTC",
            current_price=90.07,
            rsi_14=39.6,
            implied_volatility_pct=61.0,
            bollinger=BollingerPosition(
                sma=95.70, upper_band=107.95, lower_band=83.45, percent_b=0.27, zone="lower half"
            ),
            fifty_two_week_high=142.35,
            fifty_two_week_low=23.68,
            all_time_high=142.35,
        )
    }
    table = format_summary_table(results, technicals_by_ticker)
    assert "RSI" in table
    assert "IV%" in table
    assert "BB %B" in table
    assert "vs52wkHi%" in table
    assert "vsATH%" in table
    assert "39.6" in table
    assert "61.0" in table
    assert "0.27" in table
    assert "-36.7" in table  # 90.07 vs 142.35 both 52wk high and ATH


def test_format_summary_table_technicals_row_handles_unavailable_data():
    results = [
        FallResult(ticker="ZZZZ", start_price=50.0, end_price=44.0, pct_change=-12.0, market_cap_before=15e9),
    ]
    technicals_by_ticker = {
        "ZZZZ": Technicals(
            ticker="ZZZZ",
            current_price=None,
            rsi_14=None,
            implied_volatility_pct=None,
            bollinger=None,
            fifty_two_week_high=None,
            fifty_two_week_low=None,
            all_time_high=None,
        )
    }
    table = format_summary_table(results, technicals_by_ticker)
    assert "n/a" in table


def test_format_context_report_with_full_data():
    context = StockContext(
        ticker="INTC",
        headlines=[
            NewsHeadline(
                title="Intel sold $20B of stock",
                publisher="Motley Fool",
                link="https://example.com/a",
                published_at="2026-08-21",
            )
        ],
        analyst=AnalystSummary(
            recommendation="hold",
            mean_target_price=114.88,
            num_analysts=41,
            upside_pct=27.5,
            recent_actions=[
                AnalystAction(
                    firm="B of A Securities",
                    action="main",
                    from_grade="Buy",
                    to_grade="Buy",
                    price_target=145.0,
                    date="2026-08-19",
                )
            ],
        ),
        social=SocialSentiment(bullish_pct=62.0, bearish_pct=38.0, sample_size=18),
    )
    report = format_context_report(context)
    assert "Intel sold $20B of stock" in report
    assert "HOLD" in report
    assert "114.88" in report
    assert "B of A Securities" in report
    assert "62% bullish" in report


def test_format_context_report_handles_missing_data():
    context = StockContext(ticker="ZZZZ", headlines=[], analyst=None, social=None)
    report = format_context_report(context)
    assert "no recent ticker-tagged headlines found" in report
    assert "analyst data unavailable" in report
    assert "social sentiment unavailable" in report


def test_format_technicals_report_with_full_data():
    t = Technicals(
        ticker="INTC",
        current_price=90.07,
        rsi_14=28.4,
        implied_volatility_pct=62.1,
        bollinger=BollingerPosition(
            sma=98.32, upper_band=111.54, lower_band=85.10, percent_b=0.19, zone="lower half"
        ),
        fifty_two_week_high=142.35,
        fifty_two_week_low=23.68,
        all_time_high=142.35,
    )
    report = format_technicals_report(t)
    assert "RSI(14): 28.4 (oversold)" in report
    assert "62.1%" in report
    assert "lower half" in report
    assert "23.68 - $142.35" in report
    assert "-36.7%" in report  # 90.07 vs 142.35 ATH


def test_format_technicals_report_handles_missing_data():
    t = Technicals(
        ticker="ZZZZ",
        current_price=None,
        rsi_14=None,
        implied_volatility_pct=None,
        bollinger=None,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
        all_time_high=None,
    )
    report = format_technicals_report(t)
    assert "RSI(14): unavailable" in report
    assert "Implied volatility: unavailable" in report
    assert "Bollinger Bands: unavailable" in report
    assert "52-week range: unavailable" in report
    assert "All-time high: unavailable" in report
