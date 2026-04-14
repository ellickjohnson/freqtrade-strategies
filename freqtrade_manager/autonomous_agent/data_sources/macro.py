"""
Macro economic data sources for research agent.

Provides macro indicators from FRED and other sources with graceful
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
class MacroIndicator:
    """Represents a macro economic indicator."""
    name: str
    value: float
    unit: str
    timestamp: datetime
    change_1m: float = 0.0
    change_3m: float = 0.0
    change_12m: float = 0.0
    interpretation: str = ""
    metadata: Dict = field(default_factory=dict)


class MacroSource:
    """Base class for macro data sources."""

    async def get_indicator(self, indicator: str) -> Optional[MacroIndicator]:
        """Fetch a single indicator. Override in subclasses."""
        raise NotImplementedError


class FREDSource(MacroSource):
    """
    Federal Reserve Economic Data (FRED) source.

    Requires FRED_API_KEY environment variable.
    Free API with extensive economic data.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"

        # Common indicator series IDs
        self.series_ids = {
            "dxy": "DTWEXBGS",  # Trade Weighted U.S. Dollar Index
            "vix": "VIXCLS",  # CBOE Volatility Index
            "treasury_10y": "GS10",  # 10-Year Treasury Yield
            "treasury_2y": "GS2",  # 2-Year Treasury Yield
            "fed_funds_rate": "FEDFUNDS",  # Federal Funds Rate
            "unemployment": "UNRATE",  # Unemployment Rate
            "cpi": "CPIAUCSL",  # Consumer Price Index
            "m2_money_supply": "M2SL",  # M2 Money Stock
            "gdp": "GDP",  # Gross Domestic Product
        }

    async def get_indicator(self, indicator: str) -> Optional[MacroIndicator]:
        """Fetch a macro indicator from FRED."""
        if not self.api_key:
            logger.debug("FRED API key not configured")
            return None

        series_id = self.series_ids.get(indicator)
        if not series_id:
            logger.warning(f"Unknown FRED indicator: {indicator}")
            return None

        try:
            # Get last 12 months of data
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow() - timedelta(days=400)).strftime("%Y-%m-%d")

            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start_date,
                "observation_end": end_date,
                "sort_order": "desc",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"FRED API error: {response.status}")
                        return None

                    data = await response.json()
                    observations = data.get("observations", [])

                    if len(observations) < 2:
                        return None

                    # Get latest and historical values
                    latest = observations[0]
                    latest_value = float(latest.get("value", 0))

                    # Calculate changes
                    change_1m = self._calc_change(observations, 1)
                    change_3m = self._calc_change(observations, 3)
                    change_12m = self._calc_change(observations, 12)

                    return MacroIndicator(
                        name=indicator,
                        value=latest_value,
                        unit=self._get_unit(indicator),
                        timestamp=datetime.fromisoformat(
                            latest.get("date", "").replace("Z", "+00:00")
                        ) if latest.get("date") else datetime.utcnow(),
                        change_1m=change_1m,
                        change_3m=change_3m,
                        change_12m=change_12m,
                        interpretation=self._interpret_indicator(indicator, latest_value, change_3m),
                        metadata={"series_id": series_id},
                    )

        except Exception as e:
            logger.error(f"Error fetching FRED indicator {indicator}: {e}")
            return None

    def _calc_change(self, observations: List[Dict], months: int) -> float:
        """Calculate percentage change over N months."""
        if len(observations) < months * 30:
            return 0.0

        try:
            latest = float(observations[0].get("value", 0))
            past = float(observations[min(months * 30, len(observations) - 1)].get("value", 0))

            if past == 0:
                return 0.0

            return ((latest - past) / past) * 100
        except (ValueError, IndexError):
            return 0.0

    def _get_unit(self, indicator: str) -> str:
        """Get unit for indicator."""
        units = {
            "dxy": "index",
            "vix": "index",
            "treasury_10y": "%",
            "treasury_2y": "%",
            "fed_funds_rate": "%",
            "unemployment": "%",
            "cpi": "index",
            "m2_money_supply": "billions USD",
            "gdp": "billions USD",
        }
        return units.get(indicator, "value")

    def _interpret_indicator(self, indicator: str, value: float, change_3m: float) -> str:
        """Generate interpretation for indicator."""
        interpretations = {
            "vix": f"VIX at {value:.1f} indicates {'high' if value > 25 else 'low'} volatility expectations.",
            "dxy": f"Dollar Index at {value:.1f}, {'strengthening' if change_3m > 0 else 'weakening'} over 3 months.",
            "treasury_10y": f"10Y yield at {value:.2f}%, {'rising' if change_3m > 0 else 'falling'} rates.",
            "fed_funds_rate": f"Federal funds rate at {value:.2f}%, {'tightening' if change_3m > 0 else 'easing'} policy.",
            "unemployment": f"Unemployment at {value:.1f}%, {'improving' if change_3m < 0 else 'deteriorating'} labor market.",
            "cpi": f"CPI at {value:.1f}, inflation {'rising' if change_3m > 0 else 'falling'}.",
        }
        return interpretations.get(indicator, f"{indicator} at {value:.2f}")

    async def get_indicators(self, indicators: Optional[List[str]] = None) -> List[MacroIndicator]:
        """Fetch multiple indicators concurrently."""
        indicators = indicators or ["dxy", "vix", "treasury_10y", "fed_funds_rate", "unemployment"]

        tasks = [self.get_indicator(ind) for ind in indicators]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


