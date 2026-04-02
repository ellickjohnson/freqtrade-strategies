import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter
from functools import reduce
import logging

logger = logging.getLogger(__name__)

class OscillatorConfluence(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '15m'
    can_short = False
    minimal_roi = {"0": 0.10, "120": 0.05, "240": 0.03}
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    startup_candle_count = 200
    CONFLUENCE_THRESHOLD = 2

    def populate_indicators(self, dataframe, metadata):
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['cci'] = ta.CCI(dataframe, timeperiod=20)
        dataframe['willr'] = ta.WILLR(dataframe, timeperiod=14)
        dataframe['mfi'] = ta.MFI(dataframe, timeperiod=14)
        bb = ta.BBANDS(dataframe, timeperiod=20)
        dataframe['bb_percent'] = (dataframe['close'] - bb['lowerband']) / (bb['upperband'] - bb['lowerband'])
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        buy_conf = ((dataframe['rsi'] < 30).astype(int) + (dataframe['slowk'] < 20).astype(int) + 
                    (dataframe['cci'] < -100).astype(int) + (dataframe['willr'] < -80).astype(int) +
                    (dataframe['mfi'] < 20).astype(int) + (dataframe['bb_percent'] < 0.2).astype(int))
        sell_conf = ((dataframe['rsi'] > 70).astype(int) + (dataframe['slowk'] > 80).astype(int) +
                     (dataframe['cci'] > 100).astype(int) + (dataframe['willr'] > -20).astype(int) +
                     (dataframe['mfi'] > 80).astype(int) + (dataframe['bb_percent'] > 0.8).astype(int))
        conditions_long = [buy_conf >= self.CONFLUENCE_THRESHOLD, dataframe['adx'] > 20, 
                          dataframe['volume'] > dataframe['volume_sma'] * 0.8, 
                          dataframe['close'] > dataframe['ema_200'] * 0.95]
        dataframe.loc[reduce(lambda x, y: x & y, conditions_long), 'enter_long'] = 1
        if self.can_short:
            conditions_short = [sell_conf >= self.CONFLUENCE_THRESHOLD, dataframe['adx'] > 20,
                               dataframe['volume'] > dataframe['volume_sma'] * 0.8,
                               dataframe['close'] < dataframe['ema_200'] * 1.05]
            dataframe.loc[reduce(lambda x, y: x & y, conditions_short), 'enter_short'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        buy_conf = ((dataframe['rsi'] < 30).astype(int) + (dataframe['slowk'] < 20).astype(int) + 
                    (dataframe['cci'] < -100).astype(int) + (dataframe['willr'] < -80).astype(int) +
                    (dataframe['mfi'] < 20).astype(int) + (dataframe['bb_percent'] < 0.2).astype(int))
        sell_conf = ((dataframe['rsi'] > 70).astype(int) + (dataframe['slowk'] > 80).astype(int) +
                     (dataframe['cci'] > 100).astype(int) + (dataframe['willr'] > -20).astype(int) +
                     (dataframe['mfi'] > 80).astype(int) + (dataframe['bb_percent'] > 0.8).astype(int))
        dataframe.loc[sell_conf >= self.CONFLUENCE_THRESHOLD, 'exit_long'] = 1
        if self.can_short:
            dataframe.loc[buy_conf >= self.CONFLUENCE_THRESHOLD, 'exit_short'] = 1
        return dataframe
