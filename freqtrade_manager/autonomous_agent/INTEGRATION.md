# Autonomous Agent Integration Guide

This guide shows how to integrate the autonomous agent system with your existing freqtrade-manager.

## Quick Start

### 1. Add Autonomous Routes to main.py

Add these imports and call at the end of your `main.py`:

```python
# Add to imports at top of freqtrade_manager/main.py
from autonomous_api import setup_autonomous_routes

# Add after the app is created, before if __name__ == "__main__":
# Setup autonomous agent routes
orchestrator = setup_autonomous_routes(app, db, manager, ws_server)
```

### 2. Set Environment Variables

Create or update your `.env` file:

```bash
# LLM Configuration
ANTHROPIC_API_KEY=your_anthropic_key_here

# Optional: Other LLM providers
# OPENAI_API_KEY=your_openai_key
# OLLAMA_BASE_URL=http://localhost:11434

# Obsidian Integration (optional)
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
```

### 3. Install Dependencies

Add to your `requirements.txt`:

```
anthropic>=0.18.0
aiohttp>=3.9.0
```

### 4. Add Dashboard Components

Import the new components in your `dashboard/app/page.tsx`:

```tsx
import { AutonomousDashboard } from '@/components/dashboard/AutonomousDashboard'
import { ApprovalQueue } from '@/components/dashboard/ApprovalQueue'
import { RiskDashboard } from '@/components/dashboard/RiskDashboard'
import { AutonomousConfig } from '@/components/dashboard/AutonomousConfig'
```

Add new navigation tabs:

```tsx
const [activeView, setActiveView] = useState<'dashboard' | 'autonomous' | 'approvals' | 'risk' | 'config'>('dashboard')

// In navigation:
<Button variant={activeView === 'autonomous' ? 'default' : 'ghost'} onClick={() => setActiveView('autonomous')}>
  <Brain className="h-4 w-4 mr-2" />
  Autonomous
</Button>

<Button variant={activeView === 'approvals' ? 'default' : 'ghost'} onClick={() => setActiveView('approvals')}>
  <AlertTriangle className="h-4 w-4 mr-2" />
  Approvals {pendingCount > 0 && <Badge>{pendingCount}</Badge>}
</Button>
```

### 5. Create Obsidian Folder Structure

Create these folders in your Obsidian vault:

```
Freqtrade Agent/
├── Decisions/
├── Research/
├── Analysis/
├── Market Regimes/
└── Hyperopt/
```

## API Endpoints

### Autonomous Control
- `GET /api/autonomous/status` - Get agent status
- `POST /api/autonomous/start` - Start autonomous mode
- `POST /api/autonomous/stop` - Stop autonomous mode
- `GET /api/autonomous/config` - Get configuration
- `PUT /api/autonomous/config` - Update configuration

### Decisions
- `GET /api/autonomous/decisions` - Get recent decisions
- `GET /api/autonomous/decisions/{id}` - Get decision with reasoning

### Approvals
- `GET /api/autonomous/approvals` - Get pending approvals
- `POST /api/autonomous/approvals/{id}/approve` - Approve decision
- `POST /api/autonomous/approvals/{id}/reject` - Reject decision

### Research
- `GET /api/autonomous/findings` - Get research findings
- `POST /api/autonomous/findings/{id}/apply` - Apply finding to strategy

### Risk
- `GET /api/autonomous/risk` - Get portfolio risk report

### Strategy Lifecycle
- `GET /api/autonomous/strategies/health` - Get strategy health scores
- `POST /api/autonomous/strategies/{id}/deprecate` - Deprecate strategy
- `POST /api/autonomous/strategies/{id}/promote` - Promote to live

### Hyperopt
- `POST /api/autonomous/hyperopt` - Run hyperopt
- `GET /api/autonomous/hyperopt/status/{id}` - Get status
- `POST /api/autonomous/hyperopt/{id}/cancel` - Cancel run

### Memory (Obsidian)
- `GET /api/autonomous/memory/search` - Search memory
- `GET /api/autonomous/memory/summary` - Get summary

## How It Works

### Agent Loop

Every 5 minutes (configurable), the orchestrator:

1. **Gathers Context** - Gets all strategy statuses, portfolio summary
2. **Runs Research Agent** - Fetches news, sentiment, on-chain data
3. **Runs Analysis Agent** - Evaluates strategy performance
4. **Runs Risk Agent** - Checks portfolio risk limits
5. **Makes Decisions** - Uses LLM to decide on actions
6. **Executes Approved** - Runs approved decisions
7. **Logs Reasoning** - Stores everything to knowledge graph + Obsidian

### Decision Flow

```
Research → Analysis → Risk Check → LLM Decision → Approval? → Execute
                                                    ↓
                                               Knowledge Graph
                                                    ↓
                                               Obsidian Vault
```

### Obsidian Integration

All agent memory is synced to Obsidian for:

1. **Human Readability** - Notes are formatted markdown
2. **Searchability** - Use Obsidian's search to find past decisions
3. **Backlinks** - Strategies link to decisions, decisions to findings
4. **Graph View** - See relationships between entities

### Search Example

In Obsidian, search for:
- `#decision stop_strategy` - All decisions to stop strategies
- `#research btc` - All research about Bitcoin
- `#analysis OscillatorConfluence` - Analysis for specific strategy
- `[[market-regime]]` - All market regime observations

## Safety Features

1. **Paper Trading Default** - All operations start in paper mode
2. **Approval Queue** - High-impact decisions need human approval
3. **Risk Limits** - Circuit breakers stop trading on excessive losses
4. **Memory Audit** - Every decision logged with reasoning chain
5. **Rollback** - Can revert any applied changes

## Configuration

Key settings in the dashboard:

| Setting | Default | Description |
|---------|---------|-------------|
| Interval | 5 min | How often agent runs |
| Auto-Apply | Off | Automatically apply improvements |
| Paper Trading | On | Only paper trade |
| Max Drawdown | 15% | Circuit breaker threshold |
| Min Improvement | 5% | Threshold for auto-apply |

## Architecture

```
freqtrade_manager/
├── autonomous_agent/
│   ├── __init__.py
│   ├── llm_client.py          # LLM interface (Claude, OpenAI, Ollama)
│   ├── knowledge_graph.py     # SQLite memory
│   ├── orchestrator.py        # Main agent loop
│   ├── research_agent.py      # External data fetching
│   ├── analysis_agent.py      # Strategy analysis
│   ├── risk_agent.py          # Risk management
│   ├── strategy_agent.py      # Lifecycle management
│   ├── hyperopt_executor.py  # Real hyperopt execution
│   ├── obsidian_memory.py    # Obsidian integration
│   └── obsidian_store.py     # Note templates
├── autonomous_api.py          # FastAPI routes
└── main.py                    # Your existing app
```

## Monitoring

Watch agent activity in real-time:

```bash
# Tail agent logs
tail -f /data/dashboard.db  # SQLite

# In Obsidian, check:
Freqtrade Agent/Decisions/  # All decisions
Freqtrade Agent/Research/    # All findings
```

## Troubleshooting

### Agent not starting decisions
- Check LLM API key is set
- Check logs for LLM errors
- Verify paper_trading_only is True initially

### No research findings
- Check news API keys
- Verify external API connectivity
- Check rate limiting

### Obsidian not syncing
- Check OBSIDIAN_VAULT_PATH is set
- Verify folder structure exists
- Check file permissions