# Setup Guide - Freqtrade Strategy Dashboard

This guide walks you through setting up and running the Freqtrade Strategy Dashboard.

## Prerequisites

1. **Docker and Docker Compose** - Install from: https://docs.docker.com/get-docker/
2. **Git** - To clone the repository
3. **Slack Webhook** (optional) - Create at: https://api.slack.com/messaging/webhooks

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/freqtrade-strategies.git
cd freqtrade-strategies
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env file
vim .env
```

**Required configuration:**
```bash
# Slack webhook (optional but recommended)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/HERE
```

### 3. Run Dashboard

**Production mode:**
```bash
docker-compose up -d
```

**Development mode (with hot reload):**
```bash
docker-compose -f docker-compose.dev.yml up -d
```

### 4. Access Dashboard

Open your browser:
- **Dashboard**: http://localhost:3000
- **Manager API Docs**: http://localhost:8000/docs

## First-Time Setup

### 1. Auto-Detect Existing Strategies

The dashboard will automatically detect existing Freqtrade configs in the `config/` directory:

- `config.json`
- `config-dry-run.json`
- `config-freqai.json`
- `config_scalp.json`

### 2. Create New Strategy from Template

1. Click **"New Strategy"** button
2. Select a template:
   - GridDCA
   - OscillatorConfluence
   - ScalpingQuick
   - BreakoutMomentum
   - TrendMomentum
   - GridDCA + FreqAI
3. Configure:
   - Strategy name
   - Trading pairs (e.g., BTC/USDT, ETH/USDT)
   - Exchange (default: Kraken)
   - Parameters (using sliders/inputs)
4. Click **"Create"**
5. Start the strategy with **"Start"** button

### 3. Monitor Strategies

Each strategy card shows:
- **Status**: Running/Stopped/Error
- **P&L**: Current profit/loss
- **Win Rate**: Percentage of winning trades
- **Trades**: Open/Closed count
- **Pairs**: Configured trading pairs

Click a strategy card to view:
- Detailed performance chart
- Trade history
- FreqAI insights (if enabled)
- Real-time logs
- Configuration editor

### 4. Configure Slack Notifications

Edit `.env` file:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
```

Notifications include:
- 🚀 Strategy started
- ⏹ Strategy stopped
- ✅ Backtest complete
- 🤖 FreqAI model trained
- 💰 Trade alerts
- ❌ Errors

Test notification:
```bash
curl -X POST http://localhost:8000/api/slack/test
```

## Architecture

### Docker Containers

```
┌──────────────────────┐
│  Dashboard (Port 3000) │  Next.js + React + Tailwind
└──────────┬───────────┘
           │ REST + WebSocket
┌──────────┴───────────┐
│  Manager (Port 8000)  │  FastAPI + Docker SDK
└──────────┬───────────┘
           │ Docker socket
┌──────────┴───────────┐
│  Freqtrade Containers │  Multiple strategies
│  (Ports 7070+)        │  Paper trading only
└──────────────────────┘
```

### Data Flow

```
Dashboard UI
    ↓ REST API requests
Manager (FastAPI)
    ↓ Docker SDK
Freqtrade Containers (spawns)
    ↓
SQLite databases (trades, logs)
    ↓
Dashboard (aggregates and displays)
```

## Configuration Details

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_WEBHOOK_URL` | Slack webhook for notifications | (required) |
| `FREQTRADE_IMAGE` | Freqtrade Docker image | `freqtradeorg/freqtrade:stable` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MANAGER_PORT` | Manager WebSocket port | `8765` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL for dashboard | `ws://localhost:8765` |
| `NEXT_PUBLIC_API_URL` | REST API URL for dashboard | `http://localhost:3000/api` |
| `DATABASE_PATH` | Dashboard SQLite path | `/data/dashboard.db` |
| `BASE_PORT` | Starting port for strategies | `7070` |

