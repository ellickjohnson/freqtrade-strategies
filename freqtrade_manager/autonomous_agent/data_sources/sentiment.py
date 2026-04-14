"""
Sentiment data sources for research agent.

Provides social sentiment from Reddit and LunarCrush with graceful
fallback to mock data when API keys are missing.
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
class SentimentItem:
    """Represents a sentiment data point."""
    source: str
    platform: str  # reddit, twitter, lunarcrush
    content: str
    sentiment: float  # -1 to 1
    engagement: int  # likes, upvotes, comments
    timestamp: datetime
    entities: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class SentimentSource:
    """Base class for sentiment sources."""

    async def get_sentiment(self, limit: int = 100) -> List[SentimentItem]:
        """Fetch sentiment data. Override in subclasses."""
        raise NotImplementedError


class RedditSource(SentimentSource):
    """
    Reddit sentiment source.

    Uses Reddit's public API (no authentication required for read access,
    but rate-limited). For authenticated access, use PRAW library.

    Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET for full access.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: str = "freqtrade-autonomous/1.0"
    ):
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent
        self.base_url = "https://oauth.reddit.com" if self.client_id else "https://www.reddit.com"

        # Subreddits to monitor
        self.subreddits = ["CryptoCurrency", "Bitcoin", "ethereum", "Solana"]

    async def get_sentiment(self, limit: int = 100) -> List[SentimentItem]:
        """Fetch posts from crypto subreddits."""
        if not self.client_id:
            logger.debug("Reddit credentials not configured, using public API")
            return await self._fetch_public(limit)

        return await self._fetch_authenticated(limit)

    async def _fetch_public(self, limit: int) -> List[SentimentItem]:
        """Fetch using public API (rate-limited)."""
        all_items = []

        try:
            headers = {"User-Agent": self.user_agent}

            async with aiohttp.ClientSession() as session:
                for subreddit in self.subreddits[:2]:  # Limit to 2 subreddits
                    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
                    params = {"limit": min(limit, 25)}

                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status != 200:
                            logger.warning(f"Reddit API error for r/{subreddit}: {response.status}")
                            continue

                        data = await response.json()
                        children = data.get("data", {}).get("children", [])

                        for child in children:
                            post = child.get("data", {})
                            all_items.append(self._parse_post(post, "reddit"))

                    # Rate limiting
                    await asyncio.sleep(1)

            logger.info(f"Fetched {len(all_items)} Reddit posts")
            return all_items

        except Exception as e:
            logger.error(f"Error fetching from Reddit: {e}")
            return []

    async def _fetch_authenticated(self, limit: int) -> List[SentimentItem]:
        """Fetch using authenticated API (higher rate limits)."""
        # Would use PRAW library for authenticated access
        # For now, fall back to public API
        return await self._fetch_public(limit)

    def _parse_post(self, post: Dict, platform: str) -> SentimentItem:
        """Parse a Reddit post into SentimentItem."""
        # Simple sentiment estimation from title
        title = post.get("title", "")
        sentiment = self._estimate_sentiment(title)

        # Extract entities
        entities = self._extract_entities(title)

        return SentimentItem(
            source=f"r/{post.get('subreddit', 'unknown')}",
            platform=platform,
            content=title,
            sentiment=sentiment,
            engagement=post.get("ups", 0) + post.get("num_comments", 0),
            timestamp=datetime.fromtimestamp(post.get("created_utc", 0)),
            entities=entities,
            metadata={
                "upvotes": post.get("ups", 0),
                "comments": post.get("num_comments", 0),
                "url": post.get("url", ""),
            }
        )

    def _estimate_sentiment(self, text: str) -> float:
        """Estimate sentiment from text using simple word matching."""
        text_lower = text.lower()

        positive_words = ["bull", "bullish", "moon", "surge", "rally", "gain", "profit", "up"]
        negative_words = ["bear", "bearish", "crash", "dump", "loss", "down", "sell", "dump"]

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count == negative_count:
            return 0.0
        elif positive_count > negative_count:
            return min(0.8, positive_count * 0.2)
        else:
            return max(-0.8, -negative_count * 0.2)

    def _extract_entities(self, text: str) -> List[str]:
        """Extract crypto tickers from text."""
        entities = []
        crypto_terms = {
            "bitcoin": "BTC", "btc": "BTC",
            "ethereum": "ETH", "eth": "ETH",
            "solana": "SOL", "sol": "SOL",
            "cardano": "ADA", "ada": "ADA",
            "dogecoin": "DOGE", "doge": "DOGE",
        }

        text_lower = text.lower()
        for term, symbol in crypto_terms.items():
            if term in text_lower:
                entities.append(symbol)

        return list(set(entities))


