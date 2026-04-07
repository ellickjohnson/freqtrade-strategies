# BreakoutMomentum Strategy for Freqtrade
# Version: 1.0 - Resistance Breakout with Momentum Confirmation

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
from freqtrade.persistence import Trade
from pandas import DataFrame
import talib
import numpy as np
from datetime import datetime
from typing import Optional
from functools import reduce

class BreakoutMomentum(IStrategy):
    """BreakoutMomentum v1.0 - Resistance Breakout Strategy
    
    Entry: Price breaks 20-candle high with volume + momentum confirmation
    Exit: ATR trailing stop after 0.8% profit, time-based exit after 8 candles
    """
    
    # Hyperoptable Parameters
    breakout_period = IntParameter(10, 30, default=20, space='buy', optimize=True)
    adx_threshold = IntParameter(18, 30, default=22, space='buy', optimize=True)
    volume_multiplier = DecimalParameter(1.4, 2.5, default=1.8, space='buy', optimize=True)
    rsi_min = IntParameter(40, 55, default=45, space='buy', optimize=True)
    rsi_max = IntParameter(60, 75, default=70, space='buy', optimize=True)
    candle_body_pct = DecimalParameter(0.5, 0.8, default=0.6, space='buy', optimize=True)
    trailing_start = DecimalParameter(0.005, 0.015, default=0.008, space='sell', optimize=True)
    max_candles = IntParameter(4, 12, default=8, space='sell', optimize=True)
    
    timeframe = '15m'
    stoploss = -0.05
    use_custom_stoploss = True
    can_short = False
    
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.012
    trailing_only_offset_is_reached = True
    
    minimal_roi = {"0": 0.06, "30": 0.03, "60": 0.015, "120": 0.005}
    max_open_trades = 3
    startup_candle_count = 200
    
    BREAKOUT_PERIOD = 20
    ADX_THRESH = 22
    VOL_MULT = 1.8
    RSI_MIN = 45
    RSI_MAX = 70
    CANDLE_BODY = 0.6
    MAX_CANDLES = 8

    @property
    def protections(self):
        return [{"method": "CooldownLookback", "stop_duration_candles": 5}]

    def informative_pairs(self):
        pairs = []
        if hasattr(self.dp, 'current_whitelist'):
            for pair in self.dp.current_whitelist():
                pairs.append((pair, '1h'))
        return pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe['close'].values
        high = dataframe['high'].values
        low = dataframe['low'].values
        volume = dataframe['volume'].values
        
        # Trend
        dataframe['ema_200'] = talib.EMA(close, timeperiod=200)
        dataframe['adx'] = talib.ADX(high, low, close, timeperiod=14)
        
        # Breakout: highest high of last N candles
        dataframe['highest_high'] = dataframe['high'].rolling(window=self.BREAKOUT_PERIOD).max()
        dataframe['breakout'] = dataframe['close'] > dataframe['highest_high'].shift(1)
        
        # Volume rising
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_spike'] = dataframe['volume'] > (dataframe['volume_mean'] * self.VOL_MULT)
        dataframe['volume_rising'] = (dataframe['volume'] > dataframe['volume'].shift(1)) & (dataframe['volume'].shift(1) > dataframe['volume'].shift(2))
        
        # Momentum
        dataframe['rsi'] = talib.RSI(close, timeperiod=14)
        dataframe['rsi_valid'] = (dataframe['rsi'] > self.RSI_MIN) & (dataframe['rsi'] < self.RSI_MAX)
        
        # Volatility
        dataframe['atr'] = talib.ATR(high, low, close, timeperiod=14)
        
        # Candle
        dataframe['candle_body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['candle_range'] = dataframe['high'] - dataframe['low']
        dataframe['body_pct'] = dataframe['candle_body'] / dataframe['candle_range'].replace(0, np.nan)
        dataframe['bullish_candle'] = (dataframe['close'] > dataframe['open']) & (dataframe['body_pct'] > self.CANDLE_BODY)
        
        # Trend strength
        dataframe['strong_trend'] = dataframe['adx'] > self.ADX_THRESH
        dataframe['above_ema200'] = dataframe['close'] > dataframe['ema_200']
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = [
            dataframe['breakout'],
            dataframe['above_ema200'],
            dataframe['strong_trend'],
            dataframe['volume_spike'],
            dataframe['volume_rising'],
            dataframe['bullish_candle'],
            dataframe['rsi_valid'],
        ]
        dataframe.loc[reduce(lambda x, y: x & y, conditions), 'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe['rsi'] > 70, 'exit_long'] = 1
        return dataframe

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        atr = float(last_candle['atr'])
        atr_stop = (atr / current_rate) * 1.5
        if current_profit > self.trailing_start.value:
            atr_stop = atr_stop * 0.5
        return max(-atr_stop, -0.05)

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        candles_held = (current_time - trade.open_date_utc).total_seconds() / 900  # 15m candles
        if candles_held > self.MAX_CANDLES and current_profit < 0.005:
            return 'time_exit'
        if current_profit > 0.04:
            return 'profit_target'
        return None
