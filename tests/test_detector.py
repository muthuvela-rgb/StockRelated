from stock_fall_detector.detector import StockPriceData, find_falling_stocks


class FakeDataSource:
    def __init__(self, data: dict[str, StockPriceData]):
        self._data = data

    def get_price_data(self, ticker: str, lookback_days: int):
        return self._data.get(ticker)


def test_flags_large_cap_stock_that_fell_more_than_threshold():
    source = FakeDataSource(
        {
            "BIG": StockPriceData("BIG", start_price=100.0, end_price=85.0, shares_outstanding=200_000_000),
        }
    )
    # market cap before = 100 * 200M = $20B, fall = 15%
    results = find_falling_stocks(["BIG"], source)
    assert len(results) == 1
    assert results[0].ticker == "BIG"
    assert round(results[0].pct_change, 2) == -15.0
    assert results[0].market_cap_before == 20_000_000_000


def test_excludes_stock_below_market_cap_threshold():
    source = FakeDataSource(
        {
            "SMALL": StockPriceData("SMALL", start_price=50.0, end_price=40.0, shares_outstanding=100_000_000),
        }
    )
    # market cap before = 50 * 100M = $5B, below default $10B threshold
    results = find_falling_stocks(["SMALL"], source)
    assert results == []


def test_excludes_stock_that_did_not_fall_enough():
    source = FakeDataSource(
        {
            "STABLE": StockPriceData("STABLE", start_price=100.0, end_price=95.0, shares_outstanding=500_000_000),
        }
    )
    # market cap before = $50B (qualifies), but only fell 5%
    results = find_falling_stocks(["STABLE"], source)
    assert results == []


def test_excludes_stock_that_rose():
    source = FakeDataSource(
        {
            "UP": StockPriceData("UP", start_price=100.0, end_price=120.0, shares_outstanding=500_000_000),
        }
    )
    results = find_falling_stocks(["UP"], source)
    assert results == []


def test_missing_data_is_skipped():
    source = FakeDataSource({})
    results = find_falling_stocks(["UNKNOWN"], source)
    assert results == []


def test_custom_thresholds():
    source = FakeDataSource(
        {
            "MID": StockPriceData("MID", start_price=100.0, end_price=94.0, shares_outstanding=150_000_000),
        }
    )
    # market cap before = $15B, fell 6%
    assert find_falling_stocks(["MID"], source, fall_threshold_pct=10.0) == []
    results = find_falling_stocks(["MID"], source, fall_threshold_pct=5.0, min_market_cap=10_000_000_000)
    assert len(results) == 1


def test_results_sorted_by_worst_fall_first():
    source = FakeDataSource(
        {
            "A": StockPriceData("A", start_price=100.0, end_price=88.0, shares_outstanding=200_000_000),
            "B": StockPriceData("B", start_price=100.0, end_price=80.0, shares_outstanding=200_000_000),
        }
    )
    results = find_falling_stocks(["A", "B"], source)
    assert [r.ticker for r in results] == ["B", "A"]


def test_zero_shares_outstanding_is_skipped():
    source = FakeDataSource(
        {
            "ZERO": StockPriceData("ZERO", start_price=100.0, end_price=80.0, shares_outstanding=0),
        }
    )
    results = find_falling_stocks(["ZERO"], source)
    assert results == []
