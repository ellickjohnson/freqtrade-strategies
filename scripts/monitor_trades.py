#!/usr/bin/env python3
"""Monitor freqtrade trades and send Slack notifications."""
import json
import urllib.request
import os
import time
from datetime import datetime

# Slack webhook URL from secrets
SLACK_WEBHOOK = open('/a0/usr/workdir/.secrets/slack_webhook').read().strip() if os.path.exists('/a0/usr/workdir/.secrets/slack_webhook') else None

# State file
STATE_FILE = '/tmp/trade_state.json'
API_BASE = 'http://localhost:8080/api/v1'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'known_trades': [], 'last_check': None}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def send_slack_notification(message):
    if not SLACK_WEBHOOK:
        print("No Slack webhook configured")
        return
    try:
        data = json.dumps({'text': message}).encode('utf-8')
        req = urllib.request.Request(SLACK_WEBHOOK, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Slack notification sent: {resp.read().decode()}")
    except Exception as e:
        print(f"Slack notification failed: {e}")

def get_api(endpoint):
    try:
        req = urllib.request.Request(f'{API_BASE}/{endpoint}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"API error: {e}")
        return None

def main():
    print(f"Trade monitor running at {datetime.now()}")
    
    # Check API
    ping = get_api('ping')
    if not ping or ping.get('state') != 'running':
        print("Bot not running, skipping check")
        return
    
    # Get active trades
    active_trades = get_api('status') or []
    
    # Load state
    state = load_state()
    known_ids = set(state.get('known_trades', []))
    
    # Check for new trades
    for trade in active_trades:
        trade_id = str(trade.get('trade_id', ''))
        if trade_id and trade_id not in known_ids:
            # New trade opened
            pair = trade.get('pair', 'Unknown')
            open_rate = trade.get('open_rate', 0)
            amount = trade.get('amount', 0)
            direction = 'LONG' if trade.get('is_open', True) else 'CLOSED'
            
            message = f"🔔 New Trade Opened\nPair: {pair}\nDirection: {direction}\nEntry Price: ${open_rate:.4f}\nAmount: {amount:.4f}"
            send_slack_notification(message)
            known_ids.add(trade_id)
    
    # Check for closed trades
    all_trades = get_api('trades?limit=50') or []
    active_ids = {str(t.get('trade_id', '')) for t in active_trades}
    
    for trade in all_trades:
        trade_id = str(trade.get('trade_id', ''))
        if trade_id in known_ids and trade_id not in active_ids:
            # Trade closed
            pair = trade.get('pair', 'Unknown')
            close_rate = trade.get('close_rate', 0)
            open_rate = trade.get('open_rate', 0)
            profit_pct = trade.get('profit_pct', 0)
            
            emoji = '🟢' if profit_pct >= 0 else '🔴'
            message = f"{emoji} Trade Closed\nPair: {pair}\nEntry: ${open_rate:.4f}\nExit: ${close_rate:.4f}\nProfit: {profit_pct:+.2f}%"
            send_slack_notification(message)
    
    # Update state
    state['known_trades'] = list(known_ids)
    state['last_check'] = datetime.now().isoformat()
    save_state(state)
    
    print(f"Checked {len(active_trades)} active trades, {len(known_ids)} known")

if __name__ == '__main__':
    main()