class LunarCrushSource(SentimentSource):
    """
    LunarCrush sentiment source.

    Provides social metrics and sentiment analysis.
    Free tier available with LUNARCRUSH_API_KEY.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("LUNARCRUSH_API_KEY")
        self.base_url = "https://lunarcrush.com/api4"

    async def get_sentiment(self, limit: int = 100) -> List[SentimentItem]:
        """Fetch social sentiment from LunarCrush."""
        if not self.api_key:
            logger.debug("LunarCrush API key not configured")
            return []

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}

            # Get social data for top coins
            coins = ["bitcoin", "ethereum", "solana"]
            all_items = []

            async with aiohttp.ClientSession() as session:
                for coin in coins:
                    url = f"{self.base_url}/coins/{coin}/social"
                    params = {"limit": limit // len(coins)}

                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status != 200:
                            logger.warning(f"LunarCrush API error for {coin}: {response.status}")
                            continue

                        data = await response.json()
                        posts = data.get("data", [])

                        for post in posts:
                            all_items.append(SentimentItem(
                                source=f"lunarcrush_{coin}",
                                platform="lunarcrush",
                                content=post.get("title", post.get("text", "")),
                                sentiment=post.get("sentiment", 0) / 100,  # Normalize to -1 to 1
                                engagement=post.get("interactions", 0),
                                timestamp=datetime.fromisoformat(
                                    post.get("created_at", "").replace("Z", "+00:00")
                                ) if post.get("created_at") else datetime.utcnow(),
                                entities=[coin.upper()],
                                metadata=post,
                            ))

            logger.info(f"Fetched {len(all_items)} LunarCrush posts")
            return all_items

        except Exception as e:
            logger.error(f"Error fetching from LunarCrush: {e}")
            return []


class MockSentimentSource(SentimentSource):
    """Mock sentiment source for testing/fallback."""

    async def get_sentiment(self, limit: int = 100) -> List[SentimentItem]:
        """Generate mock sentiment data."""
        now = datetime.utcnow()

        mock_sentiments = [
            {
                "source": "r/CryptoCurrency",
                "content": "Bitcoin ETF approval could trigger massive rally",
                "sentiment": 0.6,
                "engagement": 1500,
                "entities": ["BTC"],
            },
            {
                "source": "r/Bitcoin",
                "content": "Whale activity suggests accumulation phase",
                "sentiment": 0.4,
                "engagement": 800,
                "entities": ["BTC"],
            },
            {
                "source": "r/ethereum",
                "content": "ETH staking yield increases as network activity grows",
                "sentiment": 0.5,
                "engagement": 600,
                "entities": ["ETH"],
            },
            {
                "source": "r/CryptoCurrency",
                "content": "Market volatility expected as Fed decision approaches",
                "sentiment": 0.0,
                "engagement": 2000,
                "entities": ["BTC", "ETH"],
            },
            {
                "source": "r/Solana",
                "content": "New DeFi protocols launching on Solana",
                "sentiment": 0.7,
                "engagement": 400,
                "entities": ["SOL"],
            },
        ]

        items = []
        for i, data in enumerate(mock_sentiments[:limit]):
            items.append(SentimentItem(
                source=data["source"],
                platform="reddit",
                content=data["content"],
                sentiment=data["sentiment"],
                engagement=data["engagement"],
                timestamp=now - timedelta(hours=i),
                entities=data["entities"],
            ))

        return items


async def fetch_sentiment(
    sources: Optional[List[str]] = None,
    limit: int = 100,
    fallback_to_mock: bool = True
) -> List[SentimentItem]:
    """
    Fetch sentiment from configured sources.

    Args:
        sources: List of source names (reddit, lunarcrush)
        limit: Maximum items
        fallback_to_mock: Use mock if no sources return data

    Returns:
        List of SentimentItem objects.
    """
    sources = sources or ["reddit", "lunarcrush"]
    all_items: List[SentimentItem] = []

    if "reddit" in sources:
        reddit_source = RedditSource()
        reddit_items = await reddit_source.get_sentiment(limit=limit)
        all_items.extend(reddit_items)

    if "lunarcrush" in sources:
        lc_source = LunarCrushSource()
        lc_items = await lc_source.get_sentiment(limit=limit)
        all_items.extend(lc_items)

    # Fallback to mock
    if not all_items and fallback_to_mock:
        logger.info("No sentiment from APIs, using mock data")
        mock_source = MockSentimentSource()
        all_items = await mock_source.get_sentiment(limit=limit)

    # Sort by engagement
    all_items.sort(key=lambda x: x.engagement, reverse=True)

    return all_items[:limit]