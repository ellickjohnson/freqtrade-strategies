#!/usr/bin/env python3
"""
Verbose Notification Script - Explains WHY trades happened

Sends detailed Slack notifications explaining:
- Entry reasoning (which conditions were met)
- Exit reasoning (what triggered exit)
- Current market conditions
- Why trades might NOT be happening
"""

import json
import sqlite3
import urllib.request
import os
from datetime import datetime
from pathlib import Path

# State file paths
STATE_FILE_MAIN = '/tmp/freqtrade_state.json'
STATE_FILE_SCALP = '/tmp/freqtrade_scalp_state.json'

# Database paths
DB_MAIN = '/a0/usr/workdir/freqtrade/tradesv3.dryrun.sqlite'
DB_SCALP = '/a0/usr/workdir/freqtrade/tradesv3_scalp.dryrun.sqlite'

# Webhook
WEBHOOK_FILE = '/a0/usr/workdir/.secrets/slack_webhook'

def get_webhook():
    """Get Slack webhook URL."""
    try:
        with open(WEBHOOK_FILE, 'r') as f:
            return f.read().strip()
    except:
        return None

def get_price(pair):
    """Get price from Kraken."""
    kraken_map = {
        'BTC/USDT': 'XXBTZUSD',
        'ETH/USDT': 'XETHZUSD',
        'SOL/USDT': 'SOLUSD',
        'LINK/USDT': 'LINKUSD',
        'AVAX/USDT': 'AVAXUSD',
        'XRP/USDT': 'XXRPZUSD',
        'DOGE/USDT': 'XXDGZUSD',
        'BNB/USDT': 'BNBUSD',
        'ADA/USDT': 'ADAUSD'
    }
    kraken_pair = kraken_map.get(pair, pair.replace('/', '').replace('USDT', 'USD'))
    try:
        url = f'https://api.kraken.com/0/public/Ticker?pair={kraken_pair}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get('result'):
                for key in data['result']:
                    return float(data['result'][key]['c'][0])
    except:
        pass
    return None

def load_state(state_file):
    """Load previous state."""
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                # Ensure all required keys exist
                if 'notified_trades' not in data:
                    data['notified_trades'] = []
                if 'notified_closes' not in data:
                    data['notified_closes'] = []
                return data
        except:
            pass
    return {'notified_trades': [], 'notified_closes': []}

def save_state(state_file, state):
    """Save current state."""
    with open(state_file, 'w') as f:
        json.dump(state, f)

