"""
Technical Indicators - Market regime detection using technical analysis.

Calculates ADX, ATR, RSI, EMA, MACD, Bollinger Bands, and other indicators
for use in market regime detection.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Container for calculated technical indicators."""
    # Trend strength
    adx: float = 0.0  # Average Directional Index (0-100, >25 = trending)
    adx_direction: str = "neutral"  # bullish, bearish, neutral

    # Volatility
    atr: float = 0.0  # Average True Range
    atr_percent: float = 0.0  # ATR as percentage of price
    bollinger_bandwidth: float = 0.0  # Bollinger bandwidth (volatility)

    # Momentum
    rsi: float = 50.0  # Relative Strength Index (0-100)
    rsi_zone: str = "neutral"  # overbought, oversold, neutral
    macd: float = 0.0  # MACD line
    macd_signal: float = 0.0  # Signal line
    macd_histogram: float = 0.0  # MACD histogram

    # Trend direction
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    ema_trend: str = "neutral"  # bullish, bearish, neutral
    price_vs_ema: Dict[str, str] = field(default_factory=dict)  # above/below for each EMA

    # Position
    bollinger_position: float = 0.0  # Position within Bollinger bands (0-1)
    price_percent_from_high: float = 0.0  # % from 52-week high
    price_percent_from_low: float = 0.0  # % from 52-week low

    # Volume
    volume_trend: float = 0.0  # Volume trend (+/-)
    volume_vs_avg: float = 1.0  # Volume vs average

    # Overall
    trend_strength: float = 0.0  # Combined trend strength (0-100)
    volatility_regime: str = "normal"  # low, normal, high
    momentum_regime: str = "neutral"  # bullish, bearish, neutral


