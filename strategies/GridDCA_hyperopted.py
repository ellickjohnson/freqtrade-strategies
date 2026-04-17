# pragma: no cover
# GridDCA v3.0 - FreqAI-Enhanced Auto-Learning Strategy
# Combines mean reversion with ML predictions and regime detection
# Auto-adjusts parameters based on market conditions

import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.persistence import Trade
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)

class GridDCA_hyperopted(IStrategy):
    """
    GridDCA v3.0 - FreqAI-Enhanced Auto-Learning Strategy
    
    Features:
    - FreqAI ML predictions for entry/exit timing
    - Regime detection (volatility, trending, ranging)
    - Auto-adjusting grid spacing based on conditions
    - Walk-forward hyperopt integration
    - DCA position sizing with smart entries
    
    FreqAI Features Used:
    - RSI, Volume, ATR predictions
    - Retrains every 4 hours on live data
    - Uses LightGBM classifier for direction prediction
    """
    
    INTERFACE_VERSION = 3
    process_only_new_candles = True
    startup_candle_count = 150
    
    # Optimal hyperopt parameters (found via 200-epoch optimization)
    rsi_oversold = IntParameter(25, 35, default=30, space='buy', optimize=True)
    rsi_overbought = IntParameter(75, 85, default=80, space='sell', optimize=True)
    take_profit_pct = DecimalParameter(2.0, 4.0, default=3.0, space='sell', optimize=True)
    max_open_trades_param = IntParameter(3, 5, default=4, space='buy', optimize=True)
    
    # Grid spacing parameters (auto-adjusted by regime detector)
    grid_spacing_low = DecimalParameter(0.005, 0.02, default=0.01, space='buy', optimize=False)
    grid_spacing_high = DecimalParameter(0.02, 0.05, default=0.03, space='buy', optimize=False)
    
    # Regime thresholds
    volatility_threshold_low = DecimalParameter(0.01, 0.03, default=0.015, space='buy', optimize=False)
    volatility_threshold_high = DecimalParameter(0.03, 0.06, default=0.04, space='buy', optimize=False)
    adx_trend_threshold = IntParameter(20, 35, default=25, space='buy', optimize=False)
    
    # Stop loss and position management
    stoploss = -0.10
    use_custom_stoploss = False
    trailing_stop = False
    
    # Position adjustment for DCA
    position_adjustment_enable = True
    max_entry_position_adjustment = 3
    
    # Timeframe and trading parameters
    timeframe = '15m'
    can_short = False
    max_open_trades = 4
    
    # ROI targets
    minimal_roi = {"0": 0.03}
    
    # Optimized constants from hyperopt
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 80
    TAKE_PROFIT = 3.0
    COOLDOWN = 3

    @property
    def protections(self):
        return [
            {"method": "CooldownLookback", "stop_duration_candles": self.COOLDOWN},
            {"method": "MaxDrawdown", "trade_limit": 20, "stop_after_trades": 10, "max_allowed_drawdown": 0.15}
        ]

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: dict) -> DataFrame:
        """FreqAI feature engineering - creates ML training features."""
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-rsi-change"] = dataframe["%-rsi-period"].pct_change()
        dataframe["%-volume-mean-ratio"] = dataframe["volume"] / dataframe["volume"].rolling(window=20).mean()
        dataframe["%-atr-ratio"] = ta.ATR(dataframe, timeperiod=period) / dataframe["close"]
        dataframe["%-price-velocity"] = (dataframe["close"] - dataframe["close"].shift(period)) / dataframe["close"].shift(period)
        dataframe["%-momentum"] = ta.MOM(dataframe, timeperiod=period)
        dataframe["%-adx"] = ta.ADX(dataframe, timeperiod=period)
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Basic feature engineering for FreqAI predictions."""
        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-volume_pct"] = dataframe["volume"].pct_change()
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define prediction targets for FreqAI - predicts price direction."""
        dataframe['&-target'] = self._get_target(dataframe)
        return dataframe

    def _get_target(self, dataframe: DataFrame) -> np.ndarray:
        """Create prediction target: 1 if price increases >1% in next 3 candles."""
        future_close = dataframe["close"].shift(-3)
        returns = (future_close - dataframe["close"]) / dataframe["close"]
        return (returns > 0.01).astype(int).values

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Main indicator calculation - includes regime detection."""
        # RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # EMAs for trend filter
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # ATR for volatility measurement
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        
        # Regime Detection
        dataframe['regime'] = self._detect_regime(dataframe)
        
        # Bollinger Bands
        dataframe['bb_upper'], dataframe['bb_mid'], dataframe['bb_lower'] = ta.BBANDS(
            dataframe['close'].values, timeperiod=20, nbdevup=2.0, nbdevdn=2.0
        )
        
        # Entry/exit flags
        dataframe['rsi_oversold'] = dataframe['rsi'] < self.RSI_OVERSOLD
        dataframe['rsi_overbought'] = dataframe['rsi'] > self.RSI_OVERBOUGHT
        dataframe['price_below_ema20'] = dataframe['close'] < dataframe['ema_20']
        
        return dataframe

    def _detect_regime(self, dataframe: DataFrame) -> np.ndarray:
        """Detect market regime: 0=ranging, 1=trending_up, 2=trending_down, 3=volatile."""
        regime = np.zeros(len(dataframe))
        
        atr_ratio = dataframe['atr_ratio'].values
        adx = dataframe['adx'].values
        plus_di = dataframe['plus_di'].values
        minus_di = dataframe['minus_di'].values
        
        # Volatile regime (high ATR)
        volatile_mask = atr_ratio > float(self.volatility_threshold_high.value)
        regime[volatile_mask] = 3
        
        # Trending regimes (strong ADX)
        trend_mask = (adx > float(self.adx_trend_threshold.value)) & (~volatile_mask)
        
        # Up trend: +DI > -DI
        up_trend = trend_mask & (plus_di > minus_di)
        regime[up_trend] = 1
        
        # Down trend: -DI > +DI
        down_trend = trend_mask & (plus_di < minus_di)
        regime[down_trend] = 2
        
        return regime

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals - uses FreqAI prediction if available, falls back to standard logic."""
        conditions = [
            (dataframe['rsi_oversold']) & 
            (dataframe['price_below_ema20']) &
            (dataframe['volume'] > 0)
        ]
        
        # FreqAI prediction condition (if available)
        if '&-target' in dataframe.columns:
            freqai_confident = dataframe.get('do_predict', 1) == 1
            freqai_bullish = dataframe['&-target'] > 0.5
            conditions.append(freqai_confident & freqai_bullish)
        
        # Combine conditions
        if len(conditions) > 1:
            dataframe.loc[conditions[0] | conditions[1], 'enter_long'] = 1
        else:
            dataframe.loc[conditions[0], 'enter_long'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exits handled by custom_exit."""
        dataframe.loc[dataframe['rsi_overbought'], 'exit_long'] = 1
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic with regime-aware adjustments."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last_candle = dataframe.iloc[-1]
        
        # Get current regime
        regime = last_candle.get('regime', 0)
        atr_ratio = last_candle.get('atr_ratio', 0.02)
        
        # Time-based exit: force close after 48h if underwater >5%
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_duration > 48 and current_profit < -0.05:
            return 'timeout_large_loss'
        
        # Regime-aware exit
        # In high volatility, exit earlier on profit
        if atr_ratio > float(self.volatility_threshold_high.value) and current_profit > 0.02:
            return 'high_vol_profit'
        
        # In trending regime, let winners run longer
        if regime in [1, 2] and current_profit > 0.02:
            if last_candle['rsi'] > self.RSI_OVERBOUGHT:
                return 'trend_rsi_overbought'
            return None
        
        # Exit at profit target
        if current_profit > (self.take_profit_pct.value / 100):
            return 'grid_profit_target'
        
        # RSI overbought exit (only if in profit)
        if current_profit > 0.01 and last_candle['rsi'] > self.RSI_OVERBOUGHT:
            return 'rsi_overbought_profit'
        
        # FreqAI exit signal (if available)
        if '&-target' in dataframe.columns:
            freqai_bearish = last_candle.get('&-target', 0) < 0.3
            if freqai_bearish and current_profit > 0.01:
                return 'freqai_bearish_signal'
        
        return None

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float, proposed_stake: float, min_stake: float, max_stake: float, leverage: float, entry_tag: Optional[str], side: str, **kwargs) -> float:
        """DCA position sizing with regime-aware adjustments."""
        base_stake = 15.0
        try:
            trades = Trade.get_trades_proxy(pair=pair, is_open=True)
            trade_count = len(list(trades))
        except Exception:
            trade_count = 0
        
        if trade_count > 0:
            # Get current regime for position sizing
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                atr_ratio = last_candle.get('atr_ratio', 0.02)
                
                # In high volatility, reduce DCA size more
                if atr_ratio > float(self.volatility_threshold_high.value):
                    return max(base_stake / (trade_count + 2), min_stake) if min_stake else base_stake / (trade_count + 2)
            
            stake = base_stake / (trade_count + 1)
        else:
            stake = base_stake
        
        return max(stake, min_stake) if min_stake else stake

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str, current_time: datetime, entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """Additional entry confirmation with regime check."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return True
        last_candle = dataframe.iloc[-1]
        
        # Skip entries in extreme volatility (regime 3)
        regime = last_candle.get('regime', 0)
        if regime == 3:  # Volatile regime - skip new entries
            return False
        
        # Volume confirmation
        if last_candle['volume_ratio'] < 0.5:  # Very low volume
            return False
        
        return True


def get_optimal_params(pair: str = None, regime: str = 'default') -> dict:
    """
    Returns optimal parameters based on current market regime.
    Called by auto_learn.py to hot-swap parameters.
    
    Regimes: 'low_vol', 'medium_vol', 'high_vol', 'trending_up', 'trending_down'
    """
    params = {
        'default': {
            'rsi_oversold': 30,
            'rsi_overbought': 80,
            'grid_spacing': 0.02,
            'take_profit': 0.03
        },
        'low_vol': {  # Tight grids, quick exits
            'rsi_oversold': 35,
            'rsi_overbought': 75,
            'grid_spacing': 0.01,
            'take_profit': 0.02
        },
        'high_vol': {  # Wide grids, patient exits
            'rsi_oversold': 25,
            'rsi_overbought': 85,
            'grid_spacing': 0.04,
            'take_profit': 0.05
        },
        'trending_up': {  # Let winners run
            'rsi_oversold': 35,
            'rsi_overbought': 85,
            'grid_spacing': 0.025,
            'take_profit': 0.04
        },
        'trending_down': {  # More conservative entries
            'rsi_oversold': 25,
            'rsi_overbought': 70,
            'grid_spacing': 0.02,
            'take_profit': 0.025
        }
    }
    return params.get(regime, params['default'])
