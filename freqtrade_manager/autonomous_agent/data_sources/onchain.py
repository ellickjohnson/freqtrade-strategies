"""
On-chain data sources for research agent.

Provides on-chain metrics from free sources (Blockchain.com, Santiment, Mempool.space)
with graceful fallback to mock data when APIs are unavailable.
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


class BlockchainComSource(OnChainSource):
    """
    Blockchain.com Charts API - Free, no auth required.

    Provides BTC MVRV, NVT, unique addresses, exchange trade volume.
    BTC-only but covers the most critical metrics.
    """

    def __init__(self):
        self.base_url = "https://api.blockchain.info/charts"

        self.metric_endpoints = {
            "mvrv": ("mvrv", "ratio"),
            "nvt": ("nvt", "ratio"),
            "nvt_signal": ("nvts", "ratio"),
            "active_addresses": ("n-unique-addresses", "count"),
            "exchange_trade_volume": ("trade-volume", "btc"),
            "market_cap": ("market-cap", "usd"),
            "transaction_count": ("n-transactions", "count"),
            "hash_rate": ("hash-rate", "th/s"),
            "fees": ("fees-usd-per-transaction", "usd"),
        }

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        if asset.upper() != "BTC":
            return None  # Blockchain.com only supports BTC

        endpoint_info = self.metric_endpoints.get(metric)
        if not endpoint_info:
            return None

        endpoint, unit = endpoint_info

        try:
            params = {
                "format": "json",
                "timespan": "30days",
            }

            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/{endpoint}"
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.debug(f"Blockchain.com API error for {metric}: {response.status}")
                        return None

                    data = await response.json()

            values = data.get("values", [])
            if not values:
                return None

            latest = values[-1]
            previous = values[-2] if len(values) >= 2 else latest

            current_val = latest.get("y", 0)
            prev_val = previous.get("y", 0)
            change_24h = ((current_val - prev_val) / abs(prev_val) * 100) if prev_val != 0 else 0

            return OnChainMetric(
                asset=asset,
                metric_name=metric,
                value=current_val,
                unit=unit,
                timestamp=datetime.fromtimestamp(latest.get("x", 0) / 1000) if latest.get("x", 0) > 1e12 else datetime.utcnow(),
                change_24h=change_24h,
                metadata={"source": "blockchain.com"},
            )

        except Exception as e:
            logger.debug(f"Error fetching Blockchain.com metric {metric}: {e}")
            return None

    async def get_metrics(self, metrics: List[str], asset: str = "BTC") -> List[OnChainMetric]:
        tasks = [self.get_metric(m, asset) for m in metrics]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


class SantimentSource(OnChainSource):
    """
    Santiment SanAPI - Free tier: 1,000 calls/month, no auth required.

    Provides active addresses (real-time), exchange balance/flows (30-day lag),
    whale transaction count (30-day lag), MVRV, NVT.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SANTIMENT_API_KEY")
        self.base_url = "https://api.santiment.net/graphql"

        self.metric_queries = {
            "active_addresses": "daily_active_addresses",
            "exchange_balance": "exchange_balance",
            "exchange_inflow": "exchange_inflow",
            "exchange_outflow": "exchange_outflow",
            "whale_transaction_count": "transaction_volume",
            "mvrv": "mvrv",
            "nvt": "nvt",
            "social_volume": "social_volume_total",
            "dev_activity": "dev_activity",
        }

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        santiment_slug = self._asset_to_slug(asset)
        metric_field = self.metric_queries.get(metric)
        if not metric_field:
            return None

        query = f"""
        {{
          getMetric(metric: "{metric_field}") {{
            timeseriesData(
              slug: "{santiment_slug}"
              from: "{(datetime.utcnow() - timedelta(days=30)).isoformat()}"
              to: "{datetime.utcnow().isoformat()}"
              interval: "1d"
            ) {{
              datetime
              value
            }}
          }}
        }}
        """

        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Apikey {self.api_key}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    json={"query": query},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        logger.debug(f"Santiment API error for {metric}: {response.status}")
                        return None

                    data = await response.json()

            timeseries = data.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
            if not timeseries:
                return None

            # Get latest two points for 24h change
            latest = timeseries[-1]
            previous = timeseries[-2] if len(timeseries) >= 2 else latest

            current_val = latest.get("value", 0) or 0
            prev_val = previous.get("value", 0) or 0
            change_24h = ((current_val - prev_val) / abs(prev_val) * 100) if prev_val != 0 else 0

            return OnChainMetric(
                asset=asset,
                metric_name=metric,
                value=current_val,
                unit="count" if "address" in metric or "count" in metric else "value",
                timestamp=datetime.fromisoformat(latest["datetime"].replace("Z", "+00:00")) if latest.get("datetime") else datetime.utcnow(),
                change_24h=change_24h,
                metadata={"source": "santiment", "lag": "30d" if metric in ["exchange_balance", "exchange_inflow", "exchange_outflow", "whale_transaction_count", "mvrv", "nvt"] else "realtime"},
            )

        except Exception as e:
            logger.debug(f"Error fetching Santiment metric {metric}: {e}")
            return None

    def _asset_to_slug(self, asset: str) -> str:
        mapping = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binance-coin"}
        return mapping.get(asset.upper(), asset.lower())


