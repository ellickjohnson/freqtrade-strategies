"""
On-chain data sources for research agent.

Provides on-chain metrics from Glassnode and other sources with graceful
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
class OnChainMetric:
    """Represents an on-chain metric data point."""
    asset: str  # BTC, ETH, etc.
    metric_name: str
    value: float
    unit: str
    timestamp: datetime
    change_24h: float = 0.0
    change_7d: float = 0.0
    metadata: Dict = field(default_factory=dict)


class OnChainSource:
    """Base class for on-chain data sources."""

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        """Fetch a single metric. Override in subclasses."""
        raise NotImplementedError

    async def get_metrics(self, metrics: List[str], asset: str = "BTC") -> List[OnChainMetric]:
        """Fetch multiple metrics."""
        results = []
        for metric in metrics:
            result = await self.get_metric(metric, asset)
            if result:
                results.append(result)
        return results


class GlassnodeSource(OnChainSource):
    """
    Glassnode on-chain data source.

    Requires GLASSNODE_API_KEY environment variable.
    Paid API with comprehensive on-chain metrics.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GLASSNODE_API_KEY")
        self.base_url = "https://api.glassnode.com/v1/metrics"

        # Common metric mappings
        self.metric_endpoints = {
            "active_addresses": "/addresses/active_count",
            "exchange_balance": "/bitcoin/distribution_balance_exchanges",
            "whale_balance": "/bitcoin/balance_distribution",
            "mvrv": "/market/mvrv",
            "nvt": "/indicators/nvt",
            "sopr": "/indicators/sopr",
            "net_transfers": "/bitcoin/exchanges/net_transfers",
            "miner_outflow": "/bitcoin/miners/outflow",
        }

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        """Fetch a single on-chain metric from Glassnode."""
        if not self.api_key:
            logger.debug("Glassnode API key not configured")
            return None

        endpoint = self.metric_endpoints.get(metric)
        if not endpoint:
            logger.warning(f"Unknown Glassnode metric: {metric}")
            return None

        try:
            params = {
                "a": asset.lower(),
                "api_key": self.api_key,
            }

            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}{endpoint}"
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Glassnode API error: {response.status}")
                        return None

                    data = await response.json()

                    if not data:
                        return None

                    # Get latest value
                    latest = data[-1] if isinstance(data, list) else data

                    return OnChainMetric(
                        asset=asset,
                        metric_name=metric,
                        value=latest.get("v", 0),
                        unit="count" if "count" in metric else "value",
                        timestamp=datetime.fromisoformat(
                            latest.get("t", "").replace("Z", "+00:00")
                        ) if latest.get("t") else datetime.utcnow(),
                        metadata={"raw": latest},
                    )

        except Exception as e:
            logger.error(f"Error fetching Glassnode metric {metric}: {e}")
            return None

    async def get_metrics(self, metrics: List[str], asset: str = "BTC") -> List[OnChainMetric]:
        """Fetch multiple metrics concurrently."""
        tasks = [self.get_metric(metric, asset) for metric in metrics]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


class MockOnChainSource(OnChainSource):
    """Mock on-chain source for testing/fallback."""

    def __init__(self):
        self.mock_metrics = {
            "active_addresses": {"BTC": 950000, "ETH": 450000},
            "exchange_balance": {"BTC": 2350000, "ETH": 18000000},
            "whale_balance": {"BTC": 8500000, "ETH": 45000000},
            "mvrv": {"BTC": 2.1, "ETH": 1.8},
            "nvt": {"BTC": 65, "ETH": 45},
            "sopr": {"BTC": 1.02, "ETH": 0.98},
        }

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        """Generate mock on-chain metric."""
        await asyncio.sleep(0.01)  # Simulate network delay

        if metric not in self.mock_metrics:
            return None

        value = self.mock_metrics[metric].get(asset.upper(), 0)

        return OnChainMetric(
            asset=asset,
            metric_name=metric,
            value=value,
            unit="count" if "count" in metric or "addresses" in metric else "value",
            timestamp=datetime.utcnow(),
            change_24h=0.5 if metric in ["active_addresses", "mvrv"] else -0.3,
            change_7d=2.1 if metric in ["active_addresses"] else 1.5,
            metadata={"mock": True},
        )


