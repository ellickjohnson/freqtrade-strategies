# Freqtrade Trading Strategies

A collection of Freqtrade trading strategies with learning-focused documentation. These strategies are designed to be transparent, explaining WHY trades happen so you can learn from every decision.

## Strategies

### 1. OscillatorConfluence (Main Bot - 15m Timeframe)

A multi-oscillator confluence strategy that enters trades when multiple indicators show oversold conditions simultaneously.

**Entry Conditions (need 2+ to be true):**
- RSI < 30 (oversold)
- Stochastic K & D < 20 (oversold)
- CCI < -100 (oversold)
- Williams %R < -80 (oversold)
- MFI < 20 (oversold)
- MACD bullish crossover
- Price below lower Bollinger Band

**Additional Requirements:**
- Price MUST be above EMA 200 (uptrend filter)
- ADX > 20 (trend strength)

**Exit Conditions:**
- 2+ oscillators show overbought (RSI > 70, Stoch > 80, etc.)
- Stop loss at -5%
- Take profit at 10% (ROI targets)
- Trailing stop after 2% profit

**Characteristics:**
- Fewer trades, higher confidence
- Larger profit targets (5-10%)
- Longer hold times (hours to days)
- Best for trending markets

---

### 2. ScalpingQuick (Scalping Bot - 5m Timeframe)

An aggressive scalping strategy that enters on momentum signals for quick profits.

**Entry Conditions (ALL must be true):**
1. RSI crossing up through 40 OR RSI 45-65 with positive MACD
2. Price above EMA 9 (short-term uptrend)
3. MACD histogram turning positive
4. Volume spike > 1.5x average
5. Price NOT at upper Bollinger Band
6. Bullish candle

**Exit Conditions:**
- Take profit at 0.8-1.5%
- Stop loss at -1.5%
- Trailing stop after 0.5% profit
- Time-based exit after 15+ minutes with profit
- RSI crossing down through 70 (overbought)

**Characteristics:**
- More trades, smaller profits
- Quick entries and exits
- Best for choppy/ranging markets
- Higher frequency trading

## Why This Repository?

**Learning-Focused:** Every trade notification includes the WHY - which conditions were met, what triggered the entry, and what will trigger the exit.

**Transparent:** All strategy logic is documented and explained. You can understand every decision the bot makes.

**Dual Strategy System:** Run both strategies simultaneously:
- **Main Bot** for larger, more confident trades
- **Scalping Bot** for quick, frequent profits

## Files

| File | Description |
|------|-------------|
| `OscillatorConfluence.py` | Multi-oscillator confluence strategy (15m) |
| `ScalpingQuick.py` | Aggressive scalping strategy (5m) |
| `analyze_signals.py` | Explains WHY signals are/aren't triggering |
| `notify_verbose.py` | Detailed Slack notifications with reasoning |
| `check_status.py` | Bot status checker |
| `notify_trades.py` | Simple trade notifications |

## Configuration

Example Freqtrade config for Main Bot:
```json
{
  "strategy": "OscillatorConfluence",
  "timeframe": "15m",
  "max_open_trades": 3,
  "stake_currency": "USDT",
  "stake_amount": 330,
  "dry_run": true
}
```

Example Freqtrade config for Scalping Bot:
```json
{
  "strategy": "ScalpingQuick",
  "timeframe": "5m",
  "max_open_trades": 5,
  "stake_currency": "USDT",
  "stake_amount": 50,
  "dry_run": true
}
```

## Learning Tools

Run `analyze_signals.py` anytime to understand current market conditions:
```bash
python3 analyze_signals.py
```

This will show:
- Current prices and positions
- Which entry conditions passed/failed
- Why signals are NOT triggering
- Expected exit conditions

## Notifications

Trade notifications include detailed explanations:

```
🟢 NEW TRADE OPENED - Main Bot

📊 SOL/USDT
💰 Entry: $79.42
💵 Stake: $330.00

📈 ENTRY REASON (OscillatorConfluence - 15m):
   • 2+ oscillators showed oversold conditions
   • RSI < 30, Stoch < 20, CCI < -100, or similar
   • Price was above EMA 200 (uptrend confirmed)
   • MACD showed bullish momentum

💡 WHAT TO EXPECT:
   • Bot will hold until exit conditions met
   • Will receive notification when trade closes
```

## Strategy Comparison

| Feature | OscillatorConfluence | ScalpingQuick |
|---------|----------------------|---------------|
| Timeframe | 15m | 5m |
| Max Trades | 3 | 5 |
| Stake/Trade | $330 | $50 |
| Target Profit | 5-10% | 0.5-1.5% |
| Stop Loss | -5% | -1.5% |
| Trade Frequency | Low | High |
| Entry Signals | Confluence (2+ oscillators) | Momentum + Volume |
| Best For | Trending markets | Choppy/sideways |

## Why No Trades Might Happen

| Condition | Effect |
|-----------|--------|
| Price below EMA | Downtrend - both strategies avoid |
| RSI 40-60 | Neutral zone - no momentum |
| No volume spikes | Market quiet - no interest |
| MACD negative | Bearish momentum |
| Price at upper BB | Resistance zone |
| Bearish candles | Selling pressure |

## Disclaimer

These strategies are for educational purposes. Always test in dry-run mode before live trading. Past performance does not guarantee future results. Cryptocurrency trading involves significant risk.

## License

MIT License

## Contributing

Contributions welcome! Please submit issues or pull requests for strategy improvements.
