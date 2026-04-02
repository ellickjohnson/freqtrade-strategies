#!/usr/bin/env python3
import json
import sqlite3
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

BOT_DIR = Path('/a0/usr/workdir/freqtrade')
DB_PATH = BOT_DIR / 'tradesv3.dryrun.sqlite'
API_URL = 'http://127.0.0.1:8080'

def check_process():
    result = subprocess.run(['pgrep', '-a', 'freqtrade'], capture_output=True, text=True, timeout=5)
    lines = [l for l in result.stdout.strip().split('\n') if l]
    if lines:
        return True, lines[0].split()[0], lines[0]
    return False, None, 'Not running'

def check_api():
    try:
        req = urllib.request.Request(f'{API_URL}/api/v1/ping', method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            return True, json.loads(response.read().decode()).get('status', 'unknown')
    except Exception as e:
        return False, str(e)

def get_db_trades():
    if not DB_PATH.exists():
        return None, 'Database not found'
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT id, pair, is_open, open_date, open_rate, amount, stake_amount FROM trades WHERE is_open = 1')
        open_trades = cursor.fetchall()
        cursor.execute('SELECT id, pair, open_date, close_date, open_rate, close_rate, stake_amount, close_profit_abs, exit_reason FROM trades WHERE is_open = 0 ORDER BY close_date DESC LIMIT 5')
        closed_trades = cursor.fetchall()
        cursor.execute('SELECT COUNT(*) FROM trades')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM trades WHERE is_open = 1')
        open_count = cursor.fetchone()[0]
        cursor.execute('SELECT SUM(close_profit_abs) FROM trades WHERE is_open = 0')
        total_profit = cursor.fetchone()[0] or 0
        conn.close()
        return {'total_trades': total, 'open_count': open_count, 'total_profit': total_profit, 'open_trades': open_trades, 'closed_trades': closed_trades}, None
    except Exception as e:
        return None, str(e)

print('=' * 60)
print('FREQTRADE BOT STATUS')
print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('=' * 60)

running, pid, proc_info = check_process()
print(f'\n[PROCESS] {"RUNNING" if running else "STOPPED"}')
if running:
    print(f'  PID: {pid}')
else:
    print(f'  Error: {proc_info}')

api_ok, api_status = check_api()
print(f'\n[API] {"OK" if api_ok else "FAILED"}')
print(f'  Response: {api_status}')

db_data, db_error = get_db_trades()
print(f'\n[DATABASE] {"OK" if db_data else "ERROR"}')
if db_error:
    print(f'  Error: {db_error}')
if db_data:
    print(f'  Total trades: {db_data["total_trades"]}')
    print(f'  Open trades: {db_data["open_count"]}')
    print(f'  Total P/L: ${db_data["total_profit"]:.4f}')
    print(f'\n[OPEN POSITIONS] {db_data["open_count"]} active')
    for t in db_data['open_trades']:
        print(f'  #{t[0]}: {t[1]} @ ${t[4]:.2f} | Stake: ${t[6]:.2f}')
    print(f'\n[CLOSED TRADES] Last 5')
    if db_data['closed_trades']:
        for t in db_data['closed_trades'][:5]:
            p = t[7]
            print(f'  #{t[0]}: {t[1]} | P/L: {"+" if p >= 0 else ""}${p:.4f}')
    else:
        print('  No closed trades yet')
print('\n' + '=' * 60)
