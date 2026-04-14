"""
Obsidian Memory Store - Creates notes in your Obsidian vault.

This module stores agent memory as Obsidian notes for human-readable
persistent memory and searchability. Uses FilesystemMemoryBackend for
actual file operations.
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from .memory_backend import get_memory_backend

logger = logging.getLogger(__name__)

# Note: The actual Obsidian MCP functions can also be used, but this module
# provides a filesystem-based implementation that works standalone.
# To use MCP tools instead, replace get_memory_backend() with MCP calls.

VAULT_NOTES_FOLDER = "Freqtrade Agent"


async def store_decision_note(decision: Dict) -> tuple:
    """
    Store an agent decision in Obsidian vault.

    Creates a formatted note with reasoning chain.
    Returns the note path and content.
    """
    note_path = f"{VAULT_NOTES_FOLDER}/Decisions/{decision['id']}.md"

    reasoning_steps = decision.get("reasoning_chain", [])
    reasoning_md = "\n".join([f"  - {step}" for step in reasoning_steps])

    status_badge = "✅ Approved" if decision.get("approved_at") else (
        "⏳ Pending" if decision.get("requires_approval") else "✓ Executed"
    )

    content = f"""# Agent Decision: {decision.get('decision_type', 'Unknown')}

**Agent:** {decision.get('agent_type', 'unknown')}
**Decision:** {decision.get('decision_type', 'unknown')}
**Confidence:** {decision.get('confidence', 0):.0%}
**Time:** {decision.get('created_at', datetime.utcnow().isoformat())}
**Status:** {status_badge}

## Reasoning Chain

{reasoning_md}

## Conclusion

{decision.get('conclusion', 'N/A')}

## Context

```json
{decision.get('context', {{}})}
```

## Outcome

{decision.get('outcome', 'Pending')}

---

#decision #{decision.get('agent_type', 'unknown')} #{decision.get('decision_type', 'unknown').replace('_', '-')}
"""

    return note_path, content


async def store_research_finding_note(finding: Dict) -> tuple:
    """
    Store a research finding in Obsidian vault.

    Creates a note with source, analysis, and implications.
    """
    finding_id = finding.get('id', datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
    note_path = f"{VAULT_NOTES_FOLDER}/Research/{finding_id}.md"

    impact_md = ""
    impact = finding.get('impact_assessment', {})
    if impact:
        impact_md = "\n".join([f"- **{k}:** {v}" for k, v in impact.items()])

    entities = finding.get('entities', ['market-wide'])
    entities_md = ", ".join([f"[[{e}]]" for e in entities])

    status_badge = "✅ Applied" if finding.get('applied_at') else "⏳ Pending Application"

    content = f"""# Research Finding: {finding.get('title', 'Untitled')}

**Source:** [[{finding.get('source', 'unknown')}]]
**Type:** {finding.get('finding_type', 'general')}
**Sentiment:** {finding.get('sentiment', 0):.2f}
**Relevance:** {finding.get('relevance', 0):.0%}
**Confidence:** {finding.get('confidence', 0):.0%}
**Time:** {finding.get('created_at', datetime.utcnow().isoformat())}
**Status:** {status_badge}

## Summary

{finding.get('content', '')}

## Impact Assessment

{impact_md or 'Not yet assessed'}

## Affected Entities

{entities_md}

## Trading Implications

*To be analyzed...*

---

#research #{finding.get('source', 'unknown')} #{finding.get('finding_type', 'general')}
"""

    return note_path, content


async def store_strategy_analysis_note(analysis: Dict) -> tuple:
    """
    Store strategy analysis in Obsidian vault.

    Creates a note with performance metrics and recommendations.
    """
    strategy_id = analysis.get('strategy_id', 'unknown')
    timestamp = analysis.get('timestamp', datetime.utcnow().isoformat())
    note_path = f"{VAULT_NOTES_FOLDER}/Analysis/{strategy_id}/{timestamp[:10]}.md"

    metrics = analysis.get('metrics', {})
    issues_md = "\n".join([f"- {i}" for i in analysis.get('issues', [])])
    recommendations_md = "\n".join([f"- {r}" for r in analysis.get('recommendations', [])])

    health_score = analysis.get('health_score', 0)
    health_emoji = "🟢" if health_score >= 70 else ("🟡" if health_score >= 40 else "🔴")

    content = f"""# Strategy Analysis: {analysis.get('strategy_name', strategy_id)}

**Strategy ID:** [[{strategy_id}]]
**Health Score:** {health_emoji} {health_score:.0f}/100
**Time:** {timestamp}

## Performance Metrics

| Metric | Value |
|--------|-------|
| Win Rate | {metrics.get('win_rate', 0):.1%} |
| Sharpe Ratio | {metrics.get('sharpe_ratio', 0):.2f} |
| Max Drawdown | {metrics.get('max_drawdown', 0):.1%} |
| Profit | {metrics.get('profit_pct', 0):.1f}% |
| Total Trades | {metrics.get('total_trades', 0)} |

## Market Regime

**Type:** {analysis.get('market_regime', {}).get('regime_type', 'unknown')}
**Confidence:** {analysis.get('market_regime', {}).get('confidence', 0):.0%}

## Issues Identified

{issues_md or 'No issues identified'}

## Recommendations

{recommendations_md or 'No specific recommendations'}

---

