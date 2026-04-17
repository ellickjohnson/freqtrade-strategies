from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.persistence import Trade
from pandas import DataFrame
import talib
import numpy as np
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SwingDCA(IStrategy):
    rsi_oversold = IntParameter(25, 45, default=40, space="buy", optimize=True)
    rsi_overbought = IntParameter(60, 80, default=70, space="sell", optimize=True)
    take_profit_pct = DecimalParameter(
        2.0, 5.0, default=3.5, space="sell", optimize=True
    )
    cooldown_candles = IntParameter(2, 5, default=3, space="buy", optimize=True)
    max_open_trades_param = IntParameter(2, 4, default=3, space="buy", optimize=True)

    timeframe = "1h"
    can_short = False
    stoploss = -0.08

    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    minimal_roi = {"0": 0.04, "60": 0.02, "240": 0.01, "720": 0.005}

    max_open_trades = 3
    startup_candle_count = 200

    position_adjustment_enable = True
    max_entry_position_adjustment = 2

    RSI_OVERSOLD = 40
    RSI_OVERBOUGHT = 70
    TAKE_PROFIT = 3.5
    COOLDOWN = 3

    @property
    def protections(self):
        return [{"method": "CooldownPeriod", "stop_duration_candles": self.COOLDOWN}]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"].values
        dataframe["rsi"] = talib.RSI(close, timeperiod=14)
        dataframe["ema_20"] = talib.EMA(close, timeperiod=20)
        dataframe["ema_50"] = talib.EMA(close, timeperiod=50)
        dataframe["ema_200"] = talib.EMA(close, timeperiod=200)
        dataframe["bb_upper"], dataframe["bb_mid"], dataframe["bb_lower"] = (
            talib.BBANDS(close, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        )
        dataframe["atr"] = talib.ATR(
            dataframe["high"].values,
            dataframe["low"].values,
            close,
            timeperiod=14,
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < self.RSI_OVERSOLD),
            "enter_long",
        ] = 1

        dataframe.loc[
            (dataframe["close"] < dataframe["bb_lower"]),
            "enter_long",
        ] = 1

        rsi_cross_up = (dataframe["rsi"] > 35) & (dataframe["rsi"].shift(1) <= 35)
        dataframe.loc[
            rsi_cross_up,
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > self.RSI_OVERBOUGHT)
            | (dataframe["close"] > dataframe["bb_upper"]),
            "exit_long",
        ] = 1
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: Optional[float],
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        base_stake = 100.0
        dca_stake = 50.0
        try:
            trades = Trade.get_trades_proxy(pair=pair, is_open=True)
            trade_count = len(list(trades))
        except Exception:
            trade_count = 0
        if trade_count > 0:
            stake = dca_stake
        else:
            stake = base_stake
        return max(stake, min_stake) if min_stake else stake

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        open_trades = Trade.get_open_trades()
        if len(open_trades) >= self.max_open_trades_param.value:
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
        if current_profit > (self.TAKE_PROFIT / 100):
            return "swing_profit_target"

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last_candle = dataframe.iloc[-1]

        if current_profit > 0.015 and last_candle["rsi"] > 65:
            return "rsi_overbought_profit"

        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_duration > 72 and current_profit < -0.04:
            return "timeout_large_loss"

        return None