async def fetch_onchain_metrics(
    metrics: Optional[List[str]] = None,
    assets: Optional[List[str]] = None,
    fallback_to_mock: bool = True
) -> List[OnChainMetric]:
    """
    Fetch on-chain metrics for specified assets.

    Args:
        metrics: List of metrics to fetch (active_addresses, exchange_balance, etc.)
        assets: List of assets (BTC, ETH, SOL)
        fallback_to_mock: Use mock data if API unavailable

    Returns:
        List of OnChainMetric objects.
    """
    metrics = metrics or ["active_addresses", "exchange_balance", "mvrv", "sopr"]
    assets = assets or ["BTC", "ETH"]

    all_metrics: List[OnChainMetric] = []

    # Try Glassnode first
    source = GlassnodeSource()
    if source.api_key:
        for asset in assets:
            asset_metrics = await source.get_metrics(metrics, asset)
            all_metrics.extend(asset_metrics)

    # Fallback to mock
    if not all_metrics and fallback_to_mock:
        logger.info("No on-chain data from Glassnode, using mock data")
        mock_source = MockOnChainSource()
        for asset in assets:
            for metric in metrics:
                result = await mock_source.get_metric(metric, asset)
                if result:
                    all_metrics.append(result)

    return all_metrics


def analyze_onchain_signals(metrics: List[OnChainMetric]) -> Dict[str, Any]:
    """
    Analyze on-chain metrics for trading signals.

    Returns:
        Dict with signals, confidence, and interpretation.
    """
    signals = {
        "overall_sentiment": 0.0,
        "confidence": 0.5,
        "signals": [],
        "interpretation": "",
    }

    for metric in metrics:
        metric_name = metric.metric_name
        value = metric.value
        change_24h = metric.change_24h

        # Active addresses increasing = bullish
        if metric_name == "active_addresses":
            if change_24h > 0:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bullish",
                    "strength": min(abs(change_24h) / 5, 1.0),
                })
            else:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bearish",
                    "strength": min(abs(change_24h) / 5, 1.0),
                })

        # Exchange balance decreasing = bullish (supply shock)
        elif metric_name == "exchange_balance":
            if change_24h < 0:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bullish",
                    "strength": min(abs(change_24h) / 3, 1.0),
                })
            else:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bearish",
                    "strength": min(change_24h / 3, 1.0),
                })

        # MVRV > 3 = overvalued, < 1 = undervalued
        elif metric_name == "mvrv":
            if value > 3:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bearish",
                    "strength": (value - 3) / 2,
                })
            elif value < 1:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bullish",
                    "strength": (1 - value) / 1,
                })

        # SOPR > 1 = profit taking, < 1 = loss taking
        elif metric_name == "sopr":
            if value > 1.05:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bearish",
                    "strength": (value - 1) / 0.1,
                })
            elif value < 0.95:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bullish",
                    "strength": (1 - value) / 0.1,
                })

    # Calculate overall sentiment
    if signals["signals"]:
        bullish_strength = sum(s["strength"] for s in signals["signals"] if s["signal"] == "bullish")
        bearish_strength = sum(s["strength"] for s in signals["signals"] if s["signal"] == "bearish")
        total_strength = bullish_strength + bearish_strength

        if total_strength > 0:
            signals["overall_sentiment"] = (bullish_strength - bearish_strength) / total_strength
            signals["confidence"] = min(total_strength / len(signals["signals"]), 1.0)

    # Generate interpretation
    signals["interpretation"] = _generate_interpretation(signals)

    return signals


def _generate_interpretation(signals: Dict) -> str:
    """Generate human-readable interpretation of signals."""
    if not signals["signals"]:
        return "No significant on-chain signals detected."

    overall = signals["overall_sentiment"]
    confidence = signals["confidence"]

    if overall > 0.5:
        sentiment_text = "bullish"
    elif overall < -0.5:
        sentiment_text = "bearish"
    else:
        sentiment_text = "neutral"

    signal_count = len(signals["signals"])
    bullish_count = sum(1 for s in signals["signals"] if s["signal"] == "bullish")
    bearish_count = signal_count - bullish_count

    return (
        f"On-chain analysis shows {sentiment_text} sentiment "
        f"({bullish_count} bullish vs {bearish_count} bearish signals) "
        f"with {confidence:.0%} confidence."
    )