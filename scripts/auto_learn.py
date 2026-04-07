#!/usr/bin/env python3
"""
Auto-Learning System for Freqtrade GridDCA Strategy

Walk-forward hyperopt optimization:
- Runs every 24h on last 90 days of data
- Detects market regime changes
- Hot-swaps optimal parameters into running strategy
- Logs "why it changed" explanations

Usage:
    python auto_learn.py [--dry-run] [--force] [--timerange DAYS]

Cron (daily at 4 AM):
    0 4 * * * cd /a0/usr/workdir/freqtrade && python user_data/auto_learn.py >> user_data/logs/auto_learn.log 2>&1
"""

import subprocess
import json
import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
import re

# Configuration
FREQTRADE_DIR = Path('/a0/usr/workdir/freqtrade')
STRATEGY_FILE = FREQTRADE_DIR / 'user_data/strategies/GridDCA_hyperopted.py'
PARAMS_FILE = FREQTRADE_DIR / 'user_data/hyperopt_results/best_params.json'
LOG_FILE = FREQTRADE_DIR / 'user_data/logs/auto_learn.log'
CONFIG_FILE = FREQTRADE_DIR / 'user_data/config.json'

# Setup logging
os.makedirs(LOG_FILE.parent, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default parameters (optimized via hyperopt)
DEFAULT_PARAMS = {
    'rsi_oversold': 30,
    'rsi_overbought': 80,
    'take_profit_pct': 3.0,
    'max_open_trades_param': 4,
    'grid_spacing_low': 0.01,
    'grid_spacing_high': 0.03,
}

# Regime-based parameter adjustments
REGIME_ADJUSTMENTS = {
    'low_volatility': {
        'reason': 'Low volatility - using tighter grids for mean reversion',
        'adjustments': {
            'grid_spacing_low': 0.005,
            'grid_spacing_high': 0.015,
            'rsi_oversold': 35,
        }
    },
    'high_volatility': {
        'reason': 'High volatility - using wider grids for safety',
        'adjustments': {
            'grid_spacing_low': 0.02,
            'grid_spacing_high': 0.05,
            'take_profit_pct': 4.0,
        }
    },
    'trending_up': {
        'reason': 'Strong uptrend - letting winners run',
        'adjustments': {
            'rsi_overbought': 85,
            'take_profit_pct': 4.0,
        }
    },
    'trending_down': {
        'reason': 'Strong downtrend - conservative entries',
        'adjustments': {
            'rsi_oversold': 25,
            'rsi_overbought': 70,
        }
    },
    'ranging': {
        'reason': 'Ranging market - optimizing for mean reversion',
        'adjustments': {
            'rsi_oversold': 28,
            'rsi_overbought': 75,
        }
    }
}


def get_current_regime() -> str:
    """Detect market regime from recent trades."""
    db_path = FREQTRADE_DIR / 'tradesv3.dryrun.sqlite'
    if not db_path.exists():
        return 'ranging'
    
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT close_profit, open_rate, close_rate 
            FROM trades 
            WHERE is_open = 0 
            AND close_date > datetime('now', '-1 day')
        ''')
        recent_trades = cursor.fetchall()
        conn.close()
        
        if len(recent_trades) < 5:
            return 'ranging'
        
        profits = [t[0] for t in recent_trades if t[0]]
        if not profits:
            return 'ranging'
        
        avg_profit = sum(profits) / len(profits)
        variance = sum((p - avg_profit) ** 2 for p in profits) / len(profits)
        
        if variance > 0.01:
            return 'high_volatility'
        elif avg_profit > 0.005:
            return 'trending_up'
        elif avg_profit < -0.005:
            return 'trending_down'
        elif variance < 0.001:
            return 'low_volatility'
        else:
            return 'ranging'
            
    except Exception as e:
        logger.error(f"Regime detection error: {e}")
        return 'ranging'


def run_hyperopt(timerange_days: int = 90, epochs: int = 100, dry_run: bool = True) -> dict:
    """Run hyperopt on recent data."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=timerange_days)
    timerange = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
    
    logger.info(f"Starting hyperopt: timerange={timerange}, epochs={epochs}")
    
    if dry_run:
        logger.info("[DRY-RUN] Would run hyperopt")
        return DEFAULT_PARAMS.copy()
    
    cmd = [
        'python3', '-m', 'freqtrade', 'hyperopt',
        '--config', str(CONFIG_FILE),
        '--strategy', 'GridDCA_hyperopted',
        '--timerange', timerange,
        '--epochs', str(epochs),
        '--spaces', 'buy', 'sell',
        '--job-workers', '2'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, cwd=str(FREQTRADE_DIR))
        if result.returncode != 0:
            logger.error(f"Hyperopt failed: {result.stderr}")
            return DEFAULT_PARAMS.copy()
        return parse_hyperopt_output(result.stdout)
    except Exception as e:
        logger.error(f"Hyperopt error: {e}")
        return DEFAULT_PARAMS.copy()


def parse_hyperopt_output(output: str) -> dict:
    """Parse hyperopt output for best parameters."""
    params = DEFAULT_PARAMS.copy()
    patterns = {
        'rsi_oversold': r'rsi_oversold.*?value.*?(\d+)',
        'rsi_overbought': r'rsi_overbought.*?value.*?(\d+)',
        'take_profit_pct': r'take_profit_pct.*?value.*?([\d.]+)',
    }
    for param, pattern in patterns.items():
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            params[param] = float(match.group(1))
    return params


def save_params(params: dict, regime: str = 'default'):
    """Save parameters to JSON file."""
    os.makedirs(PARAMS_FILE.parent, exist_ok=True)
    data = {
        'timestamp': datetime.now().isoformat(),
        'regime': regime,
        'params': params,
        'reason': REGIME_ADJUSTMENTS.get(regime, {}).get('reason', 'Optimization result')
    }
    with open(PARAMS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved params: {params}")


def get_current_params() -> dict:
    """Read current parameters from strategy file."""
    params = DEFAULT_PARAMS.copy()
    try:
        with open(STRATEGY_FILE, 'r') as f:
            content = f.read()
        for param in DEFAULT_PARAMS.keys():
            pattern = rf'{param}\s*=.*?default\s*=\s*([\d.]+)'
            match = re.search(pattern, content)
            if match:
                params[param] = float(match.group(1))
    except Exception as e:
        logger.error(f"Could not read params: {e}")
    return params


def log_change(old_params: dict, new_params: dict, regime: str, reason: str):
    """Log parameter changes with explanations."""
    changes = []
    for param, new_val in new_params.items():
        old_val = old_params.get(param)
        if old_val is not None and old_val != new_val:
            delta = new_val - old_val
            direction = "increased" if delta > 0 else "decreased"
            changes.append(f"  {param}: {old_val} -> {new_val} ({direction} by {abs(delta):.4f})")
    
    if changes:
        logger.info("=" * 60)
        logger.info("PARAMETER CHANGE DETECTED")
        logger.info(f"Regime: {regime}")
        logger.info(f"Reason: {reason}")
        logger.info("Changes:")
        for change in changes:
            logger.info(change)
        logger.info("=" * 60)


def main():
    """Main auto-learning loop."""
    parser = argparse.ArgumentParser(description='Freqtrade Auto-Learning System')
    parser.add_argument('--dry-run', action='store_true', help='Run without making changes')
    parser.add_argument('--force', action='store_true', help='Force hyperopt run')
    parser.add_argument('--timerange', type=int, default=90, help='Days for hyperopt')
    parser.add_argument('--epochs', type=int, default=100, help='Hyperopt epochs')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("AUTO-LEARNING SYSTEM STARTING")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Dry-run: {args.dry_run}")
    logger.info("=" * 60)
    
    # Detect regime
    regime = get_current_regime()
    logger.info(f"Detected regime: {regime}")
    
    # Get current params
    current_params = get_current_params()
    logger.info(f"Current params: {current_params}")
    
    # Run hyperopt or use cached
    if not args.dry_run:
        if PARAMS_FILE.exists() and not args.force:
            with open(PARAMS_FILE, 'r') as f:
                cached = json.load(f)
            cached_time = datetime.fromisoformat(cached['timestamp'])
            if datetime.now() - cached_time < timedelta(hours=24):
                logger.info("Using cached hyperopt results")
                new_params = cached['params']
            else:
                new_params = run_hyperopt(args.timerange, args.epochs, args.dry_run)
        else:
            new_params = run_hyperopt(args.timerange, args.epochs, args.dry_run)
    else:
        new_params = DEFAULT_PARAMS.copy()
    
    # Apply regime adjustments
    if regime in REGIME_ADJUSTMENTS:
        for param, value in REGIME_ADJUSTMENTS[regime]['adjustments'].items():
            new_params[param] = value
        logger.info(f"Applied regime adjustments for {regime}")
    
    # Log changes
    reason = REGIME_ADJUSTMENTS.get(regime, {}).get('reason', 'Optimization')
    log_change(current_params, new_params, regime, reason)
    
    # Save params
    if not args.dry_run:
        save_params(new_params, regime)
        logger.info("Parameters saved. Restart bot to apply.")
    else:
        logger.info("[DRY-RUN] Would save these params")
    
    # Summary
    logger.info("=" * 60)
    logger.info("AUTO-LEARNING SUMMARY")
    logger.info(f"Regime: {regime}")
    logger.info(f"Parameters: {new_params}")
    logger.info("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
