from stock_fall_detector.cli import format_context_report, format_summary_table, resolve_tickers
from stock_fall_detector.context import AnalystAction, AnalystSummary, NewsHeadline, SocialSentiment, StockContext
from stock_fall_detector.detector import FallResult
from stock_fall_detector.qqq_components import QQQ_COMPONENTS


def test_resolve_tickers_returns_explicit_list_when_given():
    assert resolve_tickers(["AAPL", "MSFT"]) == ["AAPL", "MSFT"]


def test_resolve_tickers_defaults_to_qqq_components_when_empty():
    assert resolve_tickers([]) == QQQ_COMPONENTS


def test_format_summary_table_includes_all_results():
    results = [
        FallResult(ticker="A", start_price=100.0, end_price=88.0, pct_change=-12.0, market_cap_before=20e9),
        FallResult(ticker="B", start_price=50.0, end_price=44.0, pct_change=-12.0, market_cap_before=15e9),
    ]
    table = format_summary_table(results)
    assert "A" in table
    assert "B" in table
    assert "-12.00" in table


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