### Docker Volumes

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `./config` | `/configs` | Freqtrade config files |
| `./strategies` | `/strategies` | Strategy Python files |
| `./user_data` | `/user_data` | Runtime data, logs, models |
| `./data` | `/data` | Dashboard database |

### Port Allocation

| Port | Service | Description |
|------|---------|-------------|
| 3000 | Dashboard | Next.js web interface |
| 8000 | Manager | FastAPI REST API |
| 8765 | Manager | WebSocket server |
| 7070 | Strategy 1 | First strategy container |
| 7071 | Strategy 2 | Second strategy container |
| 7072+ | Strategy N | Additional strategies |

## Using the Dashboard

### Strategy Management

#### Start a Strategy

1. Find the strategy card
2. Click **"Start"** button
3. Wait for container to start (2-5 seconds)
4. Status changes to **"Running"**

#### Stop a Strategy

1. Find the strategy card
2. Click **"Stop"** button
3. Container stops immediately
4. Status changes to **"Stopped"**

#### Edit Configuration

1. Click the **gear icon** on strategy card
2. Modify parameters:
   - Stop loss: -5% to -15%
   - RSI threshold: 20-40
   - Max trades: 1-10
   - Stake amount: $10-$1000
   - Trailing stop: Enable/disable
3. Click **"Save"**
4. Restart strategy to apply changes

#### View Details

1. Click strategy card to expand
2. View:
   - Performance chart (candlestick)
   - Trade history
   - FreqAI insights (if enabled)
   - Log viewer
   - Configuration file

### Backtesting Hub

#### Run Backtest

1. Navigate to **"Backtest"** tab
2. Select strategy
3. Choose time range:
   - Quick: Last 30 days
   - Custom: Select start/end dates
4. Adjust parameters (sliders):
   - Stop loss
   - Take profit
   - RSI threshold
   - etc.
5. Click **"Run Backtest"**
6. View results:
   - Total profit/loss
   - Win rate
   - Sharpe ratio
   - Drawdown
   - Trade count

#### Compare Backtests

1. Run multiple backtests with different parameters
2. Click **"Compare"** button
3. Side-by-side comparison:
   - Profit comparison
   - Win rate comparison
   - Parameter differences

### FreqAI Insights

#### View Model Status

For FreqAI-enabled strategies:

1. Click strategy card
2. Navigate to **"FreqAI"** tab
3. View:
   - Model type (LightGBM, XGBoost, etc.)
   - Training time
   - Accuracy/Precision/Recall
   - Feature importance chart

#### Understand Predictions

For each trade, FreqAI shows:

1. **Model Confidence**: 0-100%
2. **Contributing Features**:
   - RSI: 34% importance
   - Volume: 28% importance
   - ATR: 21% importance
   - etc.
3. **Market Regime**: Trending/Ranging/Volatile
4. **Supporting Indicators**: Why the signal triggered

#### Trade Explainability

Example output:

```
Entry Signal: BTC/USDT Long @ $67,234
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Model Confidence: 87%
Market Regime: RANGING_LOW_VOLATILITY

Top Contributing Features:
1. RSI_14 (score: -1.82)    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 34%
2. Volume_ratio (1.34)    ▓▓▓▓▓▓▓▓▓▓▓▓ 27%
3. ATR_14 (0.054)          ▓▓▓▓▓▓▓▓ 21%

Traditional Signals:
✓ RSI < 25 (oversold)
✓ Price < EMA20 (mean reversion)
✓ Volume spike (1.34x average)
```

### Portfolio Summary

Top-level metrics:

- **Total P&L**: Across all strategies
- **Daily/Weekly/Monthly P&L**: Time-based breakdown
- **Win Rate**: Aggregate percentage
- **Open Trades**: Currently active
- **Active Strategies**: Running count

### Real-Time Updates

Dashboard uses WebSocket for live updates:

- **Trade notifications**: Instant alerts
- **Status changes**: Running ↔ Stopped
- **Log streaming**: Tail logs in real-time
- **P&L updates**: Refresh every 5 seconds

## Common Tasks

### Add New Exchange

