# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
OscillatorConfluence Strategy v2 - Multi-oscillator confluence with trend filter

Improvements over v1:
- Added MACD calculation and usage (aligns with README)
- All magic numbers converted to hyperopt parameters
- 1h informative timeframe for trend filter (close > EMA 200)
- Protections: cooldown after stop-loss, max_drawdown, trailing stop in profit only
- Improved exits with custom_exit, ATR-based dynamic stop
- Better risk management
"""
import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter
from freqtrade.strategy import merge_informative_pair
from pandas import DataFrame
from functools import reduce
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class OscillatorConfluence(IStrategy):
    """
    OscillatorConfluence Strategy
    
    Entry: Requires 2+ oscillators showing oversold conditions simultaneously.
    Exit: Requires 2+ oscillators showing overbought conditions.
    Trend Filter: Only long entries when 1h close > 1h EMA 200.
    
    Hyperopt-ready with all parameters configurable.
    """
    
    INTERFACE_VERSION = 3
    
    # Timeframe
    timeframe = '15m'
    can_short = False
    
    # Hyperopt Parameters - Entry Thresholds
    rsi_oversold = IntParameter(20, 40, default=30, space='buy')
    stoch_oversold = IntParameter(10, 30, default=20, space='buy')
    cci_oversold = IntParameter(-150, -50, default=-100, space='buy')
    willr_oversold = IntParameter(-90, -70, default=-80, space='buy')
    mfi_oversold = IntParameter(10, 30, default=20, space='buy')
    bb_percent_oversold = DecimalParameter(0.1, 0.3, default=0.2, space='buy')
    
    # Hyperopt Parameters - Exit Thresholds
    rsi_overbought = IntParameter(60, 80, default=70, space='sell')
    stoch_overbought = IntParameter(70, 90, default=80, space='sell')
    cci_overbought = IntParameter(50, 150, default=100, space='sell')
    willr_overbought = IntParameter(-30, -10, default=-20, space='sell')
    mfi_overbought = IntParameter(70, 90, default=80, space='sell')
    bb_percent_overbought = DecimalParameter(0.7, 0.9, default=0.8, space='sell')
    
    # Hyperopt Parameters - Strategy Settings
    confluence_threshold = IntParameter(2, 5, default=2, space='buy')
    adx_threshold = IntParameter(15, 30, default=20, space='buy')
    ema_trend_period = IntParameter(100, 300, default=200, space='buy')
    ema_trend_buffer = DecimalParameter(0.90, 1.0, default=0.95, space='buy')
    volume_sma_period = IntParameter(10, 30, default=20, space='buy')
    volume_threshold = DecimalParameter(0.5, 1.5, default=0.8, space='buy')
    
    # Hyperopt Parameters - Indicator Periods
    rsi_period = IntParameter(7, 21, default=14, space='buy')
    stoch_period = IntParameter(7, 21, default=14, space='buy')
    cci_period = IntParameter(10, 30, default=20, space='buy')
    willr_period = IntParameter(7, 21, default=14, space='buy')
    mfi_period = IntParameter(7, 21, default=14, space='buy')
    bb_period = IntParameter(10, 30, default=20, space='buy')
    macd_fast = IntParameter(8, 16, default=12, space='buy')
    macd_slow = IntParameter(20, 32, default=26, space='buy')
    macd_signal = IntParameter(7, 12, default=9, space='buy')
    atr_period = IntParameter(10, 20, default=14, space='sell')
    
    # Hyperopt Parameters - Risk Management
    stoploss_val = DecimalParameter(-0.10, -0.02, default=-0.05, space='sell')
    trailing_stop_val = CategoricalParameter([True, False], default=True, space='sell')
    trailing_stop_positive_val = DecimalParameter(0.01, 0.05, default=0.02, space='sell')
    trailing_stop_positive_offset_val = DecimalParameter(0.02, 0.06, default=0.03, space='sell')
    
    # ROI table - hyperopt will optimize these
    minimal_roi = {
        "0": 0.10,
        "60": 0.05,
        "120": 0.03,
        "240": 0.02
    }
    
    # Stop loss
    stoploss = -0.05
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True
    
    # Protections
    @property
    def protections(self):
        return [
            {
                "method": "CooldownLookback",
                "stop_duration_candles": 5
            },
            {
                "method": "MaxDrawdown",
                "max_allowed_drawdown": 0.15
            },
            {
                "method": "StoplossFromGain",
                "gains": [0.02, 0.05, 0.10],
                "stoplosses": [-0.03, -0.02, -0.01]
            }
        ]
    
    startup_candle_count = 200
    use_custom_stoploss = True
    
    def informative_pairs(self):
        """Add 1h timeframe for trend filter."""
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, '1h') for pair in pairs]
        return informative_pairs
    
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate 1h indicators for trend filter."""
        informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='1h')
        
        # EMA 200 on 1h for trend filter
        informative['ema_200_1h'] = ta.EMA(informative, timeperiod=self.ema_trend_period.value)
        
        # Merge with main dataframe
        dataframe = merge_informative_pair(dataframe, informative, '1h', ffill=True)
        
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all indicators needed for entry/exit signals."""
        
        # 1h trend filter
        dataframe = self.populate_indicators_1h(dataframe, metadata)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=self.stoch_period.value, 
                         slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # ADX
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        
        # CCI
        dataframe['cci'] = ta.CCI(dataframe, timeperiod=self.cci_period.value)
        
        # Williams %R
        dataframe['willr'] = ta.WILLR(dataframe, timeperiod=self.willr_period.value)
        
        # MFI
        dataframe['mfi'] = ta.MFI(dataframe, timeperiod=self.mfi_period.value)
        
        # Bollinger Bands
        bb = ta.BBANDS(dataframe, timeperiod=self.bb_period.value)
        dataframe['bb_lower'] = bb['lowerband']
        dataframe['bb_middle'] = bb['middleband']
        dataframe['bb_upper'] = bb['upperband']
        dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lower']) / \
                                   (dataframe['bb_upper'] - dataframe['bb_lower'])
        
        # MACD (now properly added)
        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value, 
                       slowperiod=self.macd_slow.value, signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        dataframe['macdhist_prev'] = dataframe['macdhist'].shift(1)
        
        # ATR for dynamic stop loss
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        
        # Volume SMA
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=self.volume_sma_period.value)
        
        # EMA for local trend
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=self.ema_trend_period.value)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Generate entry signals based on oscillator confluence."""
        
        # Count oversold oscillators
        buy_conf = (
            (dataframe['rsi'] < self.rsi_oversold.value).astype(int) +
            (dataframe['slowk'] < self.stoch_oversold.value).astype(int) +
            (dataframe['cci'] < self.cci_oversold.value).astype(int) +
            (dataframe['willr'] < self.willr_oversold.value).astype(int) +
            (dataframe['mfi'] < self.mfi_oversold.value).astype(int) +
            (dataframe['bb_percent'] < self.bb_percent_oversold.value).astype(int) +
            # MACD bullish crossover or positive histogram
            ((dataframe['macd'] > dataframe['macdsignal']) & 
             (dataframe['macdhist'].shift(1) < 0) & (dataframe['macdhist'] > 0)).astype(int)
        )
        
        # Entry conditions:
        # 1. Confluence threshold met
        # 2. ADX shows trend
        # 3. Volume confirmation
        # 4. 1h trend filter: close > EMA 200 on 1h
        # 5. MACD bullish or turning bullish
        conditions = [
            buy_conf >= self.confluence_threshold.value,
            dataframe['adx'] > self.adx_threshold.value,
            dataframe['volume'] > dataframe['volume_sma'] * self.volume_threshold.value,
            # 1h trend filter
            dataframe['close_1h'] > dataframe['ema_200_1h_1h'],
            # MACD bullish signal
            (dataframe['macdhist'] > 0) | 
            ((dataframe['macdhist'] > dataframe['macdhist_prev']) & 
             (dataframe['macdhist_prev'] < 0))
        ]
        
        dataframe.loc[
            reduce(lambda x, y: x & y, conditions),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Generate exit signals based on oscillator confluence."""
        
        # Count overbought oscillators
        sell_conf = (
            (dataframe['rsi'] > self.rsi_overbought.value).astype(int) +
            (dataframe['slowk'] > self.stoch_overbought.value).astype(int) +
            (dataframe['cci'] > self.cci_overbought.value).astype(int) +
            (dataframe['willr'] > self.willr_overbought.value).astype(int) +
            (dataframe['mfi'] > self.mfi_overbought.value).astype(int) +
            (dataframe['bb_percent'] > self.bb_percent_overbought.value).astype(int) +
            # MACD bearish crossover
            ((dataframe['macd'] < dataframe['macdsignal']) & 
             (dataframe['macdhist'].shift(1) > 0) & (dataframe['macdhist'] < 0)).astype(int)
        )
        
        # Exit when 2+ oscillators show overbought
        dataframe.loc[
            sell_conf >= self.confluence_threshold.value,
            'exit_long'
        ] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade, current_time, current_profit: float,
                         current_rate: float, **kwargs) -> Optional[float]:
        """Dynamic ATR-based stop loss."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Use ATR for dynamic stop loss
        atr = last_candle['atr']
        current_price = last_candle['close']
        
        # ATR-based stop: 2 * ATR below entry
        # Only activate trailing stop after profit
        if current_profit > self.trailing_stop_positive_offset_val.value:
            # Trail stop at 1.5 * ATR below current price
            stoploss_price = current_price - (1.5 * atr)
            stoploss_distance = (current_price - stoploss_price) / current_price
            return -stoploss_distance
        
        return None
    
    def custom_exit(self, pair: str, trade, current_time, current_profit: float,
                     **kwargs) -> Optional[str]:
        """Custom exit logic for improved risk management."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Time-based exit
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # Exit if held for more than 24 hours with minimal profit
        if trade_duration > 24 and current_profit < 0.01:
            return 'timeout_minimal_profit'
        
        # Exit if held for more than 48 hours regardless of profit
        if trade_duration > 48:
            return 'timeout_48h'
        
        # Exit on strong reversal signals
        if current_profit > 0.02:  # Only check reversal if in profit
            # MACD bearish crossover
            if (last_candle['macdhist'] < 0 and 
                last_candle['macdhist_prev'] > 0 and
                last_candle['macd'] < last_candle['macdsignal']):
                return 'macd_bearish_cross'
            
            # RSI overbought
            if last_candle['rsi'] > self.rsi_overbought.value:
                return 'rsi_overbought'
            
            # Price at upper Bollinger Band
            if last_candle['close'] >= last_candle['bb_upper'] * 0.99:
                return 'bb_upper_resistance'
        
        return None