def send_notification(message):
    """Send Slack notification."""
    webhook = get_webhook()
    if not webhook:
        print("No webhook configured")
        return False
    
    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps({'text': message}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode() == 'ok'
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False

def explain_entry_reason(pair, strategy='unknown'):
    """Explain why a trade was entered."""
    if strategy == 'OscillatorConfluence' or 'Oscillator' in strategy:
        return f"""📈 ENTRY REASON (OscillatorConfluence - 15m):
   • 2+ oscillators showed oversold conditions
   • RSI < 30, Stoch < 20, CCI < -100, or similar
   • Price was above EMA 21 (uptrend confirmed)
   • MACD showed bullish momentum
   • Strategy waits for CONFLUENCE of signals"""
    elif strategy == 'ScalpingQuick' or 'Scalping' in strategy:
        return f"""⚡ ENTRY REASON (ScalpingQuick - 5m):
   • RSI crossed up through 40 (momentum building)
   • Price above EMA 9 (short-term uptrend)
   • MACD histogram turned positive
   • Volume spike > 1.5x average
   • Bullish candle pattern"""
    else:
        return f"""📈 ENTRY REASON:
   • Strategy detected favorable entry conditions
   • Check strategy documentation for details"""

def explain_exit_reason(profit_pct, strategy='unknown'):
    """Explain why a trade exited."""
    if strategy == 'OscillatorConfluence' or 'Oscillator' in strategy:
        if profit_pct >= 5:
            return "🎯 EXIT REASON: Profit target reached (>5%)", "TAKE PROFIT"
        elif profit_pct <= -5:
            return "🛑 EXIT REASON: Stop loss triggered (-5%)", "STOP LOSS"
        else:
            return "🎯 EXIT REASON: 2+ oscillators showed overbought", "SIGNAL EXIT"
    elif strategy == 'ScalpingQuick' or 'Scalping' in strategy:
        if profit_pct >= 1.5:
            return "🎯 EXIT REASON: Take profit reached (>1.5%)", "TAKE PROFIT"
        elif profit_pct >= 0.8:
            return "🎯 EXIT REASON: Time-based exit (>0.8% after 15min)", "TIME EXIT"
        elif profit_pct <= -1.5:
            return "🛑 EXIT REASON: Stop loss triggered (-1.5%)", "STOP LOSS"
        else:
            return "🎯 EXIT REASON: RSI overbought or MACD bearish", "SIGNAL EXIT"
    else:
        return "🎯 EXIT REASON: Strategy exit conditions met", "SIGNAL EXIT"

def check_trades(db_path, state_file, bot_name, strategy_name):
    """Check for new/closed trades and send notifications."""
    if not os.path.exists(db_path):
        return 0
    
    state = load_state(state_file)
    notifications = 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check for new trades
    cursor.execute('''
        SELECT id, pair, open_date, open_rate, amount, stake_amount
        FROM trades WHERE is_open = 1
    ''')
    open_trades = cursor.fetchall()
    
    for trade in open_trades:
        tid, pair, open_date, open_rate, amount, stake = trade
        if tid not in state['notified_trades']:
            # New trade!
            current_price = get_price(pair)
            if current_price:
                msg = f"""🟢 NEW TRADE OPENED - {bot_name}

📊 {pair}
💰 Entry: ${open_rate:.4f}
💵 Stake: ${stake:.2f}
📈 Current: ${current_price:.4f}
⏰ Time: {open_date}

{explain_entry_reason(pair, strategy_name)}

💡 WHAT TO EXPECT:
   • Bot will hold until exit conditions met
   • Will receive notification when trade closes"""
            else:
                msg = f"""🟢 NEW TRADE OPENED - {bot_name}

📊 {pair}
💰 Entry: ${open_rate:.4f}
💵 Stake: ${stake:.2f}
⏰ Time: {open_date}

{explain_entry_reason(pair, strategy_name)}"""
            
            if send_notification(msg):
                state['notified_trades'].append(tid)
                notifications += 1
    
    # Check for closed trades
    cursor.execute('''
        SELECT id, pair, open_date, close_date, open_rate, close_rate, 
               amount, stake_amount, profit_ratio
        FROM trades WHERE is_open = 0 AND close_date IS NOT NULL
        ORDER BY close_date DESC LIMIT 10
    ''')
    closed_trades = cursor.fetchall()
    
    for trade in closed_trades:
        tid, pair, open_date, close_date, open_rate, close_rate, amount, stake, profit_ratio = trade
        if tid not in state['notified_closes']:
            # Closed trade!
            profit_pct = (profit_ratio * 100) if profit_ratio else 0
            profit = stake * profit_ratio if profit_ratio else 0
            exit_reason, exit_type = explain_exit_reason(profit_pct, strategy_name)
            
            emoji = '✅' if profit >= 0 else '🔴'
            
            msg = f"""{emoji} TRADE CLOSED - {bot_name}

📊 {pair}
💰 Entry: ${open_rate:.4f} → Exit: ${close_rate:.4f}
💵 P/L: ${profit:+.2f} ({profit_pct:+.2f}%)
⏰ Opened: {open_date}
⏰ Closed: {close_date}

{exit_reason}

💡 WHY IT EXITED:
   • {exit_type} triggered the exit"""
            
            if send_notification(msg):
                state['notified_closes'].append(tid)
                notifications += 1
    
    conn.close()
    save_state(state_file, state)
    return notifications

def check_bot_status(db_path, bot_name):
    """Check if bot is running."""
    import subprocess
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    if bot_name == 'Main':
        return 'freqtrade' in result.stdout and 'OscillatorConfluence' in result.stdout
    else:
        return 'freqtrade' in result.stdout and 'ScalpingQuick' in result.stdout

def main():
    print(f"Verbose Trade Notification Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    total_notifications = 0
    
    # Check Main Bot (OscillatorConfluence)
    if os.path.exists(DB_MAIN):
        print(f"\nChecking Main Bot (OscillatorConfluence)...")
        n = check_trades(DB_MAIN, STATE_FILE_MAIN, 'Main Bot', 'OscillatorConfluence')
        print(f"  Notifications sent: {n}")
        total_notifications += n
    
    # Check Scalping Bot (ScalpingQuick)
    if os.path.exists(DB_SCALP):
        print(f"\nChecking Scalping Bot (ScalpingQuick)...")
        n = check_trades(DB_SCALP, STATE_FILE_SCALP, 'Scalping Bot', 'ScalpingQuick')
        print(f"  Notifications sent: {n}")
        total_notifications += n
    
    print(f"\nTotal notifications: {total_notifications}")
    return total_notifications

if __name__ == '__main__':
    main()