1. Edit `.env` file:
```bash
EXCHANGE_NAME=binance
```

2. Create new config in `config/config-binance.json`:
```json
{
  "exchange": {
    "name": "binance",
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"]
  }
}
```

3. Restart dashboard:
```bash
docker-compose restart
```

### Add Custom Strategy

1. Create strategy file in `strategies/`:
```python
# strategies/MyCustomStrategy.py

class MyCustomStrategy(IStrategy):
    # Your strategy implementation
    pass
```

2. Dashboard auto-detects new strategy
3. Create template in `manager.py` or use existing template

### Import Existing Backtest Results

1. Place results in `data/results/`
2. Dashboard auto-imports compatible JSON files

### Scale Multiple Strategies

Each strategy runs in its own container:

```bash
# Check running strategies
docker ps | grep freqtrade

# View strategy logs
docker logs freqtrade-<strategy-id>

# Resource usage
docker stats
```

## Troubleshooting

### Dashboard Won't Start

```bash
# Check logs
docker-compose logs dashboard

# Common issues:
# - Port 3000 in use → Change in docker-compose.yml
# - Database locked → rm data/dashboard.db
# - Missing dependencies → docker-compose build --no-cache
```

### Manager Won't Start

```bash
# Check logs
docker-compose logs manager

# Common issues:
# - Docker socket permission → sudo chmod 666 /var/run/docker.sock
# - Missing Python deps → docker-compose build --no-cache
```

### Strategy Won't Start

```bash
# Check strategy-specific logs
docker logs freqtrade-<strategy-id>

# Common issues:
# - Invalid config → Validate JSON syntax
# - Missing strategy file → Check strategies/ directory
# - Port conflict → Change BASE_PORT in .env
```

### No Slack Notifications

```bash
# Test webhook
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK \
  -d '{"text":"Test message"}'

# Verify environment
docker-compose exec manager env | grep SLACK
```

### WebSocket Connection Failed

```bash
# Check WebSocket server
curl http://localhost:8000/health

# Verify URL in browser console
# localStorage.getItem('NEXT_PUBLIC_WS_URL')
```

### Performance Issues

```bash
# Monitor resources
docker stats

# Check database size
ls -lh data/

# Limit log retention
# Edit .env:
LOG_MAX_SIZE=10M
LOG_MAX_FILES=3
```

## Development

### Run in Development Mode

```bash
# Start with hot reload
docker-compose -f docker-compose.dev.yml up -d

# View dashboard logs
docker-compose -f docker-compose.dev.yml logs -f dashboard

# View manager logs
docker-compose -f docker-compose.dev.yml logs -f manager
```

### Make Changes

1. **Dashboard UI**:
   - Edit files in `dashboard/`
   - Changes auto-reload in dev mode

2. **Manager API**:
   - Edit files in `freqtrade_manager/`
   - Changes auto-reload in dev mode

3. **Strategies**:
   - Add files to `strategies/`
   - Dashboard detects changes immediately

### Run Tests

```bash
# Python tests
cd freqtrade_manager
pytest tests/

# Dashboard tests
cd dashboard
npm test
```

## Security Notes

- **Paper Trading Only**: All strategies default to dry-run mode
- **No Authentication**: Dashboard has no auth (local development only)
- **Docker Socket**: Requires host docker.sock access
- **No External Access**: Bind to localhost only

For production:

1. Add authentication layer
2. Use HTTPS
3. Restrict API access
4. Remove Docker socket access
5. Use external database (PostgreSQL)

## Next Steps

1. **Create Your First Strategy**: Use a template and customize parameters
2. **Run Backtests**: Test strategies before live trading
3. **Monitor Performance**: Watch real-time updates
4. **Optimize**: Adjust parameters based on results
5. **Scale**: Add more strategies as needed

## Support

- GitHub Issues: https://github.com/YOUR_USERNAME/freqtrade-strategies/issues
- Freqtrade Docs: https://www.freqtrade.io/en/stable/

---

Built with ❤️ for the Freqtrade community