#analysis #{strategy_id}
"""

    return note_path, content


async def store_market_regime_note(regime: Dict) -> tuple:
    """
    Store market regime observation in Obsidian vault.
    """
    date = regime.get('timestamp', datetime.utcnow().isoformat())[:10]
    note_path = f"{VAULT_NOTES_FOLDER}/Market Regimes/{date}.md"

    affected = ", ".join([f"[[{s}]]" for s in regime.get('affected_strategies', ['all'])])
    recommendations_md = "\n".join([f"- {r}" for r in regime.get('recommendations', [])])

    regime_type = regime.get('regime_type', 'unknown')
    regime_emoji = {
        'trending_up': '📈',
        'trending_down': '📉',
        'ranging': '↔️',
        'volatile': '⚡',
    }.get(regime_type, '❓')

    content = f"""# Market Regime: {regime_emoji} {regime_type.replace('_', ' ').title()}

**Date:** {date}
**Confidence:** {regime.get('confidence', 0):.0%}

## Characteristics

{regime.get('characteristics', 'Not specified')}

## Affected Strategies

{affected}

## Trading Recommendations

{recommendations_md}

---

#market-regime #{regime_type}
"""

    return note_path, content


async def store_hyperopt_result_note(result: Dict) -> tuple:
    """
    Store hyperopt results in Obsidian vault.
    """
    hyperopt_id = result.get('hyperopt_id', datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
    note_path = f"{VAULT_NOTES_FOLDER}/Hyperopt/{hyperopt_id}.md"

    status_emoji = "✅" if result.get('status') == 'completed' else (
        "❌" if result.get('status') == 'failed' else "🔄"
    )

    params_md = ""
    best_params = result.get('best_params', {})
    if best_params:
        params_md = "\n".join([f"- **{k}:** {v}" for k, v in best_params.items()])

    metrics = result.get('metrics', {})
    metrics_md = ""
    if metrics:
        metrics_md = "\n".join([f"- **{k}:** {v}" for k, v in metrics.items()])

    content = f"""# Hyperopt Results: {hyperopt_id}

**Strategy:** [[{result.get('strategy_id', 'unknown')}]]
**Status:** {status_emoji} {result.get('status', 'unknown')}
**Time:** {result.get('start_time', 'unknown')}
**Improvement:** {result.get('improvement_pct', 0):.1f}%

## Best Parameters

{params_md or 'No parameters found'}

## Performance Metrics

{metrics_md or 'No metrics available'}

## Reasoning

This hyperopt was run to optimize strategy parameters.
The improvement of {result.get('improvement_pct', 0):.1f}% was achieved over the baseline.

---

#hyperopt #{result.get('strategy_id', 'unknown')[:8]}
"""

    return note_path, content


def get_weekly_summary_template() -> str:
    """Generate weekly summary note template."""
    return f"""# Weekly Summary: {datetime.utcnow().strftime('%Y-W%W')}

## Summary

*Generated by Autonomous Agent*

## Key Decisions

- [ ] Review decisions from this week
- [ ] Apply pending improvements
- [ ] Review risk metrics

## Performance Overview

| Strategy | Health | Win Rate | Sharpe |
|----------|--------|----------|--------|
| *To be filled* | | | |

## Research Highlights

- *Top research findings from the week*

## Next Week Focus

- [ ] Priority 1
- [ ] Priority 2
- [ ] Priority 3

---

#weekly-summary #{datetime.utcnow().strftime('%Y-W%W')}
"""


# Integration functions for the orchestrator

async def sync_to_obsidian(memory_type: str, data: Dict, create_note_func=None) -> Optional[str]:
    """
    Sync agent memory to Obsidian vault.

    This function is called by agents to persist their memory to Obsidian.
    Uses FilesystemMemoryBackend for actual file operations.

    Args:
        memory_type: Type of memory (decision, research, analysis, regime, hyperopt)
        data: Memory data to store
        create_note_func: Optional custom note creation function (for testing)

    Returns:
        Path to created note or None on error.
    """
    try:
        # Format the note based on memory type
        if memory_type == "decision":
            path, content = await store_decision_note(data)
        elif memory_type == "research":
            path, content = await store_research_finding_note(data)
        elif memory_type == "analysis":
            path, content = await store_strategy_analysis_note(data)
        elif memory_type == "regime":
            path, content = await store_market_regime_note(data)
        elif memory_type == "hyperopt":
            path, content = await store_hyperopt_result_note(data)
        else:
            logger.warning(f"Unknown memory type: {memory_type}")
            return None

        # Write to filesystem using the backend
        backend = get_memory_backend()
        success = backend.create_note(path, content)

        if success:
            logger.info(f"Stored {memory_type} note: {path}")
            return path
        else:
            logger.error(f"Failed to store {memory_type} note")
            return None

    except Exception as e:
        logger.error(f"Error syncing to Obsidian: {e}")
        return None


async def search_obsidian_memory(query: str, search_func=None, limit: int = 20) -> List[Dict]:
    """
    Search agent memory in Obsidian vault.

    Uses FilesystemMemoryBackend for search operations.

    Args:
        query: Search query string
        search_func: Optional custom search function (for testing)
        limit: Maximum results to return

    Returns:
        List of matching notes as dicts.
    """
    try:
        backend = get_memory_backend()
        results = backend.search_notes(query, limit)
        return [r.__dict__ for r in results]

    except Exception as e:
        logger.error(f"Error searching Obsidian: {e}")
        return []


def get_memory_summary() -> Dict[str, Any]:
    """
    Get summary statistics about stored memory.

    Returns:
        Dict with counts by type, total notes, etc.
    """
    backend = get_memory_backend()
    return backend.get_summary()


def list_memory_notes(
    memory_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    List notes in the vault.

    Args:
        memory_type: Optional filter by type (decision, research, etc.)
        limit: Maximum results
        offset: Offset for pagination

    Returns:
        List of note metadata dicts.
    """
    backend = get_memory_backend()
    return backend.list_notes(memory_type, limit, offset)