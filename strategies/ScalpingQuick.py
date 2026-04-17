# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
ScalpingQuick Strategy - High-frequency scalping for small frequent profits

Key features:
- 5-minute timeframe (faster than 15m OscillatorConfluence)
- Quick profit targets: 0.5-1.5% per trade
- Tight stoploss: -1.5% with trailing
- Aggressive entry on momentum signals
- Fast exit on profit taking or reversal
- Smaller position sizes, more trades
"""

import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import IStrategy
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ScalpingQuick(IStrategy):
    """
    ScalpingQuick - Aggressive scalping strategy for frequent small profits

    Entry conditions:
    - RSI crossing up through 40 (momentum building)
    - Price above EMA 9 (short-term trend)
    - MACD histogram turning positive
    - Volume spike (>1.5x average)

    Exit conditions:
    - Take profit at 0.8-1.5%
    - Stop loss at -1.5%
    - Trailing stop after 0.5% profit
    - RSI crossing down through 70
    """

    INTERFACE_VERSION = 3

    # Faster timeframe for scalping
    timeframe = "5m"

    can_short: bool = False

    # Quick profit targets
    minimal_roi = {
        "0": 0.02,
        "5": 0.012,
        "15": 0.007,
        "30": 0.003,
        "60": 0.001,
    }

    stoploss = -0.045

    trailing_stop = True
    trailing_stop_positive = 0.004
    trailing_stop_positive_offset = 0.006
    trailing_only_offset_is_reached = True

    # Only process new candles
    process_only_new_candles = True

    startup_candle_count = 50

    # Indicator settings
    rsi_period = 14
    rsi_entry_threshold = 45
    rsi_exit_threshold = 70

    ema_short = 9
    ema_medium = 21
    ema_long = 50

    volume_factor = 1.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all indicators needed for entry/exit signals."""

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period)
        dataframe["rsi_prev"] = dataframe["rsi"].shift(1)

        # EMAs for trend
        dataframe["ema_9"] = ta.EMA(dataframe, timeperiod=self.ema_short)
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=self.ema_medium)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=self.ema_long)

        # MACD for momentum
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        dataframe["macdhist_prev"] = dataframe["macdhist"].shift(1)

        # Bollinger Bands for volatility
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bollinger["lowerband"]
        dataframe["bb_middle"] = bollinger["middleband"]
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_width"] = (
            dataframe["bb_upper"] - dataframe["bb_lower"]
        ) / dataframe["bb_middle"]

        # Volume analysis
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean"]

        # Stochastic for overbought/oversold
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe["stoch_k"] = stoch["slowk"]
        dataframe["stoch_d"] = stoch["slowd"]

        # ATR for volatility measure
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Candle patterns
        dataframe["candle_body"] = abs(dataframe["close"] - dataframe["open"])
        dataframe["candle_range"] = dataframe["high"] - dataframe["low"]
        dataframe["bullish_candle"] = (dataframe["close"] > dataframe["open"]).astype(
            int
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Generate entry signals for scalping.
        """
        rsi_cross_up = (dataframe["rsi"] > self.rsi_entry_threshold) & (
            dataframe["rsi_prev"] <= self.rsi_entry_threshold
        )

        rsi_momentum = (
            (dataframe["rsi"] > 35)
            & (dataframe["rsi"] < 70)
            & (dataframe["macdhist"] > 0)
        )

        rsi_oversold_bounce = (
            (dataframe["rsi"] < 40)
            & (dataframe["close"] > dataframe["ema_9"])
            & (dataframe["macdhist"] > dataframe["macdhist_prev"])
        )

        macd_turning = (dataframe["macdhist"] > 0) | (
            (dataframe["macdhist"] > dataframe["macdhist_prev"])
            & (dataframe["macdhist_prev"] < 0)
        )

        ema_uptrend = (dataframe["close"] > dataframe["ema_9"]) | (
            dataframe["close"] > dataframe["ema_21"]
        )

        dataframe.loc[
            (
                (rsi_cross_up | rsi_momentum | rsi_oversold_bounce)
                & ema_uptrend
                & macd_turning
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        if "enter_long" not in dataframe.columns:
            dataframe["enter_long"] = 0

        dataframe.loc[
            (
                (dataframe["rsi"] < 30)
                & (dataframe["close"] < dataframe["bb_lower"] * 1.05)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Generate exit signals for scalping.
        """
        rsi_overbought_cross = (dataframe["rsi"] > self.rsi_exit_threshold) & (
            dataframe["rsi_prev"] >= self.rsi_exit_threshold
        )

        multi_overbought = (
            (dataframe["rsi"] > 75)
            & (dataframe["stoch_k"] > 80)
            & (dataframe["close"] > dataframe["bb_upper"] * 0.99)
        )

        rsi_high = (
            (dataframe["rsi"] > 65)
            & (dataframe["macdhist"] < dataframe["macdhist_prev"])
            & (dataframe["close"] > dataframe["bb_upper"] * 0.97)
        )

        dataframe.loc[
            (
                (rsi_overbought_cross | multi_overbought | rsi_high)
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1

        return dataframe

    def custom_exit(
        self, pair: str, trade, current_time, current_profit: float, **kwargs
    ) -> Optional[str]:
        """
        Custom exit logic for scalping - quick profit taking.

        Exit early if:
        - Profit > 1.2% and RSI > 75 (taking profits)
        - Profit > 0.8% and held for > 15 minutes (time-based exit)
        - Profit > 0.5% and MACD turning bearish
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # Quick profit taking
        if current_profit > 0.012:  # 1.2% profit
            if last_candle["rsi"] > 75:
                return "profit_taking_high"

        # Time-based exit
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
        if current_profit > 0.008 and trade_duration > 15:  # 0.8% profit after 15 min
            return "profit_taking_time"

        # Momentum reversal
        if current_profit > 0.005:  # 0.5% profit
            if last_candle["macdhist"] < 0 and last_candle["macdhist_prev"] > 0:
                return "momentum_reversal"

        return None

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """Confirm trade entry with additional checks."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        if side == "long" and last_candle["rsi"] > 82:
            return False

        return True