class TechnicalAnalyzer:
    """
    Calculate technical indicators for market regime detection.

    Uses OHLCV data to calculate trend, volatility, and momentum indicators
    that help identify market regime (trending_up, trending_down, ranging, volatile).
    """

    def __init__(self):
        self.lookback_periods = {
            "short": 14,
            "medium": 50,
            "long": 200,
        }

    def calculate_indicators(
        self,
        ohlcv: np.ndarray,
        pair: str = "BTC/USDT"
    ) -> TechnicalIndicators:
        """
        Calculate all technical indicators from OHLCV data.

        Args:
            ohlcv: numpy array with shape (n, 5) containing [open, high, low, close, volume]
            pair: Trading pair for logging

        Returns:
            TechnicalIndicators object with all calculated values.
        """
        if len(ohlcv) < 200:
            logger.warning(f"Insufficient data for {pair}: {len(ohlcv)} candles (need 200)")
            return self._calculate_with_available_data(ohlcv)

        try:
            # Extract OHLCV columns
            open_prices = ohlcv[:, 0]
            high_prices = ohlcv[:, 1]
            low_prices = ohlcv[:, 2]
            close_prices = ohlcv[:, 3]
            volumes = ohlcv[:, 4]

            indicators = TechnicalIndicators()

            # Calculate trend strength (ADX)
            adx, plus_di, minus_di = self._calculate_adx(high_prices, low_prices, close_prices, 14)
            indicators.adx = adx
            indicators.adx_direction = "bullish" if plus_di > minus_di else ("bearish" if minus_di > plus_di else "neutral")

            # Calculate volatility (ATR)
            atr = self._calculate_atr(high_prices, low_prices, close_prices, 14)
            indicators.atr = atr
            indicators.atr_percent = (atr / close_prices[-1]) * 100

            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger(close_prices, 20, 2)
            indicators.bollinger_bandwidth = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            indicators.bollinger_position = (close_prices[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1])

            # Calculate RSI
            rsi = self._calculate_rsi(close_prices, 14)
            indicators.rsi = rsi
            indicators.rsi_zone = "overbought" if rsi > 70 else ("oversold" if rsi < 30 else "neutral")

            # Calculate MACD
            macd, signal, histogram = self._calculate_macd(close_prices)
            indicators.macd = macd[-1]
            indicators.macd_signal = signal[-1]
            indicators.macd_histogram = histogram[-1]

            # Calculate EMAs
            ema_20 = self._calculate_ema(close_prices, 20)
            ema_50 = self._calculate_ema(close_prices, 50)
            ema_200 = self._calculate_ema(close_prices, 200)

            indicators.ema_20 = ema_20[-1]
            indicators.ema_50 = ema_50[-1]
            indicators.ema_200 = ema_200[-1]

            # EMA trend
            if ema_20[-1] > ema_50[-1] > ema_200[-1]:
                indicators.ema_trend = "bullish"
            elif ema_20[-1] < ema_50[-1] < ema_200[-1]:
                indicators.ema_trend = "bearish"
            else:
                indicators.ema_trend = "neutral"

            # Price vs EMAs
            indicators.price_vs_ema = {
                "ema_20": "above" if close_prices[-1] > ema_20[-1] else "below",
                "ema_50": "above" if close_prices[-1] > ema_50[-1] else "below",
                "ema_200": "above" if close_prices[-1] > ema_200[-1] else "below",
            }

            # Distance from high/low
            period_high = np.max(close_prices[-252:]) if len(close_prices) >= 252 else np.max(close_prices)
            period_low = np.min(close_prices[-252:]) if len(close_prices) >= 252 else np.min(close_prices)
            indicators.price_percent_from_high = ((period_high - close_prices[-1]) / period_high) * 100
            indicators.price_percent_from_low = ((close_prices[-1] - period_low) / period_low) * 100

            # Volume analysis
            avg_volume = np.mean(volumes[-20:])
            indicators.volume_vs_avg = volumes[-1] / avg_volume if avg_volume > 0 else 1.0

            volume_ma = np.mean(volumes[-50:])
            volume_ma_prev = np.mean(volumes[-100:-50])
            indicators.volume_trend = (volume_ma - volume_ma_prev) / volume_ma_prev if volume_ma_prev > 0 else 0.0

            # Calculate overall metrics
            indicators = self._calculate_overall_metrics(indicators, close_prices)

            return indicators

        except Exception as e:
            logger.error(f"Error calculating indicators for {pair}: {e}")
            return TechnicalIndicators()

    def _calculate_with_available_data(self, ohlcv: np.ndarray) -> TechnicalIndicators:
        """Calculate indicators with whatever data is available."""
        indicators = TechnicalIndicators()
        n = len(ohlcv)

        if n < 14:
            return indicators

        close_prices = ohlcv[:, 3]
        high_prices = ohlcv[:, 1]
        low_prices = ohlcv[:, 2]

        # Calculate what we can
        if n >= 14:
            indicators.rsi = self._calculate_rsi(close_prices, min(14, n - 1))
            indicators.atr = self._calculate_atr(high_prices, low_prices, close_prices, min(14, n - 1))
            indicators.adx, _, _ = self._calculate_adx(high_prices, low_prices, close_prices, min(14, n - 1))

        if n >= 20:
            indicators.ema_20 = self._calculate_ema(close_prices, 20)[-1]

        return indicators

    def _calculate_adx(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> Tuple[float, float, float]:
        """
        Calculate Average Directional Index.

        Returns:
            Tuple of (ADX, +DI, -DI)
        """
        n = len(close)
        if n < period * 2:
            return 25.0, 25.0, 25.0

        # Calculate true range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )

        # Calculate directional movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        # Smooth with EMA
        atr = self._smooth(tr, period)
        plus_di = 100 * self._smooth(plus_dm, period) / atr
        minus_di = 100 * self._smooth(minus_dm, period) / atr

        # Calculate DX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)

        # Smooth DX to get ADX
        adx = self._smooth(dx, period)

        return float(adx[-1]), float(plus_di[-1]), float(minus_di[-1])

    def _calculate_atr(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> float:
        """Calculate Average True Range."""
        n = len(close)
        if n < period + 1:
            return 0.0

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )

        atr = self._smooth(tr, period)
        return float(atr[-1])

    def _calculate_rsi(self, close: np.ndarray, period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        n = len(close)
        if n < period + 1:
            return 50.0

        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = self._smooth(gains, period)
        avg_loss = self._smooth(losses, period)

        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        return float(np.clip(rsi[-1], 0, 100))

    def _calculate_macd(
        self,
        close: np.ndarray,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate MACD, Signal, and Histogram."""
        ema_fast = self._calculate_ema(close, fast_period)
        ema_slow = self._calculate_ema(close, slow_period)

        macd = ema_fast - ema_slow
        signal = self._calculate_ema(macd, signal_period)
        histogram = macd - signal

        return macd, signal, histogram

    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        multiplier = 2.0 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1]

        return ema

    def _calculate_bollinger(
        self,
        close: np.ndarray,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate Bollinger Bands."""
        n = len(close)
        middle = np.zeros(n)
        upper = np.zeros(n)
        lower = np.zeros(n)

        for i in range(period - 1, n):
            window = close[i - period + 1:i + 1]
            middle[i] = np.mean(window)
            std = np.std(window)
            upper[i] = middle[i] + std_dev * std
            lower[i] = middle[i] - std_dev * std

        # Fill initial values
        middle[:period - 1] = close[:period - 1]
        upper[:period - 1] = close[:period - 1]
        lower[:period - 1] = close[:period - 1]

        return upper, middle, lower

    def _smooth(self, data: np.ndarray, period: int) -> np.ndarray:
        """Smooth data using Wilder's smoothing (similar to EMA)."""
        smoothed = np.zeros_like(data, dtype=float)
        smoothed[0] = data[0]

        alpha = 1.0 / period

        for i in range(1, len(data)):
            smoothed[i] = alpha * data[i] + (1 - alpha) * smoothed[i - 1]

        return smoothed

    def _calculate_overall_metrics(
        self,
        indicators: TechnicalIndicators,
        close_prices: np.ndarray
    ) -> TechnicalIndicators:
        """Calculate overall trend strength and regime classifications."""

        # Trend strength (0-100)
        trend_score = 0.0

        # ADX contribution (0-25)
        if indicators.adx > 25:
            trend_score += min(indicators.adx, 50) * 0.5

        # EMA alignment (0-25)
        if indicators.ema_trend == "bullish":
            trend_score += 25
        elif indicators.ema_trend == "bearish":
            trend_score += 25
        elif indicators.ema_trend == "neutral":
            trend_score += 12.5

        # Price position (0-25)
        if indicators.price_vs_ema.get("ema_200") == "above":
            trend_score += 25

        # MACD contribution (0-25)
        if indicators.macd_histogram > 0:
            trend_score += 12.5
        elif indicators.macd_histogram < 0:
            trend_score += 12.5

        indicators.trend_strength = min(trend_score, 100)

        # Volatility regime
        if indicators.atr_percent > 5:
            indicators.volatility_regime = "high"
        elif indicators.atr_percent < 2:
            indicators.volatility_regime = "low"
        else:
            indicators.volatility_regime = "normal"

        # Momentum regime
        if indicators.rsi > 70 and indicators.macd_histogram > 0:
            indicators.momentum_regime = "bullish"
        elif indicators.rsi < 30 and indicators.macd_histogram < 0:
            indicators.momentum_regime = "bearish"
        elif indicators.macd_histogram > 0:
            indicators.momentum_regime = "bullish"
        elif indicators.macd_histogram < 0:
            indicators.momentum_regime = "bearish"
        else:
            indicators.momentum_regime = "neutral"

        return indicators

    def detect_regime(self, indicators: TechnicalIndicators) -> Dict[str, any]:
        """
        Detect market regime from technical indicators.

        Returns:
            Dict with regime_type, confidence, and characteristics.
        """
        regime = {
            "regime_type": "ranging",
            "confidence": 0.5,
            "characteristics": {},
            "affected_strategies": [],
            "recommendations": [],
        }

        # Trending market
        if indicators.adx > 25:
            regime["regime_type"] = "trending_up" if indicators.adx_direction == "bullish" else "trending_down"
            regime["confidence"] = min(indicators.adx / 100 + 0.3, 0.9)
            regime["characteristics"]["trend_strength"] = indicators.adx
            regime["characteristics"]["direction"] = indicators.adx_direction

            if indicators.ema_trend == "bullish":
                regime["affected_strategies"] = ["trend_following", "momentum"]
                regime["recommendations"].append("Trend-following strategies should perform well")
            else:
                regime["affected_strategies"] = ["short", "hedged"]
                regime["recommendations"].append("Consider defensive positioning")

        # Volatile market
        elif indicators.atr_percent > 4:
            regime["regime_type"] = "volatile"
            regime["confidence"] = min(indicators.atr_percent / 10, 0.85)
            regime["characteristics"]["volatility"] = indicators.atr_percent
            regime["characteristics"]["atr"] = indicators.atr

            regime["affected_strategies"] = ["scalping", "range_trading"]
            regime["recommendations"].append("High volatility - use wider stops")

        # Ranging market
        else:
            regime["regime_type"] = "ranging"
            regime["confidence"] = 0.6 + (25 - indicators.adx) / 100
            regime["characteristics"]["range_bounds"] = {
                "support": indicators.ema_200 * 0.95,
                "resistance": indicators.ema_200 * 1.05,
            }

            regime["affected_strategies"] = ["mean_reversion", "oscillator"]
            regime["recommendations"].append("Mean reversion strategies should perform well")

        # Add momentum context
        regime["characteristics"]["momentum"] = indicators.momentum_regime
        regime["characteristics"]["rsi"] = indicators.rsi
        regime["characteristics"]["volume_trend"] = indicators.volume_trend

        return regime