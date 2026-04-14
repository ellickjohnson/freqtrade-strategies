"""
News data sources for research agent.

Provides news from CryptoCompare and NewsAPI with graceful fallback
to mock data when API keys are missing.
"""

import aiohttp
import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """Represents a news article."""
    title: str
    source: str
    url: str
    published_at: datetime
    summary: str = ""
    sentiment: float = 0.0  # -1 to 1
    relevance: float = 0.5  # 0 to 1
    entities: List[str] = field(default_factory=list)
    raw_data: Dict = field(default_factory=dict)


class NewsSource:
    """Base class for news sources."""

    async def fetch(self, limit: int = 20) -> List[NewsItem]:
        """Fetch news items. Override in subclasses."""
        raise NotImplementedError


class CryptoCompareSource(NewsSource):
    """
    CryptoCompare news API source.

    Requires CRYPTOCOMPARE_API_KEY environment variable.
    Free tier: 100,000 calls/month
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CRYPTOCOMPARE_API_KEY")
        self.base_url = "https://min-api.cryptocompare.com/data/v2/news/"

    async def fetch(self, limit: int = 20) -> List[NewsItem]:
        """Fetch crypto news from CryptoCompare."""
        if not self.api_key:
            logger.debug("CryptoCompare API key not configured")
            return []

        try:
            params = {
                "lang": "EN",
                "limit": limit,
            }
            headers = {"Api-Key": self.api_key}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}latest",
                    params=params,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        logger.error(f"CryptoCompare API error: {response.status}")
                        return []

                    data = await response.json()
                    news_items = []

                    for item in data.get("Data", [])[:limit]:
                        news_items.append(NewsItem(
                            title=item.get("title", ""),
                            source=item.get("source", "unknown"),
                            url=item.get("url", ""),
                            published_at=datetime.fromtimestamp(item.get("published_on", 0)),
                            summary=item.get("body", "")[:500],
                            entities=item.get("categories", "").split(","),
                            raw_data=item,
                        ))

                    logger.info(f"Fetched {len(news_items)} news items from CryptoCompare")
                    return news_items

        except Exception as e:
            logger.error(f"Error fetching from CryptoCompare: {e}")
            return []


class NewsAPISource(NewsSource):
    """
    General news API source.

    Requires NEWSAPI_KEY environment variable.
    Free tier: 100 requests/day
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self.base_url = "https://newsapi.org/v2/everything"

    async def fetch(
        self,
        query: str = "crypto OR bitcoin OR ethereum OR blockchain",
        limit: int = 20
    ) -> List[NewsItem]:
        """Fetch news from NewsAPI."""
        if not self.api_key:
            logger.debug("NewsAPI key not configured")
            return []

        try:
            from_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

            params = {
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": limit,
                "language": "en",
            }
            headers = {"X-Api-Key": self.api_key}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url,
                    params=params,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        logger.error(f"NewsAPI error: {response.status}")
                        return []

                    data = await response.json()
                    news_items = []

                    for item in data.get("articles", [])[:limit]:
                        # Extract entities from title/description
                        title = item.get("title", "")
                        description = item.get("description", "") or ""
                        entities = self._extract_entities(title + " " + description)

                        news_items.append(NewsItem(
                            title=title,
                            source=item.get("source", {}).get("name", "unknown"),
                            url=item.get("url", ""),
                            published_at=datetime.fromisoformat(
                                item.get("publishedAt", "").replace("Z", "+00:00")
                            ) if item.get("publishedAt") else datetime.utcnow(),
                            summary=description[:500],
                            entities=entities,
                            raw_data=item,
                        ))

                    logger.info(f"Fetched {len(news_items)} news items from NewsAPI")
                    return news_items

        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {e}")
            return []

    def _extract_entities(self, text: str) -> List[str]:
        """Extract crypto entities from text."""
        entities = []
        crypto_terms = {
            "bitcoin": "BTC",
            "btc": "BTC",
            "ethereum": "ETH",
            "eth": "ETH",
            "solana": "SOL",
            "cardano": "ADA",
            "xrp": "XRP",
            "dogecoin": "DOGE",
            "polkadot": "DOT",
            "avalanche": "AVAX",
        }

        text_lower = text.lower()
        for term, symbol in crypto_terms.items():
            if term in text_lower:
                entities.append(symbol)

        return list(set(entities))


class MockNewsSource(NewsSource):
    """Mock news source for testing/fallback."""

    async def fetch(self, limit: int = 20) -> List[NewsItem]:
        """Generate mock news items."""
        now = datetime.utcnow()

        mock_news = [
            {
                "title": "Bitcoin Surges Past $70K as Institutional Adoption Grows",
                "source": "Mock News",
                "summary": "Bitcoin continues its upward trajectory as major institutions announce new cryptocurrency investments.",
                "sentiment": 0.7,
                "entities": ["BTC"],
            },
            {
                "title": "Ethereum 2.0 Staking Reaches New All-Time High",
                "source": "Mock News",
                "summary": "Ethereum staking deposits have reached unprecedented levels as more validators join the network.",
                "sentiment": 0.5,
                "entities": ["ETH"],
            },
            {
                "title": "Market Analysis: Crypto Volatility Expected in Q4",
                "source": "Mock Analysis",
                "summary": "Analysts predict increased market volatility as we approach year-end regulatory decisions.",
                "sentiment": 0.0,
                "entities": ["BTC", "ETH"],
            },
            {
                "title": "DeFi Total Value Locked Exceeds $100 Billion",
                "source": "Mock News",
                "summary": "Decentralized finance protocols continue to attract capital with innovative yield opportunities.",
                "sentiment": 0.6,
                "entities": ["ETH", "SOL"],
            },
            {
                "title": "Central Banks Explore Digital Currency Frameworks",
                "source": "Mock News",
                "summary": "Multiple central banks announce pilot programs for central bank digital currencies.",
                "sentiment": 0.2,
                "entities": [],
            },
        ]

        news_items = []
        for i, item in enumerate(mock_news[:limit]):
            news_items.append(NewsItem(
                title=item["title"],
                source=item["source"],
                url=f"https://mock.news/{i}",
                published_at=now - timedelta(hours=i),
                summary=item["summary"],
                sentiment=item["sentiment"],
                entities=item["entities"],
            ))

        return news_items


async def fetch_news(
    sources: Optional[List[str]] = None,
    limit: int = 20,
    fallback_to_mock: bool = True
) -> List[NewsItem]:
    """
    Fetch news from configured sources.

    Args:
        sources: List of source names to use (cryptocompare, newsapi)
        limit: Maximum items per source
        fallback_to_mock: Use mock data if no sources return data

    Returns:
        List of NewsItem objects.
    """
    sources = sources or ["cryptocompare", "newsapi"]
    all_news: List[NewsItem] = []

    if "cryptocompare" in sources:
        cc_source = CryptoCompareSource()
        cc_news = await cc_source.fetch(limit=limit)
        all_news.extend(cc_news)

    if "newsapi" in sources:
        na_source = NewsAPISource()
        na_news = await na_source.fetch(limit=limit)
        all_news.extend(na_news)

    # Fallback to mock if no data
    if not all_news and fallback_to_mock:
        logger.info("No news from APIs, using mock data")
        mock_source = MockNewsSource()
        all_news = await mock_source.fetch(limit=limit)

    # Deduplicate by title
    seen_titles = set()
    unique_news = []
    for item in all_news:
        title_key = item.title.lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_news.append(item)

    return unique_news