"""
Data Sources - External data integrations for research agent.

Provides news, sentiment, on-chain, and macro data from various APIs.
Each source has graceful fallback to mock data when API keys are missing.
"""

from .news import NewsSource, CryptoCompareSource, NewsAPISource
from .sentiment import SentimentSource, RedditSource, LunarCrushSource
from .onchain import OnChainSource, GlassnodeSource
from .macro import MacroSource, FREDSource

__all__ = [
    "NewsSource",
    "CryptoCompareSource",
    "NewsAPISource",
    "SentimentSource",
    "RedditSource",
    "LunarCrushSource",
    "OnChainSource",
    "GlassnodeSource",
    "MacroSource",
    "FREDSource",
]