class MockMacroSource(MacroSource):
    """Mock macro source for testing/fallback."""

    def __init__(self):
        self.mock_values = {
            "dxy": {"value": 104.5, "change_1m": 0.8, "change_3m": 2.1},
            "vix": {"value": 18.5, "change_1m": -5.2, "change_3m": -8.3},
            "treasury_10y": {"value": 4.25, "change_1m": 0.15, "change_3m": 0.45},
            "treasury_2y": {"value": 4.65, "change_1m": 0.10, "change_3m": 0.35},
            "fed_funds_rate": {"value": 5.25, "change_1m": 0.0, "change_3m": 0.25},
            "unemployment": {"value": 3.8, "change_1m": -0.1, "change_3m": -0.2},
            "cpi": {"value": 3.2, "change_1m": 0.1, "change_3m": 0.3},
            "m2_money_supply": {"value": 20800, "change_1m": -0.5, "change_3m": -1.2},
            "gdp": {"value": 27500, "change_1m": 0.4, "change_3m": 1.8},
        }

    async def get_indicator(self, indicator: str) -> Optional[MacroIndicator]:
        """Generate mock macro indicator."""
        await asyncio.sleep(0.01)  # Simulate network delay

        if indicator not in self.mock_values:
            return None

        data = self.mock_values[indicator]

        return MacroIndicator(
            name=indicator,
            value=data["value"],
            unit="index" if indicator in ["dxy", "vix"] else "%",
            timestamp=datetime.utcnow(),
            change_1m=data["change_1m"],
            change_3m=data["change_3m"],
            interpretation=f"Mock {indicator} data for testing.",
            metadata={"mock": True},
        )


async def fetch_macro_indicators(
    indicators: Optional[List[str]] = None,
    fallback_to_mock: bool = True
) -> List[MacroIndicator]:
    """
    Fetch macro economic indicators.

    Args:
        indicators: List of indicators to fetch (dxy, vix, treasury_10y, etc.)
        fallback_to_mock: Use mock data if API unavailable

    Returns:
        List of MacroIndicator objects.
    """
    indicators = indicators or ["dxy", "vix", "treasury_10y", "fed_funds_rate", "unemployment"]

    all_indicators: List[MacroIndicator] = []

    # Try FRED first
    source = FREDSource()
    if source.api_key:
        all_indicators = await source.get_indicators(indicators)

    # Fallback to mock
    if not all_indicators and fallback_to_mock:
        logger.info("No macro data from FRED, using mock data")
        mock_source = MockMacroSource()
        for indicator in indicators:
            result = await mock_source.get_indicator(indicator)
            if result:
                all_indicators.append(result)

    return all_indicators


