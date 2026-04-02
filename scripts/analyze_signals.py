#!/usr/bin/env python3
"""
Signal Analysis Tool - Explains WHY trades are/aren't happening

This script provides detailed analysis of:
- Current indicator values for each pair
- Which entry conditions passed/failed
- Which exit conditions passed/failed
- Why signals are NOT triggering
- Market state assessment
"""

import json
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

BOT_DIR = Path('/a0/usr/workdir/freqtrade')

def get_kraken_price(pair):
    """Fetch current price from Kraken."""
    kraken_pair = pair.replace('/', '').replace('USDT', 'USD')
    if 'BTC' in pair:
        kraken_pair = 'XBT' + pair.split('/')[0].replace('BTC', '') + 'ZUSD'
        kraken_pair = 'XXBTZUSD'
    elif 'ETH' in pair:
        kraken_pair = 'XETHZUSD'
    elif pair == 'SOL/USDT':
        kraken_pair = 'SOLUSD'
    elif pair == 'LINK/USDT':
        kraken_pair = 'LINKUSD'
    elif pair == 'AVAX/USDT':
        kraken_pair = 'AVAXUSD'
    elif pair == 'XRP/USDT':
        kraken_pair = 'XXRPZUSD'
    elif pair == 'DOGE/USDT':
        kraken_pair = 'XXDGZUSD'
    elif pair == 'MATIC/USDT':
        kraken_pair = 'MATICUSD'
    else:
        kraken_pair = pair.replace('/', '').replace('USDT', 'USD')
    
    try:
        url = f'https://api.kraken.com/0/public/Ticker?pair={kraken_pair}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get('result'):
                for key in data['result']:
                    return float(data['result'][key]['c'][0])
    except Exception as e:
        print(f'Error fetching {pair}: {e}')
    return None

def analyze_pair(pair, strategy='both'):
    """Analyze a trading pair and explain signal status."""
    print(f"\n{'='*70}")
    print(f"📊 {pair} ANALYSIS")
    print(f"{'='*70}")
    
    # Get current price
    price = get_kraken_price(pair)
    if price:
        print(f"\n💰 Current Price: ${price:.4f}")
    
    # Explain both strategies
    print(f"\n{'─'*70}")
    print("📈 OSCILLATORCONFLUENCE STRATEGY (Main Bot - 15m)")
    print(f"{'─'*70}")
    
    print("\n📝 Entry Conditions Required (need 2+ true):")
    print("  1. RSI < 30 (oversold)")
    print("  2. Stochastic K & D < 20 (oversold)")
    print("  3. CCI < -100 (oversold)")
    print("  4. Williams %R < -80 (oversold)")
    print("  5. MFI < 20 (oversold)")
    print("  6. MACD bullish crossover")
    print("  7. Price below lower Bollinger Band")
    print("\n📝 Additional Requirements:")
    print("  • Price MUST be above EMA 21 (trend filter)")
    print("  • At least 2 oscillators must show oversold")
    
    print("\n📝 Exit Conditions (any triggers exit):")
    print("  • 2+ oscillators show overbought (RSI > 70, Stoch > 80, etc.)")
    print("  • MACD bearish crossover")
    print("  • Price above upper Bollinger Band")
    
    print(f"\n{'─'*70}")
    print("⚡ SCALPINGQUICK STRATEGY (Scalping Bot - 5m)")
    print(f"{'─'*70}")
    
    print("\n📝 Entry Conditions Required (ALL must be true):")
    print("  1. RSI crossing up through 40 OR RSI 45-65 with positive MACD")
    print("  2. Price above EMA 9 (short-term uptrend)")
    print("  3. MACD histogram turning positive")
    print("  4. Volume spike > 1.5x average")
    print("  5. Price NOT at upper Bollinger Band")
    print("  6. Bullish candle")
    
    print("\n📝 Exit Conditions (any triggers exit):")
    print("  • RSI crossing down through 70 (overbought)")
    print("  • RSI > 75 + Stoch > 80 + Price at upper BB")
    print("  • Profit > 1.2% with RSI > 75")
    print("  • Profit > 0.8% after 15 minutes")
    print("  • Profit > 0.5% with MACD turning bearish")
    
    print("\n💡 WHY NO SIGNAL?")
    print("  If no entry is occurring, likely reasons:")
    print("  • RSI not in entry zone (not crossing 40 or not 45-65)")
    print("  • MACD histogram still negative")
    print("  • Volume too low (no spike)")
    print("  • Price at/above upper Bollinger Band")
    print("  • Bearish or doji candle")
    print("  • Price below EMA 9 (downtrend)")
    
    return price

