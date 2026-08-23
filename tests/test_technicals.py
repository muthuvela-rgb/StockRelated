from stock_fall_detector.technicals import compute_bollinger, compute_rsi


def test_compute_rsi_all_gains_is_100():
    closes = [100 + i for i in range(20)]  # strictly rising
    assert compute_rsi(closes) == 100.0


def test_compute_rsi_all_losses_is_0():
    closes = [100 - i for i in range(20)]  # strictly falling
    assert compute_rsi(closes) == 0.0


def test_compute_rsi_flat_series_is_none_avg_loss_zero():
    # flat prices: no losses at all -> avg_loss stays 0 -> RSI defined as 100
    closes = [100.0] * 20
    assert compute_rsi(closes) == 100.0


def test_compute_rsi_insufficient_data_returns_none():
    assert compute_rsi([100.0, 101.0, 102.0], period=14) is None


def test_compute_bollinger_price_at_sma_gives_percent_b_half():
    # Alternating series centered on 100 so the last close equals the SMA.
    closes = [100.0] * 19 + [100.0]
    bb = compute_bollinger(closes, period=20)
    assert bb is not None
    assert bb.sma == 100.0
    assert bb.percent_b == 0.5
    assert bb.zone == "lower half"


def test_compute_bollinger_price_above_upper_band():
    closes = [100.0] * 19 + [200.0]
    bb = compute_bollinger(closes, period=20)
    assert bb is not None
    assert bb.percent_b > 1
    assert bb.zone == "above upper band"


def test_compute_bollinger_insufficient_data_returns_none():
    assert compute_bollinger([100.0, 101.0], period=20) is None
