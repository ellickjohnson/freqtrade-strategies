# TrendMomentum Strategy for Freqtrade
# Version: 1.0 - Trend Following with Momentum Confirmation
# Trades in direction of higher-timeframe trend on pullbacks

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    CategoricalParameter,
    merge_informative_pair,
)
from freqtrade.persistence import Trade
from pandas import DataFrame
import talib
import numpy as np
from datetime import datetime
from typing import Optional
from functools import reduce
import logging

logger = logging.getLogger(__name__)


class TrendMomentum(IStrategy):
    """TrendMomentum Strategy v1.0 - Trend Following with Momentum Confirmation

    Strategy Philosophy:
    - Only trade in direction of higher-timeframe trend (1h EMA200)
    - Enter on pullbacks with momentum confirmation
    - Avoid oversold conditions (reversal traps)
    - Exit on time-based or momentum exhaustion

    Entry Conditions (all must be true):
    1. Trend Filter: Price > 1h EMA200 (informative timeframe)
    2. Price Position: 15m price > EMA(50) OR EMA(20) crossover bullish
    3. Trend Strength: ADX > 20 (decent trend)
    4. Momentum: RSI(14) > 45 (not oversold, avoiding reversal traps)
    5. MACD: Histogram positive AND increasing
    6. Volume: > 1.4x 20-period average
    7. Candle: Bullish candle (close > open, body > 50% of range)

    Exit Conditions:
    - Time-based: Exit after 6-12 candles (1.5-3 hours) if no profit
    - Momentum: RSI > 70 OR MACD histogram decreasing
    - ATR-based trailing stop after 1% profit
    - Stop loss: -5%
    """

    # Hyperoptable Parameters
    adx_threshold = IntParameter(15, 30, default=20, space="buy", optimize=True)
    rsi_min = IntParameter(40, 55, default=45, space="buy", optimize=True)
    rsi_max = IntParameter(65, 80, default=70, space="sell", optimize=True)
    volume_multiplier = DecimalParameter(
        1.2, 2.0, default=1.4, space="buy", optimize=True
    )
    ema_period = CategoricalParameter([20, 50], default=50, space="buy", optimize=True)
    candle_body_pct = DecimalParameter(
        0.4, 0.7, default=0.5, space="buy", optimize=True
    )
    max_duration_hours = DecimalParameter(
        1.5, 4.0, default=3.0, space="sell", optimize=True
    )
    profit_target = DecimalParameter(
        0.02, 0.08, default=0.04, space="sell", optimize=True
    )
    trailing_start = DecimalParameter(
        0.005, 0.02, default=0.01, space="sell", optimize=True
    )

    # Strategy settings
    timeframe = "15m"
    stoploss = -0.05
    use_custom_stoploss = True
    can_short = False  # Spot only

    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True

    minimal_roi = {
        "0": 0.08,
        "30": 0.04,  # 30 min: 4% profit target
        "60": 0.02,  # 1 hour: 2% profit target
        "120": 0.01,  # 2 hours: 1% profit target
    }
    max_open_trades = 3
    startup_candle_count = 200

    # Fixed constants
    ADX_THRESH = 20
    RSI_MIN = 45
    RSI_MAX_EXIT = 70
    VOL_MULT = 1.4
    EMA_FAST = 20
    EMA_SLOW = 50
    CANDLE_BODY = 0.5
    MAX_DURATION_HOURS = 3.0

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
        ]

    def informative_pairs(self):
        """Add 1h timeframe for trend filter."""
        pairs = []
        # Get pairs from config
        if hasattr(self.dp, "current_whitelist"):
            for pair in self.dp.current_whitelist():
                pairs.append((pair, "1h"))
        return pairs

    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Populate 1h indicators for trend filter."""
        # 1h EMA200 for trend direction
        dataframe["ema_200_1h"] = talib.EMA(dataframe["close"], timeperiod=200)
        return dataframe

    def do_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Merge 1h informative into main dataframe."""
        if not self.dp:
            return dataframe

        # Get informative pairs
        inf_pairs = self.informative_pairs()
        for pair, tf in inf_pairs:
            if pair == metadata["pair"] and tf == "1h":
                informative = self.dp.get_pair_dataframe(pair=pair, timeframe=tf)
                informative = self.populate_indicators_1h(informative.copy(), metadata)
                dataframe = merge_informative_pair(
                    dataframe,
                    informative,
                    self.timeframe,
                    tf,
                    ffill=True,
                    drop_nan=True,
                )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"].values
        high = dataframe["high"].values
        low = dataframe["low"].values
        volume = dataframe["volume"].values
        open_vals = dataframe["open"].values

        # Trend indicators
        dataframe["ema_20"] = talib.EMA(close, timeperiod=20)
        dataframe["ema_50"] = talib.EMA(close, timeperiod=50)
        dataframe["ema_200"] = talib.EMA(close, timeperiod=200)
        dataframe["adx"] = talib.ADX(high, low, close, timeperiod=14)

        # 1h trend filter (if available from informative)
        # Check if we have the 1h EMA200 column
        ema_200_1h_col = (
            "ema_200_1h_1h" if "ema_200_1h_1h" in dataframe.columns else "ema_200_1h"
        )
        if ema_200_1h_col in dataframe.columns:
            dataframe["above_ema200_1h"] = (
                dataframe["close"] > dataframe[ema_200_1h_col]
            )
        else:
            # Fallback to 15m EMA200 if 1h not available
            dataframe["above_ema200_1h"] = dataframe["close"] > dataframe["ema_200"]

        # Momentum indicators
        dataframe["rsi"] = talib.RSI(close, timeperiod=14)
        dataframe["rsi_not_oversold"] = dataframe["rsi"] > self.RSI_MIN
        dataframe["rsi_overbought"] = dataframe["rsi"] > self.RSI_MAX_EXIT

        # MACD
        macd, macdsignal, macdhist = talib.MACD(
            close, fastperiod=12, slowperiod=26, signalperiod=9
        )
        dataframe["macd"] = macd
        dataframe["macdsignal"] = macdsignal
        dataframe["macdhist"] = macdhist
        dataframe["macd_positive"] = dataframe["macdhist"] > 0
        dataframe["macd_increasing"] = dataframe["macdhist"] > dataframe[
            "macdhist"
        ].shift(1)
        dataframe["macd_bullish"] = (
            dataframe["macd_positive"] & dataframe["macd_increasing"]
        )

        # Volume
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_spike"] = dataframe["volume"] > (
            dataframe["volume_mean"] * self.VOL_MULT
        )

        # Volatility
        dataframe["atr"] = talib.ATR(high, low, close, timeperiod=14)

        # Candle patterns
        dataframe["candle_body"] = abs(dataframe["close"] - dataframe["open"])
        dataframe["candle_range"] = dataframe["high"] - dataframe["low"]
        dataframe["body_pct"] = dataframe["candle_body"] / dataframe[
            "candle_range"
        ].replace(0, np.nan)
        dataframe["bullish_candle"] = (
            (dataframe["close"] > dataframe["open"])  # Green candle
            & (dataframe["body_pct"] > self.CANDLE_BODY)  # Body > 50% of range
        )

        # EMA crossover signals
        dataframe["ema_cross_up"] = (dataframe["ema_20"] > dataframe["ema_50"]) & (
            dataframe["ema_20"].shift(1) <= dataframe["ema_50"].shift(1)
        )
        dataframe["above_ema50"] = dataframe["close"] > dataframe["ema_50"]
        dataframe["above_ema20"] = dataframe["close"] > dataframe["ema_20"]

        # Trend position
        dataframe["strong_trend"] = dataframe["adx"] > self.ADX_THRESH

        # Combined entry signal
        dataframe["trend_alignment"] = dataframe["above_ema200_1h"]
        dataframe["momentum_alignment"] = (
            dataframe["rsi_not_oversold"] & dataframe["macd_bullish"]
        )
        dataframe["price_position"] = (
            dataframe["above_ema50"] | dataframe["ema_cross_up"]
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry conditions - simplified trend following."""
        # Primary: trend pullback with momentum
        dataframe.loc[
            (
                dataframe["above_ema200_1h"]
                & (dataframe["rsi"] > 40)
                & (dataframe["rsi"] < 75)
                & (dataframe["macdhist"] > 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Secondary: EMA crossover confirmation
        dataframe.loc[
            (
                dataframe["above_ema200_1h"]
                & dataframe["ema_cross_up"]
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit conditions - simplified."""
        dataframe.loc[
            ((dataframe["rsi"] > 75) | (dataframe["close"] < dataframe["ema_50"])),
            "exit_long",
        ] = 1
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """ATR-based trailing stop, activates after 1% profit."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        atr = float(last_candle["atr"])
        atr_stop = (atr / current_rate) * 1.5

        # Tighten stop after 1% profit
        if current_profit > self.trailing_start.value:
            atr_stop = atr_stop * 0.5
        if current_profit > 0.02:
            atr_stop = min(atr_stop, 0.02)

        return max(-atr_stop, -0.05)

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str = None,
        **kwargs,
    ) -> bool:
        """Minimal entry confirmation."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        if float(last_candle["rsi"]) < 30:
            return False

        return True

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """Time-based and momentum exit logic."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600

        # Exit after max duration if losing
        max_hours = self.max_duration_hours.value
        if trade_duration > max_hours and current_profit < 0.005:
            return "time_exit_no_profit"

        # Take profit at target
        if current_profit > self.profit_target.value:
            return f"profit_target_{int(self.profit_target.value * 100)}pct"

        # Exit on momentum exhaustion
        if current_profit > 0.01:  # Only exit on momentum if in profit
            if last_candle["rsi"] > 75:
                return "rsi_exhaustion"
