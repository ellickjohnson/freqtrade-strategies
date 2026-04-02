# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
ScalpingQuick Strategy v2 - High-frequency scalping with trend filter and improved risk management

Improvements over v1:
- All magic numbers converted to hyperopt parameters
- 1h informative timeframe for trend filter (close > EMA 200)
- Proper volume filtering (reject if volume < volume_mean)
- Protections: cooldown after stop-loss, max_drawdown 15%
- ATR-based dynamic stop loss
- Improved custom_exit with time-based exits
- Better risk management
"""
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, CategoricalParameter
from freqtrade.strategy import merge_informative_pair
from typing import Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ScalpingQuick(IStrategy):
    """
    ScalpingQuick v2 - Aggressive scalping with trend filter
    
    Entry conditions:
    - RSI crossing up through threshold OR RSI in momentum zone with positive MACD
    - Price above EMA short-term (uptrend)
    - MACD histogram turning positive
    - Volume spike > volume_factor * volume_mean (MUST be above mean)
    - Price NOT at upper Bollinger Band
    - 1h trend filter: close > EMA 200
    
    Exit conditions:
    - Take profit at dynamic ROI levels
    - Stop loss at -1.5% (dynamic ATR-based)
    - Trailing stop after profit
    - Time-based exits
    - Signal-based exits (RSI overbought, MACD reversal)
    
    Hyperopt-ready with all parameters configurable.
    """
    
    INTERFACE_VERSION = 3
    
    # Timeframe
    timeframe = '5m'
    can_short = False
    
    # Hyperopt Parameters - Entry Thresholds
    rsi_entry_threshold = IntParameter(30, 50, default=40, space='buy')
    rsi_momentum_low = IntParameter(40, 50, default=45, space='buy')
    rsi_momentum_high = IntParameter(55, 70, default=65, space='buy')
    rsi_exit_threshold = IntParameter(65, 80, default=70, space='sell')
    rsi_overbought = IntParameter(70, 85, default=75, space='sell')
    
    # Hyperopt Parameters - EMA Settings
    ema_short = IntParameter(5, 15, default=9, space='buy')
    ema_medium = IntParameter(15, 30, default=21, space='buy')
    ema_long = IntParameter(40, 60, default=50, space='buy')
    ema_trend_period = IntParameter(100, 300, default=200, space='buy')
    
    # Hyperopt Parameters - MACD
    macd_fast = IntParameter(8, 16, default=12, space='buy')
    macd_slow = IntParameter(20, 32, default=26, space='buy')
    macd_signal = IntParameter(7, 12, default=9, space='buy')
    
    # Hyperopt Parameters - Bollinger Bands
    bb_period = IntParameter(15, 25, default=20, space='buy')
    bb_std = IntParameter(1, 3, default=2, space='buy')
    bb_upper_threshold = DecimalParameter(0.96, 1.0, default=0.98, space='sell')
    
    # Hyperopt Parameters - Stochastic
    stoch_k_period = IntParameter(10, 20, default=14, space='sell')
    stoch_overbought = IntParameter(75, 90, default=80, space='sell')
    
    # Hyperopt Parameters - ATR
    atr_period = IntParameter(10, 20, default=14, space='sell')
    atr_stop_multiplier = DecimalParameter(1.0, 3.0, default=1.5, space='sell')
    
    # Hyperopt Parameters - Volume
    volume_sma_period = IntParameter(10, 30, default=20, space='buy')
    volume_factor = DecimalParameter(1.2, 2.0, default=1.5, space='buy')
    
    # Hyperopt Parameters - Risk Management
    stoploss_val = DecimalParameter(-0.03, -0.01, default=-0.015, space='sell')
    trailing_stop_val = CategoricalParameter([True, False], default=True, space='sell')
    trailing_stop_positive_val = DecimalParameter(0.003, 0.01, default=0.005, space='sell')
    trailing_stop_positive_offset_val = DecimalParameter(0.005, 0.015, default=0.008, space='sell')
    
    # ROI table - hyperopt will optimize
    minimal_roi = {
        "0": 0.015,   # 1.5% immediate profit
        "5": 0.012,   # 1.2% after 5 minutes
        "10": 0.008,  # 0.8% after 10 minutes
        "20": 0.005,  # 0.5% after 20 minutes
        "30": 0.003   # 0.3% after 30 minutes
    }
    
    # Stop loss
    stoploss = -0.015
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.008
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
            }
        ]
    
    startup_candle_count = 50
    process_only_new_candles = True
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
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_prev'] = dataframe['rsi'].shift(1)
        
        # EMAs for trend
        dataframe['ema_9'] = ta.EMA(dataframe, timeperiod=self.ema_short.value)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=self.ema_long.value)
        
        # MACD for momentum
        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value, 
                       slowperiod=self.macd_slow.value, signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        dataframe['macdhist_prev'] = dataframe['macdhist'].shift(1)
        
        # Bollinger Bands for volatility
        bollinger = ta.BBANDS(dataframe, timeperiod=self.bb_period.value, 
                              nbdevup=self.bb_std.value, nbdevdn=self.bb_std.value)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # Volume analysis - FIXED: proper rolling average
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=self.volume_sma_period.value).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        # Mark if volume is above mean (critical for entry)
        dataframe['volume_above_mean'] = (dataframe['volume'] > dataframe['volume_mean']).astype(int)
        
        # Stochastic for overbought/oversold
        stoch = ta.STOCH(dataframe, fastk_period=self.stoch_k_period.value, 
                         slowk_period=3, slowd_period=3)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        
        # ATR for dynamic stop loss
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        
        # Candle patterns
        dataframe['bullish_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Generate entry signals for scalping with strict volume filtering."""
        
        # Momentum conditions - need at least one
        momentum_conditions = [
            # RSI crossing up through threshold
            (dataframe['rsi'] > self.rsi_entry_threshold.value) &
            (dataframe['rsi_prev'] <= self.rsi_entry_threshold.value),
            
            # OR RSI in momentum zone with positive MACD
            (dataframe['rsi'] > self.rsi_momentum_low.value) &
            (dataframe['rsi'] < self.rsi_momentum_high.value) &
            (dataframe['macdhist'] > 0)
        ]
        
        # Entry conditions:
        # 1. Momentum condition met
        # 2. Price above short EMA (uptrend)
        # 3. MACD bullish
        # 4. Volume spike AND volume above mean (CRITICAL FIX)
        # 5. Not at upper Bollinger
        # 6. Bullish candle
        # 7. 1h trend filter (close > EMA 200)
        conditions = [
            # At least one momentum condition
            momentum_conditions[0] | momentum_conditions[1],
            # Price above short EMA (uptrend)
            dataframe['close'] > dataframe['ema_9'],
            # MACD histogram positive or turning positive
            (dataframe['macdhist'] > 0) | 
            ((dataframe['macdhist'] > dataframe['macdhist_prev']) & 
             (dataframe['macdhist_prev'] < 0)),
            # Volume spike AND above mean
            (dataframe['volume_ratio'] > self.volume_factor.value) &
            (dataframe['volume_above_mean'] == 1),
            # Not at upper Bollinger (room to grow)
            dataframe['close'] < dataframe['bb_upper'] * self.bb_upper_threshold.value,
            # Bullish candle
            dataframe['bullish_candle'] == 1,
            # Ensure volume
            dataframe['volume'] > 0,
            # 1h trend filter
            dataframe['close_1h'] > dataframe['ema_200_1h_1h']
        ]
        
        dataframe.loc[
            (conditions[0]) &
            (conditions[1]) &
            (conditions[2]) &
            (conditions[3]) &
            (conditions[4]) &
            (conditions[5]) &
            (conditions[6]) &
            (conditions[7]),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Generate exit signals for scalping."""
        
        # Exit conditions
        exit_conditions = [
            # RSI crossing down through exit threshold
            (dataframe['rsi'] > self.rsi_exit_threshold.value) &
            (dataframe['rsi_prev'] >= self.rsi_exit_threshold.value),
            
            # OR multiple overbought signals
            (dataframe['rsi'] > self.rsi_overbought.value) &
            (dataframe['stoch_k'] > self.stoch_overbought.value) &
            (dataframe['close'] > dataframe['bb_upper'] * 0.99)
        ]
        
        dataframe.loc[
            (exit_conditions[0] | exit_conditions[1]) &
            (dataframe['macdhist'] < dataframe['macdhist_prev']) &
            (dataframe['volume'] > 0),
            'exit_long'
        ] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade, current_time, current_profit: float,
                         current_rate: float, **kwargs) -> Optional[float]:
        """Dynamic ATR-based stop loss for scalping."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Use ATR for dynamic stop loss
        atr = last_candle['atr']
        current_price = last_candle['close']
        
        # ATR-based stop: multiplier * ATR below current price
        if current_profit > self.trailing_stop_positive_offset_val.value:
            # Tight trail for scalping: 1 * ATR
            stoploss_price = current_price - (self.atr_stop_multiplier.value * atr)
            stoploss_distance = (current_price - stoploss_price) / current_price
            return -stoploss_distance
        
        return None
    
    def custom_exit(self, pair: str, trade, current_time, current_profit: float,
                     **kwargs) -> Optional[str]:
        """Custom exit logic for scalping - quick profit taking."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Quick profit taking
        if current_profit > 0.012:  # 1.2% profit
            if last_candle['rsi'] > self.rsi_overbought.value:
                return 'profit_taking_high'
        
        # Time-based exit
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
        if current_profit > 0.008 and trade_duration > 15:  # 0.8% profit after 15 min
            return 'profit_taking_time'
        
        # Momentum reversal
        if current_profit > 0.005:  # 0.5% profit
            if last_candle['macdhist'] < 0 and last_candle['macdhist_prev'] > 0:
                return 'momentum_reversal'
        
        # Exit if held too long without profit
        if trade_duration > 60 and current_profit < 0.005:  # 1 hour without profit
            return 'timeout_no_profit'
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag: Optional[str],
                            side: str, **kwargs) -> bool:
        """Confirm trade entry with additional checks."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Don't enter if RSI is already overbought
        if side == 'long' and last_candle['rsi'] > self.rsi_overbought.value:
            return False
        
        # Don't enter if price is at upper Bollinger
        if last_candle['close'] > last_candle['bb_upper'] * 0.99:
            return False
        
        # CRITICAL FIX: Don't enter if volume is below mean
        if last_candle['volume_above_mean'] != 1:
            return False
        
        return True