class MempoolSpaceSource(OnChainSource):
    """
    Mempool.space API - Free, no auth required.

    Provides real-time Bitcoin mempool data, fee estimates, hash rate.
    Useful as sentiment proxy (high fees = high network usage = bullish signal).
    """

    def __init__(self):
        self.base_url = "https://mempool.space/api"

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        if asset.upper() != "BTC":
            return None

        try:
            async with aiohttp.ClientSession() as session:
                if metric == "mempool_fee_rate":
                    url = f"{self.base_url}/v1/fees/mempool"
                elif metric == "hash_rate":
                    url = f"{self.base_url}/v1/mining/hashrate"
                elif metric == "difficulty":
                    url = f"{self.base_url}/v1/mining/difficulty"
                elif metric == "mempool_size":
                    url = f"{self.base_url}/mempool"
                else:
                    return None

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()

            if metric == "mempool_fee_rate":
                value = data.get("fee_histogram", [{}])[0].get("feerate", 0) if isinstance(data, dict) else 0
            elif metric == "hash_rate":
                value = data.get("currentHashrate", 0) if isinstance(data, dict) else 0
            elif metric == "difficulty":
                value = data.get("currentDifficulty", 0) if isinstance(data, dict) else 0
            elif metric == "mempool_size":
                value = data.get("count", 0) if isinstance(data, dict) else 0
            else:
                return None

            return OnChainMetric(
                asset=asset,
                metric_name=metric,
                value=value,
                unit="sat/vb" if "fee" in metric else "eh/s" if "hash" in metric else "value",
                timestamp=datetime.utcnow(),
                metadata={"source": "mempool.space"},
            )

        except Exception as e:
            logger.debug(f"Error fetching Mempool.space metric {metric}: {e}")
            return None


class FreeOnChainSource(OnChainSource):
    """
    Combined free on-chain source.

    Tries Blockchain.com first (real-time BTC metrics),
    then Santiment (multi-asset with some 30d lag),
    then Mempool.space (mempool/fee data).
    Falls back to MockOnChainSource if all fail.
    """

    def __init__(self):
        self.blockchain_com = BlockchainComSource()
        self.santiment = SantimentSource()
        self.mempool_space = MempoolSpaceSource()

        # Which source handles which metric
        self.metric_routing = {
            "mvrv": ["blockchain_com", "santiment"],
            "nvt": ["blockchain_com", "santiment"],
            "nvt_signal": ["blockchain_com"],
            "active_addresses": ["blockchain_com", "santiment"],
            "exchange_balance": ["santiment", "blockchain_com"],
            "exchange_inflow": ["santiment"],
            "exchange_outflow": ["santiment"],
            "whale_transaction_count": ["santiment"],
            "social_volume": ["santiment"],
            "dev_activity": ["santiment"],
            "exchange_trade_volume": ["blockchain_com"],
            "transaction_count": ["blockchain_com"],
            "hash_rate": ["blockchain_com", "mempool_space"],
            "fees": ["blockchain_com"],
            "mempool_fee_rate": ["mempool_space"],
            "mempool_size": ["mempool_space"],
            "difficulty": ["mempool_space"],
        }

        self.sources = {
            "blockchain_com": self.blockchain_com,
            "santiment": self.santiment,
            "mempool_space": self.mempool_space,
        }

    async def get_metric(self, metric: str, asset: str = "BTC") -> Optional[OnChainMetric]:
        source_names = self.metric_routing.get(metric, ["blockchain_com", "santiment"])

        for source_name in source_names:
            source = self.sources[source_name]
            result = await source.get_metric(metric, asset)
            if result is not None:
                return result

        return None

    async def get_metrics(self, metrics: List[str], asset: str = "BTC") -> List[OnChainMetric]:
        tasks = [self.get_metric(m, asset) for m in metrics]
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
        await asyncio.sleep(0.01)

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

    Uses free data sources (Blockchain.com, Santiment, Mempool.space).
    Falls back to mock data if all sources fail.

    Args:
        metrics: List of metrics to fetch
        assets: List of assets (BTC, ETH, SOL)
        fallback_to_mock: Use mock data if all APIs fail

    Returns:
        List of OnChainMetric objects.
    """
    metrics = metrics or ["active_addresses", "exchange_balance", "mvrv", "nvt"]
    assets = assets or ["BTC", "ETH"]

    all_metrics: List[OnChainMetric] = []

    # Try free sources
    source = FreeOnChainSource()
    for asset in assets:
        asset_metrics = await source.get_metrics(metrics, asset)
        all_metrics.extend(asset_metrics)

    # Fallback to mock
    if not all_metrics and fallback_to_mock:
        logger.info("No on-chain data from free sources, using mock data")
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

        # NVT high = overvalued, low = undervalued
        elif metric_name == "nvt":
            if value > 90:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bearish",
                    "strength": (value - 90) / 50,
                })
            elif value < 40:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bullish",
                    "strength": (40 - value) / 30,
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

        # High mempool fees = high network usage (bullish proxy)
        elif metric_name == "mempool_fee_rate":
            if value > 50:
                signals["signals"].append({
                    "metric": metric_name,
                    "signal": "bullish",
                    "strength": min(value / 100, 1.0),
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