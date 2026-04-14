# Autonomous Financial Engineering Agent System

## Overview

This system provides autonomous, LLM-powered financial engineering agents that continuously research, analyze, and improve trading strategies.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR AGENT                                  │
│  - Coordinates all sub-agents                                                 │
│  - Prioritizes research tasks                                                 │
│  - Makes portfolio-level decisions                                            │
│  - Observability dashboard integration                                        │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┬─────────────────────┐
        │                       │                       │                     │
        ▼                       ▼                       ▼                     ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐    ┌─────────────────┐
│ RESEARCH AGENT │     │ ANALYSIS AGENT  │     │ RISK AGENT      │    │ STRATEGY AGENT  │
│               │     │                 │     │                 │    │                 │
│ - News/Sent.  │     │ - Performance    │     │ - Drawdown     │    │ - Create new    │
│ - On-chain    │     │ - Correlations   │     │ - Position     │    │ - Optimize      │
│ - Macro data  │     │ - Market regime │     │ - Exposure     │    │ - Deprecate     │
│ - Social      │     │ - Backtest eval  │     │ - VaR          │    │ - Hyperopt      │
└───────┬───────┘     └────────┬────────┘     └────────┬────────┘    └────────┬────────┘
        │                      │                       │                      │
        └──────────────────────┴───────────────────────┴──────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │           KNOWLEDGE GRAPH           │
                    │  - Strategy performance history      │
                    │  - Market regime patterns            │
                    │  - Research findings                 │
                    │  - Decision reasoning logs           │
                    └─────────────────────────────────────┘
```

## Agent Responsibilities

### 1. Orchestrator Agent
- Runs continuously (every 5-15 minutes)
- Coordinates all sub-agents
- Prioritizes tasks based on urgency/importance
- Makes portfolio-level decisions
- Logs all reasoning to `agent_logs` table
- Sends notifications for critical events

### 2. Research Agent
- Fetches news, social sentiment, on-chain data
- Identifies market-moving events
- Discovers new trading opportunities
- Tracks macro economic indicators
- Stores findings in knowledge graph

### 3. Analysis Agent
- Evaluates strategy performance
- Detects market regime changes
- Correlates strategies with market conditions
- Backtests strategy modifications
- Generates improvement hypotheses

### 4. Risk Agent
- Monitors drawdown across portfolio
- Calculates Value at Risk (VaR)
- Tracks position exposure
- Adjusts position sizes dynamically
- Triggers emergency stops

### 5. Strategy Agent
- Creates new strategies from templates
- Runs hyperopt optimizations
- Deprecates poor performers
- Applies research findings
- Manages strategy lifecycle

## Data Flow

```
External Data ──► Research Agent ──► Knowledge Graph
                                              │
                    ┌─────────────────────────┤
                    │                         │
                    ▼                         ▼
            Analysis Agent            Risk Agent
                    │                         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                         Strategy Agent
                                 │
                                 ▼
                      ┌─────────────────┐
                      │ FreqAI/Freqtrade│
                      │   Strategies    │
                      └─────────────────┘
                                 │
                                 ▼
                        Dashboard/API
```

## API Endpoints

### Autonomous Control
- `POST /api/autonomous/start` - Start autonomous mode
- `POST /api/autonomous/stop` - Stop autonomous mode
- `GET /api/autonomous/status` - Get current autonomous status
- `GET /api/autonomous/decisions` - View recent agent decisions
- `GET /api/autonomous/reasoning` - View reasoning logs

### Research
- `POST /api/research/news` - Trigger news research
- `POST /api/research/sentiment` - Trigger sentiment analysis
- `GET /api/research/findings` - Get research findings

### Strategy Lifecycle
- `POST /api/strategies/{id}/lifecycle/evaluate` - Evaluate strategy health
- `POST /api/strategies/{id}/lifecycle/deprecate` - Deprecate strategy
- `POST /api/strategies/{id}/lifecycle/promote` - Promote to production

## Configuration

```json
{
  "autonomous_mode": {
    "enabled": true,
    "orchestrator_interval_minutes": 5,
    "max_concurrent_research": 3,
    "min_improvement_threshold": 5.0,
    "auto_apply_improvements": false,
    "paper_trading_only": true
  },
  "research_sources": {
    "news_apis": ["newsapi", "cryptocompare"],
    "sentiment_sources": ["twitter", "reddit", "discord"],
    "on_chain_sources": ["glassnode", "dune"],
    "macro_sources": ["fred", "tradingeconomics"]
  },
  "risk_limits": {
    "max_drawdown_pct": 15,
    "max_position_pct": 10,
    "max_correlated_positions": 3,
    "var_confidence": 0.95
  },
  "strategy_lifecycle": {
    "min_trades_for_evaluation": 100,
    "min_sharpe_ratio": 0.5,
    "max_drawdown_pct": 20,
    "min_uptime_days": 7,
    "deprecation_threshold": -5
  },
  "notifications": {
    "slack": true,
    "email": false,
    "critical_decisions": true
  }
}
```

## Usage

### Starting Autonomous Mode

```bash
# Start the autonomous agent
curl -X POST http://localhost:8000/api/autonomous/start

# Check status
curl http://localhost:8000/api/autonomous/status
```

### Viewing Agent Reasoning

```bash
# Get recent decisions
curl http://localhost:8000/api/autonomous/decisions?limit=10

# Get reasoning for specific decision
curl http://localhost:8000/api/autonomous/decisions/{decision_id}/reasoning
```

## Monitoring

The dashboard shows:
- Active agents and their status
- Recent research findings
- Pending decisions requiring approval
- Strategy health scores
- Risk metrics in real-time
- Performance attribution

## Safety Features

1. **Paper Trading Default**: All autonomous operations start in paper trading mode
2. **Approval Thresholds**: High-impact changes require human approval
3. **Rollback Capability**: Automatic rollback on performance degradation
4. **Circuit Breakers**: Stop all operations on critical errors
5. **Audit Trail**: Every decision logged with full reasoning