def analyze_macro_environment(indicators: List[MacroIndicator]) -> Dict[str, Any]:
    """
    Analyze macro environment for crypto implications.

    Returns:
        Dict with overall assessment, risk factors, and opportunities.
    """
    analysis = {
        "overall_assessment": "neutral",
        "risk_level": "moderate",
        "risk_factors": [],
        "opportunities": [],
        "crypto_implications": "",
        "confidence": 0.5,
    }

    indicator_map = {ind.name: ind for ind in indicators}

    # Analyze VIX (volatility)
    if "vix" in indicator_map:
        vix = indicator_map["vix"].value
        if vix > 30:
            analysis["risk_factors"].append("High market volatility (VIX > 30)")
            analysis["risk_level"] = "high"
        elif vix > 20:
            analysis["risk_factors"].append("Elevated volatility (VIX > 20)")
        else:
            analysis["opportunities"].append("Low volatility environment (VIX < 20)")

    # Analyze dollar strength
    if "dxy" in indicator_map:
        dxy = indicator_map["dxy"]
        if dxy.change_3m > 5:
            analysis["risk_factors"].append("Strong dollar pressure on risk assets")
        elif dxy.change_3m < -3:
            analysis["opportunities"].append("Weak dollar supportive for crypto")

    # Analyze interest rates
    if "treasury_10y" in indicator_map:
        treasury_10y = indicator_map["treasury_10y"]
        if treasury_10y.value > 4.5:
            analysis["risk_factors"].append("High yields competing with crypto yields")
        if treasury_10y.change_3m > 0.5:
            analysis["risk_factors"].append("Rising yields tightening financial conditions")

    # Analyze fed funds rate
    if "fed_funds_rate" in indicator_map:
        fed_funds = indicator_map["fed_funds_rate"]
        if fed_funds.value > 5:
            analysis["risk_factors"].append("Restrictive monetary policy")
        if fed_funds.change_3m < -0.5:
            analysis["opportunities"].append("Rate cuts potentially supportive for risk assets")

    # Generate overall assessment
    risk_count = len(analysis["risk_factors"])
    opp_count = len(analysis["opportunities"])

    if risk_count > opp_count + 1:
        analysis["overall_assessment"] = "bearish"
        analysis["confidence"] = 0.6 + (risk_count - opp_count) * 0.05
    elif opp_count > risk_count + 1:
        analysis["overall_assessment"] = "bullish"
        analysis["confidence"] = 0.6 + (opp_count - risk_count) * 0.05
    else:
        analysis["overall_assessment"] = "neutral"
        analysis["confidence"] = 0.5

    analysis["confidence"] = min(analysis["confidence"], 0.85)

    # Generate crypto implications
    analysis["crypto_implications"] = _generate_crypto_implications(analysis)

    return analysis


def _generate_crypto_implications(analysis: Dict) -> str:
    """Generate implications for crypto markets."""
    assessment = analysis["overall_assessment"]
    risk_level = analysis["risk_level"]

    if assessment == "bearish":
        return (
            f"Macro environment shows {risk_level} risk for crypto. "
            f"Consider reducing exposure or waiting for better entry points. "
            f"Risk factors: {', '.join(analysis['risk_factors'][:2])}."
        )
    elif assessment == "bullish":
        return (
            f"Macro environment is supportive for crypto. "
            f"Opportunities: {', '.join(analysis['opportunities'][:2])}. "
            f"Monitor for potential trend continuation."
        )
    else:
        return (
            f"Macro environment is mixed with no strong directional bias. "
            f"Continue with strategy-specific signals while monitoring "
            f"risk factors: {', '.join(analysis['risk_factors'][:2])}."
        )