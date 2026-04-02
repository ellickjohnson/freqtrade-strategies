#!/usr/bin/env python3
"""Trade notification script - sends Slack alerts for trade events."""

import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Configuration
BOT_DIR = Path('/a0/usr/workdir/freqtrade')
DB_PATH = BOT_DIR / 'tradesv3.dryrun.sqlite'
STATE_FILE = Path('/tmp/freqtrade_state.json')
WEBHOOK_FILE = Path('/a0/usr/workdir/.secrets/slack_webhook')

def get_webhook():
    """Get Slack webhook URL."""
    if WEBHOOK_FILE.exists():
        url = WEBHOOK_FILE.read_text().strip()
        if url and not url.startswith('PLACEHOLDER'):
            return url
    return None

def send_slack(text):
    """Send message to Slack."""
    webhook_url = get_webhook()
    if not webhook_url:
        print('No valid webhook configured')
        return False
    try:
        data = json.dumps({'text': text}).encode('utf-8')
        req = urllib.request.Request(webhook_url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode() == 'ok'
    except Exception as e:
        print(f'Slack error: {e}')
        return False

def get_trades():
    """Get current trades from database."""
    if not DB_PATH.exists():
        return None, 'Database not found'
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT id, pair, is_open, open_date, open_rate, amount, stake_amount FROM trades')
        trades = cursor.fetchall()
        conn.close()
        return trades, None
    except Exception as e:
        return None, str(e)

def load_state():
    """Load previous state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {'known_open_ids': [], 'known_closed_ids': []}

def save_state(state):
    """Save current state."""
    STATE_FILE.write_text(json.dumps(state))

def main():
    """Main notification logic."""
    print(f'Trade Notification Check - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    # Get trades
    trades, error = get_trades()
    if error:
        print(f'Error: {error}')
        return 1
    
    # Load state
    state = load_state()
    
    # Categorize trades
    open_trades = [t for t in trades if t[2] == 1]  # is_open = 1
    closed_trades = [t for t in trades if t[2] == 0]  # is_open = 0
    
    current_open_ids = [t[0] for t in open_trades]
    current_closed_ids = [t[0] for t in closed_trades]
    
    # Check for new open trades
    new_opens = [t for t in open_trades if t[0] not in state['known_open_ids']]
    
    # Check for newly closed trades
    new_closes = [t for t in closed_trades if t[0] not in state['known_closed_ids']]
    
    notifications_sent = 0
    
    # Send notifications for new open trades
    for t in new_opens:
        tid, pair, _, open_date, open_rate, amount, stake = t
        msg = f"🟢 NEW TRADE OPENED\n{pair} @ ${open_rate:.2f}\nStake: ${stake:.2f}\nAmount: {amount:.6f}\nTime: {open_date}"
        if send_slack(msg):
            print(f'Notified: NEW OPEN {pair}')
            notifications_sent += 1
    
    # Send notifications for newly closed trades
    for t in new_closes:
        tid, pair, _, open_date, close_date, open_rate, close_rate, stake, profit, exit_reason = t
        pnl = f'+${profit:.4f}' if profit and profit >= 0 else f'-${abs(profit):.4f}' if profit else '$0'
        msg = f"🔴 TRADE CLOSED\n{pair}\nP/L: {pnl}\nExit Reason: {exit_reason or 'N/A'}"
        if send_slack(msg):
            print(f'Notified: CLOSED {pair}')
            notifications_sent += 1
    
    # Update state
    state['known_open_ids'] = current_open_ids
    state['known_closed_ids'] = current_closed_ids
    save_state(state)
    
    print(f'Open trades: {len(open_trades)}, Closed trades: {len(closed_trades)}')
    print(f'Notifications sent: {notifications_sent}')
    
    return 0

if __name__ == '__main__':
    exit(main())