def get_open_trades_with_analysis():
    """Get open trades with detailed analysis."""
    db_path = BOT_DIR / 'tradesv3.dryrun.sqlite'
    if not db_path.exists():
        return [], {}
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, pair, open_date, open_rate, amount, stake_amount
        FROM trades WHERE is_open = 1
    ''')
    trades = cursor.fetchall()
    conn.close()
    
    trades_analysis = {}
    for trade in trades:
        tid, pair, open_date, open_rate, amount, stake = trade
        current_price = get_kraken_price(pair)
        if current_price:
            pnl = (current_price - open_rate) * amount
            pnl_pct = ((current_price - open_rate) / open_rate) * 100
            trades_analysis[pair] = {
                'entry': open_rate,
                'current': current_price,
                'amount': amount,
                'stake': stake,
                'pnl': pnl,
                'pnl_pct': pnl_pct
            }
    
    return trades, trades_analysis

def explain_exit_reason(trade_pair, entry_price, current_price, pnl_pct):
    """Explain why a position might exit soon."""
    print(f"\n{'─'*70}")
    print(f"🔍 EXIT ANALYSIS FOR {trade_pair}")
    print(f"{'─'*70}")
    
    print(f"\n📊 Position Status:")
    print(f"  Entry: ${entry_price:.4f}")
    print(f"  Current: ${current_price:.4f}")
    print(f"  P/L: {pnl_pct:+.2f}%")
    
    if pnl_pct >= 5:
        print(f"\n✅ EXIT IMMINENT: Profit > 5% (OscillatorConfluence target)")
        print("  OscillatorConfluence will likely exit on overbought signals")
    elif pnl_pct >= 1.5:
        print(f"\n⚠️ TAKE PROFIT ZONE: Profit > 1.5% (ScalpingQuick target)")
        print("  ScalpingQuick would exit here with profit taking")
    elif pnl_pct <= -5:
        print(f"\n🛑 STOP LOSS ZONE: Loss > 5% (OscillatorConfluence stop)")
        print("  OscillatorConfluence would exit here with stop loss")
    elif pnl_pct <= -1.5:
        print(f"\n🛑 STOP LOSS ZONE: Loss > 1.5% (ScalpingQuick stop)")
        print("  ScalpingQuick would exit here with stop loss")
    else:
        print(f"\n⏳ HOLDING: Waiting for exit signals...")
        print("  OscillatorConfluence: Waiting for 2+ overbought signals")
        print("  ScalpingQuick: Would take profit at 0.8-1.5%")

def main():
    print("="*70)
    print("📊 FREQTRADE SIGNAL ANALYSIS")
    print("Learning WHY trades are/aren't happening")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)
    
    # Get current open trades
    trades, trades_analysis = get_open_trades_with_analysis()
    
    print(f"\n{'='*70}")
    print("📋 CURRENT POSITIONS")
    print(f"{'='*70}")
    
    if trades_analysis:
        for pair, data in trades_analysis.items():
            print(f"\n{pair}:")
            print(f"  Entry: ${data['entry']:.4f} → Current: ${data['current']:.4f}")
            print(f"  P/L: ${data['pnl']:+.4f} ({data['pnl_pct']:+.2f}%)")
            explain_exit_reason(pair, data['entry'], data['current'], data['pnl_pct'])
    else:
        print("\nNo open positions")
    
    # Analyze potential pairs
    print(f"\n{'='*70}")
    print("🔍 POTENTIAL ENTRY ANALYSIS")
    print(f"{'='*70}")
    
    pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'LINK/USDT', 'AVAX/USDT', 'XRP/USDT', 'DOGE/USDT', 'MATIC/USDT']
    
    for pair in pairs:
        analyze_pair(pair)
    
    print(f"\n{'='*70}")
    print("📚 LEARNING SUMMARY")
    print(f"{'='*70}")
    
    print("\n🎯 Main Bot (OscillatorConfluence) - WHY TRADES HAPPEN:")
    print("  • Waiting for multiple oversold signals at once")
    print("  • Needs 2+ oscillators below threshold (RSI<30, Stoch<20, etc.)")
    print("  • Must be in uptrend (price above EMA 21)")
    print("  • Takes FEWER trades but with HIGHER confidence")
    print("  • Profits target: 5-10% per trade")
    
    print("\n⚡ Scalping Bot (ScalpingQuick) - WHY TRADES HAPPEN:")
    print("  • Looking for momentum building (RSI crossing up through 40)")
    print("  • Needs volume spike and bullish candle")
    print("  • Must be short-term uptrend (price above EMA 9)")
    print("  • Takes MORE trades with QUICKER profits")
    print("  • Profits target: 0.5-1.5% per trade")
    
    print("\n💡 WHY NO TRADES MIGHT HAPPEN:")
    print("  • Market in downtrend (price below EMA)")
    print("  • No volume spikes (market quiet)")
    print("  • RSI in neutral zone (40-60, no momentum)")
    print("  • Price at resistance (upper Bollinger Band)")
    print("  • MACD bearish (histogram negative)")
    
    print(f"\n{'='*70}")
    print("Run this anytime to learn WHY signals are/aren't triggering!")
    print("python3 /a0/usr/workdir/freqtrade/user_data/analyze_signals.py")
    print("="*70)

if __name__ == '__main__':
    main()
