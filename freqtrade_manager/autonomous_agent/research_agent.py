"""
Research Agent - Gathers and analyzes external data sources.

Handles news, sentiment, on-chain data, and macro indicators.
Uses LLM to extract trading-relevant insights from raw data.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient
from .knowledge_graph import KnowledgeGraph, ResearchFinding, EntityType
from .data_sources.news import fetch_news, NewsItem
from .data_sources.sentiment import fetch_sentiment, SentimentItem
from .data_sources.onchain import fetch_onchain_metrics, analyze_onchain_signals, OnChainMetric
from .data_sources.macro import fetch_macro_indicators, analyze_macro_environment, MacroIndicator

logger = logging.getLogger(__name__)


@dataclass
class DataSourceConfig:
    """Configuration for a data source."""
    enabled: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    rate_limit_per_minute: int = 60
    cache_ttl_seconds: int = 300


@dataclass
class ResearchConfig:
    """Configuration for research agent."""
    # News sources
    news_enabled: bool = True
    newsapi_key: Optional[str] = None
    cryptocompare_key: Optional[str] = None

    # Sentiment sources
    sentiment_enabled: bool = True
    twitter_enabled: bool = False  # Requires API access
    reddit_enabled: bool = True

    # On-chain data
    onchain_enabled: bool = True
    glassnode_key: Optional[str] = None

    # Macro data
    macro_enabled: bool = True
    fred_key: Optional[str] = None

    # Research settings
    max_findings_per_cycle: int = 50
    min_confidence: float = 0.3
    relevance_threshold: float = 0.5


class ResearchAgent:
    """
    Agent that continuously researches external data sources.

    Responsibilities:
    - Fetch news from multiple sources
    - Analyze social sentiment
    - Monitor on-chain metrics
    - Track macro economic indicators
    - Extract trading-relevant insights
    - Store findings in knowledge graph
    """

    def __init__(
        self,
        db_path: str,
        llm_client: LLMClient,
        knowledge_graph: KnowledgeGraph,
        config: Optional[ResearchConfig] = None,
    ):
        self.db_path = db_path
        self.llm = llm_client
        self.kg = knowledge_graph
        self.config = config or ResearchConfig()

        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    async def run(self) -> List[Dict]:
        """
        Run research cycle - gather data from all sources.

        Returns list of research findings.
        """
        findings = []

        # Run all research tasks in parallel
        tasks = []

        if self.config.news_enabled:
            tasks.append(self._research_news())

        if self.config.sentiment_enabled:
            tasks.append(self._research_sentiment())

        if self.config.onchain_enabled:
            tasks.append(self._research_onchain())

        if self.config.macro_enabled:
            tasks.append(self._research_macro())

        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Research task failed: {result}")
            elif isinstance(result, list):
                findings.extend(result)

        # Filter by confidence and relevance
        filtered = [
            f for f in findings
            if f.get("confidence", 0) >= self.config.min_confidence
            and f.get("relevance", 0) >= self.config.relevance_threshold
        ][:self.config.max_findings_per_cycle]

        # Store findings in knowledge graph
        for finding in filtered:
            self._store_finding(finding)

        return filtered

    async def _research_news(self) -> List[Dict]:
        """Research news from multiple sources."""
        findings = []

        # Determine which sources to use
        sources = []
        if self.config.cryptocompare_key:
            sources.append("cryptocompare")
        if self.config.newsapi_key:
            sources.append("newsapi")

        # Fetch news from data sources (with fallback to mock)
        try:
            news_items = await fetch_news(
                sources=sources if sources else None,
                limit=20,
                fallback_to_mock=True
            )

            for item in news_items[:15]:
                analyzed = await self._analyze_news_item(item)
                if analyzed:
                    findings.append(analyzed)

        except Exception as e:
            logger.error(f"News fetch failed: {e}")

        return findings

    async def _fetch_cryptocompare_news(self) -> List[Dict]:
        """Fetch news from CryptoCompare API (deprecated - use fetch_news)."""
        # This method is now handled by data_sources.news
        return []

    async def _analyze_news_item(self, item) -> Optional[Dict]:
        """Use LLM to analyze news item and extract trading insights."""
        try:
            # Handle both NewsItem objects and dicts
            if isinstance(item, NewsItem):
                title = item.title
                body = item.summary
                source = item.source
                url = item.url
                entities = item.entities
            else:
                title = item.get('title', '')
                body = item.get('body', item.get('description', item.get('summary', '')))[:1000]
                source = item.get('source', 'unknown')
                url = item.get('url', '')
                entities = item.get('entities', item.get('categories', []))

            schema = {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "sentiment": {"type": "number", "minimum": -1, "maximum": 1},
                    "relevance": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence": {"type": "number"},
                    "impact_areas": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "affected_assets": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "trading_implications": {"type": "string"},
                    "time_horizon": {"type": "string", "enum": ["immediate", "short", "medium", "long"]},
                },
                "required": ["summary", "sentiment", "relevance", "confidence"]
            }

            prompt = f"""Analyze this news item for trading relevance:

