"""ContextSource implementation: recent news from Yahoo Finance search,
analyst opinion from Yahoo Finance's quoteSummary, and social sentiment
from StockTwits' public message stream.

Each of the three pieces is fetched independently and best-effort: if one
fails (rate limit, network error, ticker not covered) it comes back as an
empty/None value rather than failing the whole report.
"""

from __future__ import annotations

import datetime
from typing import Optional

from ._yahoo_http import YahooSession
from .context import AnalystAction, AnalystSummary, NewsHeadline, SocialSentiment, StockContext

_MAX_HEADLINES = 5
_MAX_ANALYST_ACTIONS = 3
_STOCKTWITS_SAMPLE = 30


class YahooStockTwitsContextSource:
    def __init__(self, timeout: float = 10.0) -> None:
        self._yahoo = YahooSession(timeout=timeout)
        self._timeout = timeout

    def get_context(self, ticker: str, current_price: Optional[float] = None) -> StockContext:
        return StockContext(
            ticker=ticker,
            headlines=self._get_headlines(ticker),
            analyst=self._get_analyst_summary(ticker, current_price),
            social=self._get_social_sentiment(ticker),
        )

    def _get_headlines(self, ticker: str) -> list[NewsHeadline]:
        data = self._yahoo.get_json(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": ticker, "newsCount": 15, "quotesCount": 0},
        )
        if not data:
            return []

        headlines = []
        for item in data.get("news", []):
            related = [t.upper() for t in item.get("relatedTickers", [])]
            if ticker.upper() not in related:
                continue
            publish_time = item.get("providerPublishTime")
            published_at = (
                datetime.datetime.utcfromtimestamp(publish_time).strftime("%Y-%m-%d")
                if publish_time
                else ""
            )
            headlines.append(
                NewsHeadline(
                    title=item.get("title", ""),
                    publisher=item.get("publisher", ""),
                    link=item.get("link", ""),
                    published_at=published_at,
                )
            )
            if len(headlines) >= _MAX_HEADLINES:
                break
        return headlines

    def _get_analyst_summary(
        self, ticker: str, current_price: Optional[float]
    ) -> Optional[AnalystSummary]:
        crumb = self._yahoo.crumb()
        if crumb is None:
            return None

        data = self._yahoo.get_json(
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
            params={"modules": "financialData,upgradeDowngradeHistory", "crumb": crumb},
        )
        if not data:
            return None

        results = data.get("quoteSummary", {}).get("result")
        if not results:
            return None

        result = results[0]
        financial_data = result.get("financialData", {})
        mean_target = financial_data.get("targetMeanPrice", {}).get("raw")
        num_analysts = financial_data.get("numberOfAnalystOpinions", {}).get("raw")
        recommendation = financial_data.get("recommendationKey")

        upside_pct = None
        if mean_target and current_price:
            upside_pct = (mean_target - current_price) / current_price * 100

        recent_actions = []
        history = result.get("upgradeDowngradeHistory", {}).get("history", [])
        for entry in history[:_MAX_ANALYST_ACTIONS]:
            grade_date = entry.get("epochGradeDate")
            date_str = (
                datetime.datetime.utcfromtimestamp(grade_date).strftime("%Y-%m-%d")
                if grade_date
                else ""
            )
            recent_actions.append(
                AnalystAction(
                    firm=entry.get("firm", ""),
                    action=entry.get("action", ""),
                    from_grade=entry.get("fromGrade", ""),
                    to_grade=entry.get("toGrade", ""),
                    price_target=entry.get("currentPriceTarget"),
                    date=date_str,
                )
            )

        return AnalystSummary(
            recommendation=recommendation,
            mean_target_price=mean_target,
            num_analysts=num_analysts,
            upside_pct=upside_pct,
            recent_actions=recent_actions,
        )

    def _get_social_sentiment(self, ticker: str) -> Optional[SocialSentiment]:
        # Reuses the Yahoo session's browser-like headers/User-Agent, which
        # StockTwits also requires (a bare `requests.get` gets 403'd).
        data = self._yahoo.get_json(
            f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        )
        if not data:
            return None

        messages = data.get("messages", [])[:_STOCKTWITS_SAMPLE]
        bullish = 0
        bearish = 0
        for msg in messages:
            sentiment = msg.get("entities", {}).get("sentiment")
            if not sentiment:
                continue
            basic = sentiment.get("basic")
            if basic == "Bullish":
                bullish += 1
            elif basic == "Bearish":
                bearish += 1

        tagged = bullish + bearish
        if tagged == 0:
            return None

        return SocialSentiment(
            bullish_pct=bullish / tagged * 100,
            bearish_pct=bearish / tagged * 100,
            sample_size=tagged,
        )
