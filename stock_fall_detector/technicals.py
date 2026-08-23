"""Data models, pure calculations, and source protocol for technical
indicators: RSI, Bollinger Bands, implied volatility, and high/low levels.

The math (compute_rsi, compute_bollinger) is pure and unit-testable without
network access; fetching the underlying price history is a separate concern
(see yahoo_technicals_source.py).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class BollingerPosition:
    sma: float
    upper_band: float
    lower_band: float
    percent_b: float  # 0.0 = at lower band, 1.0 = at upper band; can go outside [0, 1]
    zone: str  # "above upper band" | "upper half" | "lower half" | "below lower band"


@dataclass(frozen=True)
class Technicals:
    ticker: str
    current_price: Optional[float]
    rsi_14: Optional[float]
    implied_volatility_pct: Optional[float]  # ATM, ~30-day expiry, annualized %
    bollinger: Optional[BollingerPosition]
    fifty_two_week_high: Optional[float]
    fifty_two_week_low: Optional[float]
    all_time_high: Optional[float]


class TechnicalsSource(Protocol):
    def get_technicals(self, ticker: str) -> Technicals:
        ...


def compute_rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI over the most recent `period` days of the given closes."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_bollinger(
    closes: Sequence[float], period: int = 20, num_std: float = 2.0
) -> Optional[BollingerPosition]:
    if len(closes) < period:
        return None

    window = closes[-period:]
    sma = statistics.mean(window)
    std = statistics.pstdev(window)
    upper = sma + num_std * std
    lower = sma - num_std * std
    price = closes[-1]

    percent_b = 0.5 if upper == lower else (price - lower) / (upper - lower)
    if percent_b > 1:
        zone = "above upper band"
    elif percent_b > 0.5:
        zone = "upper half"
    elif percent_b >= 0:
        zone = "lower half"
    else:
        zone = "below lower band"

    return BollingerPosition(
        sma=sma, upper_band=upper, lower_band=lower, percent_b=percent_b, zone=zone
    )
