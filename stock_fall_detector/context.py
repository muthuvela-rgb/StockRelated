"""Data models and source protocol for the extra "why did it fall" context:
recent news, analyst opinion, and social sentiment for a ticker.

Kept separate from detector.py's PriceDataSource so the core fall-detection
logic stays free of this (optional, best-effort) enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    publisher: str
    link: str
    published_at: str  # human-readable, source-provided formatting


@dataclass(frozen=True)
class AnalystAction:
    firm: str
    action: str  # e.g. "main", "init", "up", "down", "reit"
    from_grade: str
    to_grade: str
    price_target: Optional[float]
    date: str


@dataclass(frozen=True)
class AnalystSummary:
    recommendation: Optional[str]  # e.g. "buy", "hold", "sell"
    mean_target_price: Optional[float]
    num_analysts: Optional[int]
    upside_pct: Optional[float]  # mean_target_price vs current price
    recent_actions: list[AnalystAction]


@dataclass(frozen=True)
class SocialSentiment:
    bullish_pct: float
    bearish_pct: float
    sample_size: int
    source: str = "StockTwits"


@dataclass(frozen=True)
class StockContext:
    ticker: str
    headlines: list[NewsHeadline]
    analyst: Optional[AnalystSummary]
    social: Optional[SocialSentiment]


class ContextSource(Protocol):
    def get_context(self, ticker: str, current_price: Optional[float] = None) -> StockContext:
        ...