Title: {title}
Body: {body[:1000]}
Source: {source}

Extract:
1. A brief summary
2. Sentiment score (-1 to 1, negative to positive)
3. Relevance to crypto trading (0 to 1)
4. Confidence in analysis (0 to 1)
5. Impact areas (e.g., "macro", "regulation", "technology")
6. Affected assets (e.g., "BTC", "ETH", "market-wide")
7. Trading implications
8. Time horizon for impact"""

            result = await self.llm.analyze(prompt, schema, system_prompt="You are a financial news analyst.")

            if result:
                return {
                    "id": f"news_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(title) % 10000}",
                    "source": "news",
                    "finding_type": "news_analysis",
                    "title": title,
                    "content": result.get("summary", ""),
                    "sentiment": result.get("sentiment", 0),
                    "relevance": result.get("relevance", 0.5),
                    "impact_assessment": {
                        "areas": result.get("impact_areas", []),
                        "assets": result.get("affected_assets", entities if isinstance(entities, list) else []),
                        "trading_implications": result.get("trading_implications", ""),
                        "time_horizon": result.get("time_horizon", "short"),
                    },
                    "entities": result.get("affected_assets", entities if isinstance(entities, list) else []),
                    "confidence": result.get("confidence", 0.5),
                    "metadata": {
                        "url": url,
                        "original_source": source,
                    },
                }
        except Exception as e:
            logger.error(f"News analysis failed: {e}")

        return None

    async def _research_sentiment(self) -> List[Dict]:
        """Research social sentiment from Twitter, Reddit, etc."""
        findings = []

        # Determine which sources to use
        sources = []
        if self.config.reddit_enabled:
            sources.append("reddit")

        # Fetch sentiment from data sources (with fallback to mock)
        try:
            sentiment_items = await fetch_sentiment(
                sources=sources if sources else None,
                limit=100,
                fallback_to_mock=True
            )

            for item in sentiment_items[:20]:
                analyzed = await self._analyze_sentiment_item(item)
                if analyzed:
                    findings.append(analyzed)

        except Exception as e:
            logger.error(f"Sentiment fetch failed: {e}")

        return findings

    async def _analyze_sentiment_item(self, item) -> Optional[Dict]:
        """Analyze sentiment data for trading insights."""
        try:
            # Handle both SentimentItem objects and dicts
            if isinstance(item, SentimentItem):
                platform = item.platform
                topic = item.source  # source contains topic/subreddit
                sentiment_score = item.sentiment
                engagement = item.engagement
                content = item.content
                entities = item.entities
            else:
                platform = item.get('platform', 'unknown')
                topic = item.get('topic', item.get('subreddit', 'unknown'))
                sentiment_score = item.get('sentiment_score', item.get('sentiment', 0.5))
                engagement = item.get('mention_count', item.get('engagement', 0))
                content = item.get('content', item.get('title', ''))
                entities = item.get('entities', [])

            schema = {
                "type": "object",
                "properties": {
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "contrarian_signal": {"type": "boolean"},
                    "trading_implication": {"type": "string"},
                }
            }

            prompt = f"""Analyze this social sentiment data:

Platform: {platform}
Topic: {topic}
Sentiment Score: {sentiment_score}
Engagement: {engagement}
Content Sample: {content[:200] if content else 'N/A'}

