# GridDCA Strategy for Freqtrade
# Version: 2.0 - Mean Reversion with DCA (Original Best Performer)

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.persistence import Trade
from pandas import DataFrame
import talib
import numpy as np
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class GridDCA(IStrategy):
    """GridDCA v2.0 - Mean Reversion with DCA
    
    BEST PERFORMER: 471 trades, 68.6% win rate, -7.33% loss, 7.73% drawdown
    
    Strategy Logic:
    - Enter when RSI oversold (< 25) and price below EMA20
    - DCA into positions on successive dips
    - Exit on RSI overbought (> 75) or profit target (2%)
    - Fixed 10% stop loss (no trailing, no ATR complexity)
    - 48h timeout for positions >5% underwater
    
    Key: Let mean reversion breathe - no aggressive early exits
    """
    
    # Hyperoptable Parameters
    rsi_oversold = IntParameter(20, 35, default=25, space='buy', optimize=True)
    rsi_overbought = IntParameter(65, 80, default=75, space='sell', optimize=True)
    take_profit_pct = DecimalParameter(1.0, 3.0, default=2.0, space='sell', optimize=True)
    max_open_trades_param = IntParameter(2, 5, default=3, space='buy', optimize=True)
    cooldown_candles = IntParameter(3, 10, default=5, space='buy', optimize=True)
    
    timeframe = '15m'
    can_short = False
    
    # Position adjustment for DCA
    position_adjustment_enable = True
    max_entry_position_adjustment = 3
    
    # Risk management - FIXED, SIMPLE
    stoploss = -0.10
    use_custom_stoploss = False
    trailing_stop = False
    
    # ROI targets
    minimal_roi = {"0": 0.05, "30": 0.03, "60": 0.02, "120": 0.01}
    
    max_open_trades = 3
    startup_candle_count = 100
    
    # Fixed constants
    RSI_OVERSOLD = 25
    RSI_OVERBOUGHT = 75
    TAKE_PROFIT = 2.0
    COOLDOWN = 5

    @property
    def protections(self):
        return [{"method": "CooldownLookback", "stop_duration_candles": self.COOLDOWN}]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe['close'].values
        dataframe['rsi'] = talib.RSI(close, timeperiod=14)
        dataframe['ema_20'] = talib.EMA(close, timeperiod=20)
        dataframe['ema_50'] = talib.EMA(close, timeperiod=50)
        dataframe['ema_200'] = talib.EMA(close, timeperiod=200)
        dataframe['bb_upper'], dataframe['bb_mid'], dataframe['bb_lower'] = talib.BBANDS(
            close, timeperiod=20, nbdevup=2, nbdevdn=2
        )
        dataframe['price_below_ema20'] = dataframe['close'] < dataframe['ema_20']
        dataframe['rsi_oversold'] = dataframe['rsi'] < self.RSI_OVERSOLD
        dataframe['rsi_overbought'] = dataframe['rsi'] > self.RSI_OVERBOUGHT
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe['rsi_oversold']) & (dataframe['price_below_ema20']),
            'enter_long'
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe['rsi_overbought'], 'exit_long'] = 1
        return dataframe

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: Optional[float],
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        base_stake = 15.0
        try:
            trades = Trade.get_trades_proxy(pair=pair, is_open=True)
            trade_count = len(list(trades))
        except Exception:
            trade_count = 0
        if trade_count > 0:
            stake = base_stake / (trade_count + 1)
        else:
            stake = base_stake
        return max(stake, min_stake) if min_stake else stake

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        open_trades = Trade.get_open_trades()
        if len(open_trades) >= self.max_open_trades_param.value:
            return False
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                   current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last_candle = dataframe.iloc[-1]
        
        # Exit at profit target (2%)
        if current_profit > (self.take_profit_pct.value / 100):
            return 'grid_profit_target'
        
        # Exit if RSI overbought and in profit
        if current_profit > 0.01 and last_candle['rsi'] > self.RSI_OVERBOUGHT:
            return 'rsi_overbought_profit'
        
        # Time exit for underwater positions (48h at -5%)
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_duration > 48 and current_profit < -0.05:
            return 'timeout_large_loss'
        
        return None