Interpret:
1. What does this sentiment indicate?
2. Is this a contrarian signal? (extreme sentiment often reverses)
3. What's the trading implication?"""

            result = await self.llm.analyze(prompt, schema)

            if result:
                return {
                    "id": f"sentiment_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(topic) % 10000}",
                    "source": "sentiment",
                    "finding_type": "social_sentiment",
                    "title": f"{platform} sentiment on {topic}",
                    "content": result.get("interpretation", ""),
                    "sentiment": sentiment_score,
                    "relevance": 0.7,  # Sentiment always relevant
                    "impact_assessment": {
                        "contrarian_signal": result.get("contrarian_signal", False),
                        "trading_implication": result.get("trading_implication", ""),
                    },
                    "entities": entities if isinstance(entities, list) else [topic],
                    "confidence": result.get("confidence", 0.6),
                    "metadata": {
                        "platform": platform,
                        "engagement": engagement,
                    },
                }
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")

        return None

    async def _research_onchain(self) -> List[Dict]:
        """Research on-chain metrics (Glassnode, Dune, etc.)."""
        findings = []

        # Fetch on-chain metrics from data sources (with fallback to mock)
        try:
            # Use configured metrics or defaults
            metrics = ["active_addresses", "exchange_balance", "mvrv", "sopr"]
            assets = ["BTC", "ETH"]

            onchain_metrics = await fetch_onchain_metrics(
                metrics=metrics,
                assets=assets,
                fallback_to_mock=True
            )

            # Analyze the metrics for signals
            if onchain_metrics:
                signals = analyze_onchain_signals(onchain_metrics)

                # Create a combined finding from signals
                if signals.get("signals"):
                    finding = {
                        "id": f"onchain_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                        "source": "onchain",
                        "finding_type": "onchain_signals",
                        "title": "On-chain Analysis",
                        "content": signals.get("interpretation", ""),
                        "sentiment": signals.get("overall_sentiment", 0),
                        "relevance": 0.8,
                        "impact_assessment": {
                            "signals": signals.get("signals", []),
                            "confidence": signals.get("confidence", 0.5),
                        },
                        "entities": ["BTC", "ETH"],
                        "confidence": signals.get("confidence", 0.5),
                        "metadata": {
                            "metrics_count": len(onchain_metrics),
                            "overall_sentiment": signals.get("overall_sentiment", 0),
                        },
                    }
                    findings.append(finding)

            # Also analyze individual metrics
            for metric in onchain_metrics[:5]:
                analyzed = await self._analyze_onchain_item(metric)
                if analyzed:
                    findings.append(analyzed)

        except Exception as e:
            logger.error(f"On-chain fetch failed: {e}")

        return findings

    async def _analyze_onchain_item(self, item) -> Optional[Dict]:
        """Analyze on-chain data for trading insights."""
        try:
            # Handle both OnChainMetric objects and dicts
            if isinstance(item, OnChainMetric):
                metric = item.metric_name
                value = item.value
                unit = item.unit
                asset = item.asset
                trend = "positive" if item.change_24h > 0 else "negative"
            else:
                metric = item.get('metric', 'unknown')
                value = item.get('value', 0)
                unit = item.get('unit', '')
                asset = item.get('asset', 'market-wide')
                trend = item.get('trend', 'unknown')

            schema = {
                "type": "object",
                "properties": {
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "signal_strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
                    "trading_implication": {"type": "string"},
                }
            }

            prompt = f"""Analyze this on-chain metric:

Metric: {metric}
Asset: {asset}
Value: {value} {unit}
Trend: {trend}

What does this metric indicate for trading?"""

            result = await self.llm.analyze(prompt, schema)

            if result:
                return {
                    "id": f"onchain_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(metric) % 10000}",
                    "source": "onchain",
                    "finding_type": "onchain_metric",
                    "title": f"On-chain: {metric}",
                    "content": result.get("interpretation", ""),
                    "sentiment": 0.7 if trend in ["positive", "increasing"] else 0.3,
                    "relevance": 0.8,  # On-chain data highly relevant
                    "impact_assessment": {
                        "signal_strength": result.get("signal_strength", "moderate"),
                        "trading_implication": result.get("trading_implication", ""),
                    },
                    "entities": [asset],
                    "confidence": result.get("confidence", 0.7),
                    "metadata": {"metric": metric, "value": value, "unit": unit},
                }
        except Exception as e:
            logger.error(f"On-chain analysis failed: {e}")

        return None

    async def _research_macro(self) -> List[Dict]:
        """Research macro economic indicators."""
        findings = []

        # Fetch macro indicators from data sources (with fallback to mock)
        try:
            # Use configured indicators or defaults
            indicators = ["dxy", "vix", "treasury_10y", "fed_funds_rate", "unemployment"]

            macro_indicators = await fetch_macro_indicators(
                indicators=indicators,
                fallback_to_mock=True
            )

            # Analyze the macro environment
            if macro_indicators:
                analysis = analyze_macro_environment(macro_indicators)

                # Create a combined finding from analysis
                if analysis:
                    finding = {
                        "id": f"macro_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                        "source": "macro",
                        "finding_type": "macro_analysis",
                        "title": f"Macro Environment: {analysis.get('overall_assessment', 'neutral').title()}",
                        "content": analysis.get("crypto_implications", ""),
                        "sentiment": 0.6 if analysis.get("overall_assessment") == "bullish" else 0.4,
                        "relevance": 0.7,
                        "impact_assessment": {
                            "risk_factors": analysis.get("risk_factors", []),
                            "opportunities": analysis.get("opportunities", []),
                            "risk_level": analysis.get("risk_level", "moderate"),
                        },
                        "entities": ["market-wide"],
                        "confidence": analysis.get("confidence", 0.5),
                        "metadata": {
                            "overall_assessment": analysis.get("overall_assessment", "neutral"),
                            "risk_level": analysis.get("risk_level", "moderate"),
                        },
                    }
                    findings.append(finding)

            # Also analyze individual indicators
            for indicator in macro_indicators[:5]:
                analyzed = await self._analyze_macro_item(indicator)
                if analyzed:
                    findings.append(analyzed)

        except Exception as e:
            logger.error(f"Macro fetch failed: {e}")

        return findings

    async def _analyze_macro_item(self, item) -> Optional[Dict]:
        """Analyze macro indicator for trading insights."""
        try:
            # Handle both MacroIndicator objects and dicts
            if isinstance(item, MacroIndicator):
                indicator = item.name
                name = item.name.upper()
                value = item.value
                unit = item.unit
                change = item.change_3m
                interpretation = item.interpretation
            else:
                indicator = item.get('indicator', 'unknown')
                name = item.get('name', item.get('indicator', '').upper())
                value = item.get('value', 0)
                unit = item.get('unit', '')
                change = item.get('change_pct', item.get('change_3m', 0))
                interpretation = item.get('interpretation', '')

            schema = {
                "type": "object",
                "properties": {
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "crypto_impact": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                }
            }

            prompt = f"""Analyze this macro economic indicator:

Indicator: {name}
Value: {value} {unit}
3M Change: {change}%

What does this mean for crypto markets?"""

            result = await self.llm.analyze(prompt, schema)

            if result:
                return {
                    "id": f"macro_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(indicator) % 10000}",
                    "source": "macro",
                    "finding_type": "economic_indicator",
                    "title": f"Macro: {name}",
                    "content": result.get("interpretation", interpretation),
                    "sentiment": 0.6 if change > 0 else 0.4,
                    "relevance": 0.7,
                    "impact_assessment": {
                        "crypto_impact": result.get("crypto_impact", ""),
                        "risk_level": result.get("risk_level", "medium"),
                    },
                    "entities": ["market-wide"],
                    "confidence": result.get("confidence", 0.6),
                    "metadata": {
                        "indicator": indicator,
                        "value": value,
                        "change_3m": change,
                    },
                }
        except Exception as e:
            logger.error(f"Macro analysis failed: {e}")

        return None

    def _store_finding(self, finding: Dict):
        """Store research finding in knowledge graph."""
        import uuid
        finding_id = finding.get("id") or f"finding_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        research_finding = ResearchFinding(
            id=finding_id,
            source=finding.get("source", "unknown"),
            finding_type=finding.get("finding_type", "general"),
            title=finding.get("title", ""),
            content=finding.get("content", ""),
            sentiment=finding.get("sentiment", 0.5),
            relevance=finding.get("relevance", 0.5),
            impact_assessment=finding.get("impact_assessment", {}),
            entities=finding.get("entities", []),
            confidence=finding.get("confidence", 0.5),
            metadata=finding.get("metadata", {}),
        )

        self.kg.add_finding(research_finding)
        logger.info(f"Stored finding: {research_finding.title}")

    async def search_findings(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search for relevant findings in knowledge graph."""
        entities = self.kg.search_entities(query, limit=limit)

        # Convert to dict format
        findings = []
        for entity in entities:
            if entity.entity_type == EntityType.FINDING:
                findings.append(entity.data)

        # Also search research findings table
        db_findings = self.kg.get_findings(source=sources[0] if sources else None, limit=limit)

        return findings + [f.to_dict() for f in db_findings]

    def get_recent_findings(self, hours: int = 24, limit: int = 50) -> List[Dict]:
        """Get recent research findings."""
        since = datetime.utcnow() - timedelta(hours=hours)
        findings = self.kg.get_findings(since=since, limit=limit)
        return [f.to_dict() for f in findings]